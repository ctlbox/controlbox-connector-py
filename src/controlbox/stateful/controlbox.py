from concurrent.futures import CancelledError

from controlbox.protocol.async import FutureValue
from controlbox.protocol.controlbox import Controlbox
from controlbox.stateful.controller import BaseProfile, ContainedObject, Container, InstantiatedObjectDescriptor, \
    ObjectTypeMapper, Profile, ReadableObject, RootContainerTraits, SystemProfile, SystemRootContainer, WritableObject,\
    fetch_dict
from controlbox.stateless.api import ControlboxApplicationAdapter, FailedOperationError


class StatefulControlbox(Controlbox):
    """Provides a stateful, synchronous object API to controlbox. The controller and proxy objects provide
       the application view of the external controller.
    :param: stateless  The connector that provides the transport stream to the remote controller
    :param: object_types  A mapper between object classes and type ids
    """
    def __init__(self, stateless: ControlboxApplicationAdapter, object_types: ObjectTypeMapper):
        """
        :param stateless:       The stateless connector that provides stateless events from the controller
        :param object_types:    The factory describing the object types available in the controller.
        """
        super().__init__(stateless.controlbox.connector)
        self.stateless = stateless
        self._object_types = object_types
        self._profiles = dict()
        self._system_root = SystemRootContainer()
        self._current_profile = None
        # todo - listen for connect/disconnect events from the connector, and
        # attach/detach the profiles

    def _initialize(self, load_profile=True):
        self._system_root.controller = self
        self._system_profile = self._build_system_profile()
        self._instantiate_profile(self._system_profile, self._system_root)

        if load_profile:
            self._set_current_profile(self.active_and_available_profiles()[0])

    def _attached(self):
        for profile_id, profile in self._profiles.items():
            profile.attach(self)

    def _detached(self):
        for profile_id, profile in self._profiles.items():
            profile.detach()

    @property
    def types(self)->ObjectTypeMapper:
        return self._object_types

    def _update_objects(self, time, object_values):
        for obj, value in object_values:
            obj._update_value(value)

    def full_erase(self):
        """
        Erases all profiles in the device.
        """
        available = self.active_and_available_profiles()
        for p in available[1]:
            self.delete_profile(p)

    def read_value(self, obj: ReadableObject):
        fn = self.stateless.read_system if self.is_system_object(obj) else self.stateless.read
        future = fn(obj.id_chain, obj.type)
        return self.result_from(future)

    def write_value(self, obj: WritableObject, value):
        fn = self.stateless.write_system if self.is_system_object(obj) else self.stateless.write
        return self._write_value(obj, value, fn)

    def write_masked_value(self, obj: WritableObject, value):
        fn = self.protocol.write_system_masked_value if self.is_system_object(
            obj) else self.protocol.write_masked_value
        return self._write_masked_value(obj, value, fn)

    def delete_object(self, obj: ContainedObject):
        self._delete_object_at(obj.id_chain)

    def next_slot(self, container) -> int:
        return self._handle_error(self._connector.protocol.next_slot, container.id_chain)

    def create_profile(self, profile: Profile=None):
        profile_id = self._handle_error(
            self._connector.protocol.create_profile)
        return self.profile_for(profile_id, profile)

    def delete_profile(self, p: Profile):
        self._handle_error(self.protocol.delete_profile, p.profile_id)
        if self._current_profile == p:
            self._set_current_profile(None)
        # profile may have already been deleted
        self._profiles.pop(p.profile_id, None)

    def activate_profile(self, p: Profile or None):
        """ activates the given profile. if p is None, the current profile is deactivated. """
        self._handle_error(self.protocol.activate_profile, Profile.id_for(p))
        self._set_current_profile(p)

    def active_and_available_profiles(self):
        """
            returns a tuple - the first element is the active profile, or None if no profile is active.
            the second element is a sequence of profiles.
        """
        future = self.stateless.profile_definitions()
        data = StatefulControlbox.result_from(future)
        activate = self.profile_for(data[0], True)
        available = tuple([self.profile_for(x) for x in data[1]])
        return activate, available

    def is_active_profile(self, p: Profile):
        active = self.active_and_available_profiles()[0]
        return False if not active else active.profile_id == p.profile_id

    def list_objects(self, p: Profile):
        future = self.protocol.list_profile(p.profile_id)
        data = StatefulControlbox.result_from(future)
        for d in data[0]:
            yield self._materialize_object_descriptor(*d)

    def reset(self, erase_eeprom=False, hard_reset=True):
        # todo - move this to application
        # if erase_eeprom:  # return the id back to the pool if the device is being wiped
        #     current_id = self.system_id().read()
        #     id_service.return_id(current_id)
        self._handle_error(self.protocol.reset, 1 if erase_eeprom else 0 or 2 if hard_reset else 0)
        if erase_eeprom:
            self._profiles.clear()
            self._current_profile = None

    def is_system_object(self, obj: ContainedObject):
        return obj.root_container() == self._sysroot

    def _write_value(self, obj: WritableObject, value, fn):
        future = fn(obj.id_chain, value, obj.type)
        new_value = self.result_from(future)
        obj._update_value(new_value)
        return new_value

    def _write_masked_value(self, obj: WritableObject, value, fn):
        encoded = obj.encode_masked(value)
        data = self._fetch_data_block(fn, obj.id_chain, *encoded)
        if not data:
            raise FailedOperationError("could not write masked value")
        new_value = obj.decode(data)
        obj._update_value(new_value)
        return new_value

    def uninstantiate(self, id_chain, optional=False):
        o = self.object_at(id_chain, optional)
        if o is not None:
            # notify the object's container that it has been removed
            o.container.notify_removed(o)
        self._current_profile._remove(id_chain)

    def _delete_object_at(self, id_chain, optional=False):
        """
        :param id_chain:    The id chain of the object to delete
        :param optional:    When false, deletion must succeed (the object is deleted). When false, deletion may silently
            fail for a non-existent object.
        """
        self._handle_error(self.protocol.delete_object, id_chain, allow_fail=optional)
        self.uninstantiate(id_chain, optional)

    def create_object(self, obj_class, args=None, container=None, slot=None) -> ContainedObject:
        """
        :param obj_class: The type of object to create
        :param args: The constructor arguments for the object. (See documentation for each object for details.)
        :param container: The container to create the object in, If None, the object is created in the root container
            of the active profile.
        :param slot:    The slot to create the object in. If None, the next available empty slot is used. If not None,
            that specific slot is used, replacing any existing object at that location.
        :return: The proxy object representing the created object in the controller
        :rtype: an instance of obj_class
        """
        container = container or self.root_container
        slot is not None and self._delete_object_at(
            container.id_chain_for(slot), optional=True)
        slot = slot if slot is not None else self.next_slot(container)
        data = (args is not None and obj_class.encode_definition(args)) or None
        dec = args and obj_class._decode_object_definition(data, controller=self)
        if dec != args:
            raise ValueError(
                "encode/decode mismatch for value %s, encoding %s, decoding %s" % (args, data, dec))
        return self._create_object(container, obj_class, slot, data, args)

    def _create_object(self, container: Container, obj_class, slot, data: bytes, args):
        data = data or []
        id_chain = container.id_chain_for(slot)
        self._handle_error(self._connector.protocol.create_object,
                           id_chain, obj_class.type_id, data)
        obj = self._instantiate_stub(obj_class, container, id_chain, args)
        return obj

    def _instantiate_stub(self, obj_class, container, id_chain, args):
        """ Creates the stub object for an existing object in the controller."""
        obj = obj_class(self, container, id_chain[-1])
        obj.definition = args
        self._current_profile._add(obj)
        container.notify_added(obj)
        return obj

    def _handle_error(self, fn, *args, allow_fail=False):
        future = fn(*args)
        error = self.result_from(future)
        if error < 0 and not allow_fail:
            raise FailedOperationError("errorcode %d" % error)
        return error

    @property
    def root_container(self):
        p = self._check_current_profile()
        return p.root

    def result_from(self, future: FutureValue, discard_on_exception=True):
        try:
            return None if future is None else future.value(self.timeout)
        except (CancelledError, TimeoutError):
            if discard_on_exception:
                self.discard_future(future)

    def discard_future(self, future: FutureValue):
        self.stateless.discard_future(future)

    def profile_for(self, profile_id, profile=None, may_be_negative=False):
        if profile_id < 0:  # todo - raise error specific to the error code
            if may_be_negative:
                return None
            raise ValueError("negative profile id")
        return fetch_dict(self._profiles, profile_id, lambda x: Profile())

    def container_at(self, id_chain):
        o = self.object_at(id_chain)
        return o

    def object_at(self, id_chain, optional=False):
        p = self._check_current_profile()
        return p.object_at(id_chain, optional)

    @staticmethod
    def container_chain_and_id(id_chain):
        """
        >>> StatefulControlbox.container_chain_and_id(b'\x50\x51\x52')
        (b'\x50\x51', 82)
        """
        return id_chain[:-1], id_chain[-1]

    def _container_slot_from_id_chain(self, id_chain):
        chain_prefix, slot = self.container_chain_and_id(id_chain)
        container = self.container_at(chain_prefix)
        return container, slot

    def _materialize_object_descriptor(self, id_chain, obj_type, data):
        """ converts the obj_type (int) to the object class, converts the id to a container+slot reference, and
            decodes the data.
        """
        # todo - the object descriptors should be in order so that we can
        # dynamically build the container proxy
        container, slot = self._container_slot_from_id_chain(id_chain)
        cls = self._object_types.from_id(obj_type)
        args = cls.decode_definition(data, controller=self) if data else None
        return InstantiatedObjectDescriptor(self, container, slot, cls, args)

    def ref(self, obj_class, args, id_chain):
        """ helper method to create an object reference from the class, args and id_chain. """
        container, slot = self._container_slot_from_id_chain(id_chain)
        return InstantiatedObjectDescriptor(self, container, slot, obj_class, args)

    def _check_current_profile(self) -> Profile:
        if not self._current_profile:
            raise FailedOperationError("no current profile")
        return self._current_profile

    # noinspection PyProtectedMember
    def _set_current_profile(self, profile: Profile):
        if self._current_profile:
            self._current_profile._deactivate()
        self._current_profile = None
        if profile:
            self._current_profile = profile
            profile._activate()

    @property
    def current_profile(self):
        return self._current_profile

    def _build_system_profile(self):
        """Construct the system profile instance."""
        profile = SystemProfile.create(self)
        return profile

    def _uninstantiate_profile(self, profile, root: RootContainerTraits):
        """tear down the active objects in the given root"""
        root.walk(lambda obj: obj.detach())

    def _instantiate_profile(self, profile: BaseProfile, root: RootContainerTraits):
        """make the profile active by listing the profile and instantiating the objects and attach them all to the
        controller."""
        profile.attach(self)
        profile._populate_object_definitions(root)
        root.att()
