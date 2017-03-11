"""
Provides an object oriented interface to a controlbox instance.
The objects represent application state, and mirror the corresponding
objects running in the controller.

It is stateful, in that the objects synchronize their state with the state in the controller as it is
made available.
"""
from abc import ABCMeta, abstractmethod

from controlbox.stateless.api import ProfileNotActiveError
from controlbox.stateless.codecs import Decoder, EmptyCodec, Encoder
from controlbox.support.events import EventSource
from controlbox.support.mixins import CommonEqualityMixin


class ControlboxException(Exception):
    pass


class ControlboxUsageException(ControlboxException):
    """
    Describes controlbox usage errors.
    """


class ControlboxDetachedException(ControlboxUsageException):
    """
    An active connection to the controlbox instance is required.
    """


class ControlboxObject(CommonEqualityMixin, EventSource):
    """A Controlbox object represents an object running in a remote controlbox instance.
        The object maintains a reference to the controller, and provides deep equality
        comparison and a source of events.

        During typical operation, the ControlboxObject acts as a proxy
        to the corresponding object running in the active profile or in the
        system container of a running controlbox instance. Operations on this
        object are reflected in the remote instance, and changes to the
        remote instance are reflected in the proxy.

        The object may be in a detached state, where changes are no longer propagated:
        - when an instance is newly created, but not yet added to a container.
        - when the current profile is changed, and the object is no longer part of the active profile
        - when the connection to the controller is lost
    """

    def __init__(self):
        super().__init__()
        super(EventSource, self).__init__()

    @property
    def controller(self)-> "StatefulControlbox":
        return self._controller

    @controller.setter
    def controller(self, controller):
        self._controller = controller

    def attach(self, controller):
        self.controller = controller

    def detach(self):
        self.controller = None

    def fire_object_event(self, type, data=None):
        self.fire(type(self, data))

    def ensure_attached(self) -> "StatefulControlbox":
        return self.ensure_controller()

    def ensure_controller(self):
        """
        ensure that we have a local controller instance.
        The object may be in a detached state.
        :return:
        """
        if self.controller is None:
            raise ControlboxDetachedException()
        return self.controller

    def walk(self, callback):
        callback(self)


class InstantiatedObjectDescriptor(ControlboxObject):
    """ Describes an instantiated object in the controller.
        The reference describes the object's location (container/slot)
        the class of the object and the arguments used to configure it.
        It is used to describe the objects configured in a profile.
        """

    def __init__(self, controller, container, slot, obj_class, args):
        super().__init__(controller)
        self.container = container
        self.slot = slot
        self.obj_class = obj_class
        self.args = args
        # todo - rather than referencing the construction arguments, why not
        # actually instantiate the type and initialize it?
        # the main reason perhaps is that the object is not a proxy to real state in
        # the controller, but a description of the initial state of the instantiated object

    @property
    def id_chain(self):
        """
        Retrieves the ID chain of the object that is being referenced.
        """
        return self.container.id_chain_for(self.slot)

    def __str__(self):
        return "%s(%r)" % (self.__class__, self.__dict__)  # noqa: H501

    def __repr__(self):
        return self.__str__()


class ContainerTraits(ControlboxObject, metaclass=ABCMeta):
    """
    A mixin that describes the expected behavior for container implementations.
    """
    @abstractmethod
    def id_chain_for(self, slot):
        """ retrieve the full chain for an ID composed of this container's ID and the given slot """
    # todo ^^ is this needed? seems like a utility method that can be factored out
    # no need to have it on each implementation.

    @abstractmethod
    def item(self, slot) -> ControlboxObject:
        """
        Fetches the item at this container's location.
        """

    @abstractmethod
    def items(self) -> dict():
        """
        retrieves a mapping from slot number to the item
        :return:
        """

    @abstractmethod
    def root_container(self):
        """
        Retrieve the root container from this container.
        """

    def for_each(self, callback):
        dict = self.items()
        for k, v in dict.items():
            callback(k, v)

    def walk(self, callback):
        """Walk all objects in the container, calling the given callback for each one. """
        super().walk(self)
        self.for_each(lambda k, v: v.walk(callback))


class TypedObject(ControlboxObject):
    """ A typed object has a type ID that is used to identify the object type to the controller. """

    @property
    def type(self):
        """Retrieve the type of this object as a type-id."""
        cls = self.__class__
        return self.controller.types.as_id(cls)


class StatefulEvent:
    """
    Base class for stateful events.
    """
    def __init__(self, source, data=None):
        self.source = source
        self.data = data


class StatefulLifetimeEvent(StatefulEvent):
    """ Describes events that relate to the lifetime of an object. """


class ObjectCreatedEvent(StatefulLifetimeEvent):
    """ Event that is posted when an object has been created. """


class ObjectDeletedEvent(StatefulLifetimeEvent):
    """ Event that is posted when an object has been deleted. """


class ContainedObject(TypedObject):
    """ An object in a container. Contained objects have a slot that is the id relative to the container
        the object is in. The full id_chain is the container's id plus the object's slot in the container.
        The type of the object is used to provide a controlbox type-id. This is used
        to infer the read/write format.
    """

    def __init__(self):
        self._container = None
        self._slot = None
        self._id_chain = None

    @property
    def container(self) -> ContainerTraits:
        """Retrieve the container this object is contained in."""
        return self._container

    def is_added(self):
        """Determine if this object has been added to a container."""
        return self._slot is not None

    def _notify_added(self, container, slot=None):
        """
        notification that this object was added to a slot in a container.
        if the container is attached, slot will be an integer.
        if the container is not attached, slot will be None
        This even may be fired twice - once when the python instance
        is added to the corresponding python container (slot is None)
        and again when the object is added to the container in the controller.
        :param container:
        :param slot:
        :return:
        """
        self._container = container
        self._slot = slot
        self._id_chain = container.id_chain_for(slot)
        self.detach()
        controller = container.controller
        if controller:
            self.attach(controller)

    def _notify_removed(self, container, slot=None):
        """Notification that this object was removed from the container.
           When slot is not None, this means the notification was
           received from the controller that the object was removed,
           but it is yet to be removed from the python proxy.
           When it is removed from the proxy, this method is called
           with slot=None
        """
        self._slot = None
        self._id_chain = None
        self.detach()
        if slot is None:
            self._container = None

    @property
    def id_chain(self):
        """ Retrieves the id_chain for this object as a iterable of integers.
        :return: The id-chain for this object
        :rtype:
        """
        return self._id_chain

    def parent(self):
        return self._container

    def root_container(self):
        return self._container.root_container()


class UserObject(ContainedObject):
    """ An object that is instantiated in a profile and managed by a container.
        (In contrast to system objects which are automatically instantiated by the system.)
    """
    # todo - we can probably remove this since it doesn't really add anything useful
    # after classes to distinguish system/user objects were removed.

    def delete(self):
        """Delete the corresponding object on the controller then detach this proxy from the controller. """
        container = self._container
        if container:
            container.remove(self)


class Container(ContainedObject, ContainerTraits):
    """ A generic non-root container. Being a non-root container, the container is always contained within a parent
    container. """

    def __init__(self):
        super().__init__()
        self.items = {}

    def id_chain_for(self, slot):
        return self.id_chain + (slot,)

    def item(self, slot):
        return self.items[slot]

    def root_container(self):
        return self.container.root_container()


class OpenContainerTraits(ContainerTraits):
    """
    Traits of a container that allows objects to be added and removed from it.
    """
    @abstractmethod
    def add(self, obj: ContainedObject, slot=None):
        """
        adds the given object to the container. The slot is determined
         if not already given. If an object already exists at the given slot, it is removed first.

        When the container is attached:
         - the controller is asked for the next slot if slot is None
         - the object creation request is sent to the controller.
         - if the object is not added, an exception is thrown. otherwise the
        object's _notify_added() method is called with the slot it was added to.

        When the container is detached:
         - the object is added to the container and added to a list of objects to add to the controller

        :param obj:
        :param slot: the location to add the object. If None, a location is chosen by the system.
        :return: obj
        """

    @abstractmethod
    def remove(self, obj: ContainedObject, slot=None):
        """
        removes the given object from the container. if the object does not
         exist at the given slot, an exception is raised.

        When the container is attached:
         - the controller is instructed to delete the object at the given location
         - if the object is not removed, an exception is thrown. otherwise the
        object's _notify_removed(container,slot) method is called with the slot,
        signifying it was removed in the controller.
        later the object's _notify_removed(container) method is called after the object
        has been removed from the python container.

        When the container is detached:
         - the object is removed from the container and added to a list of objects to remove in the controller

        :param obj:
        :return:
        """
        # todo - I'm not sure if add/remove should function detached
        # the main rationale is to allow a hierarchy to be created independently from a running controller
        # an alternative implementation has these methods raise a detached exception,
        # and the caller enqueue a command for later execution when the controller is reconnected

    def _add(self, obj, slot):
        """add the object to this python container. This does not propagate the
        request to the controller."""

    def _remove(self, obj, slot):
        """add the object to this python container. This does not propagate the
        request to the controller."""

    def notify_added(self, obj: ContainedObject, slot):
        """ Notification from the controller that this object will be added to this container. This is called
            after the object has been added in the controller. """
        self._add(obj, slot)
        obj._notify_added(self, slot)

    def notify_removed(self, obj: ContainedObject, slot):
        """ Notification from the controller that this object will be removed from this container. This is called
            prior to removing the object from the container in the controller and clearing the container member in the
            contained object. """
        self._remove(obj, slot)
        obj._notify_removed(self, slot)


class RootContainerTraits(ContainerTraits):
    """ Describes the traits of a root container implementation.
        It has no parent
    """
    def id_chain_for(self, slot):
        return slot,

    @property
    def id_chain(self):
        """ Returns the id chain for this root container, which is an empty sequence.
        :return: An empty sequence
        :rtype:
        """
        return tuple()

    def root_container(self):
        return self

    # todo add a reference to the profile?
    # when the profile is deactivated we need some way to stop attempts at changing the profile
    # the profile could still be available in read only mode.


class BaseProfile(ControlboxObject):
    """Describes the behaviour of all profiles"""
    def __init__(self):
        super().__init__()
        self.profile_id = None
        self.definitions = None

    def activate(self):
        """Activate this profile on the controller and """
        controller = self.ensure_attached()
        controller._activate_profile(self)
        return self

    def _populate_object_definitions(self, root):
        controller = self.ensure_attached()
        definitions = controller.list_profile(self.profile_id)
        return definitions  # avoid flake8 error


class SystemProfile(BaseProfile):
    """Represents the system profile. This profile is not created or deleted by
    user code, but instantiated by the system."""

    system_profile_id = -1

    def activate(self):
        """Activate the system profile. In practice this deactivates
        any current user profile. """
        super().activate()

    def deactivate(self):
        """The system profile cannot be deactivated."""

    @staticmethod
    def create(controller):
        profile = SystemProfile()
        profile.controller = controller
        return profile._populate_system_profile()

    def _populate_system_profile(self):
        self.profile_id = self.system_profile_id
        self._populate_object_definitions(SystemRootContainer())
        return self


class Profile(BaseProfile):
    """Represents a profile - a profile is a persisted set of object definitions.
    When the profile is active, the root container in the system is instantiated
    with the contents of the profile. Objects added and removed to the root or a descendent
    update the contents of the profile.

    Internally a profile is identified by an integer ID.
    """

    def create(self):
        """
        creates a new user Profile
        :return:
        """
        self.ensure_attached()
        self.controller.create_profile()

    def __eq__(self, other):
        return other is self or \
            (type(other) == type(
                self) and self.profile_id == other.profile_id and self.controller is other.controller)

    def refresh(self, obj):
        """ retrieve the current proxy for the given object id chain. """
        # todo - not sure we should do this - an object proxy can have a lifetime longer than profile activation.
        # when the profile is activated, the object state is synchronized <> controller.
        return self.object_at(obj.id_chain)

    def activate(self):
        self.controller.activate_profile(self)

    def deactivate(self):
        if self.active:
            self.controller.activate_profile(None)

    def delete(self):
        # todo - all contained objects should refer to the profile they are
        # contained in, and
        self.controller.delete_profile(self)

    @property
    def root(self):
        """
        retrieves the root container.
        raises ProfileNotActive if the profile isn't active.
        """
        # todo - rather than raising an exception,
        # should we still allow enumeration of the object types in an inactive profile,
        # but not allow their state to be retrieved?
        self._check_active()
        return self._objects[tuple()]

    def _check_active(self):
        """ if this profile isn't active raise ProfileNotActiveError. """
        if not self.active:
            raise ProfileNotActiveError()

    @property
    def active(self):
        """ determines if this profile is active. """
        return self.controller.is_active_profile(self)

    def object_at(self, id_chain, optional=False):
        obj = self._objects.get(tuple(id_chain))
        if not optional and obj is None:
            raise ValueError("no such object for id_chain %s " % id_chain)
        return obj

    @classmethod
    def id_for(cls, p):
        """ retrieves the id for a given profile object, which is >= 0. If the profile is None, returns -1."""
        return p.profile_id if p else -1

    def _deactivate(self):
        """  This profile is no longer active, so detach all objects from the controller to prevent any unintended
             access.
        """
        for x in self._objects.values():
            x.controller = None  # make them zombies
        self._objects.clear()

    def _activate(self):
        """
        Called by the controller to activate this profile. The profile instantiates the stub root container
        and the other stub objects currently in the profile.
        """
        # self._add(ControllerLoopContainer(self))
        for ref in self.controller.list_objects(self):
            self.controller._instantiate_stub(
                ref.obj_class, ref.container, ref.id_chain, ref.args)

    def _add(self, obj: ControlboxObject):
        self._objects[tuple(obj.id_chain)] = obj

    def _remove(self, id_chain):
        self._objects.pop(id_chain, None)


class RootContainer(RootContainerTraits, OpenContainerTraits, ControlboxObject):
    """ A root container is the top-level container in a profile."""
    def __init__(self, profile: Profile):
        super().__init__(profile.controller)
        self.profile = profile


class SystemRootContainer(RootContainerTraits, ControlboxObject):
    """ Represents the container for system objects. The user cannot instantiate
        objects here, but the system can. """


class ForwardingDecoder(Decoder):
    """ Decoder implementation that forwards to another decoder instance. This allows the encoding implementation to be
    changed at runtime. """
    decoder = None

    def __init__(self, decoder=None):
        if decoder:
            self.decoder = decoder

    def decode(self, buf, mask=None):
        return self.decoder.decode(buf)


def make_default_mask(buf):
    """
    >>> make_default_mask(bytearray(3))
    bytearray(b'\xff\xff\xff')
    """
    for x in range(len(buf)):
        buf[x] = 0xFF
    return buf


class ForwardingEncoder(Encoder):
    """ Encoder implementation that forwards to another encoder instance. This allows the encoding implementation to
    be changed at runtime. """
    encoder = None

    def __init__(self, encoder: Encoder=None):
        if encoder:
            self.encoder = encoder

    def encode(self, value):
        return self.encoder.encode(value)


class ValueChangedEvent(StatefulEvent):

    def __init__(self, source, before, after):
        super().__init__(source, (before, after))

    def before(self):
        return self.data[0]

    def after(self):
        return self.data[1]


class ReadableObject(ContainedObject):
    """
    A readable object can update the current state from the controller.
    """
    def read(self):
        controller = self.ensure_attached()
        return controller.read_value(self)

    @abstractmethod
    def _update(self, state):
        """update the state of this object from the decoded state from the stateless layer"""


class WritableObject(ReadableObject):

    def write(self):
        controller = self.ensure_attached()
        controller.write(self)

    @abstractmethod
    def _value(self):
        """Retrieve the current state of this object as expected by the stateless
        layer."""


class ValueObject(WritableObject):
    """
    Describes an object in the container with an associated value
    """
    def __init__(self):
        super().__init__()
        self.value = None

    def _update(self, new_value):
        """
        Updates the value associated with this object
        If the value has changed, a ValueChangedEvent is fired.
        """
        p = self.value
        self.value = new_value
        if p != new_value:
            self.fire(ValueChangedEvent(self, p, new_value))
        return new_value

    def _value(self):
        return self.value


class DynamicContainer(EmptyCodec, OpenContainerTraits, Container):
    """
    todo - need to figure out the sequence of adding an object to the container.
    Since an object's location is part of it's identity/construction, the python objects surely represent
    non-created objects, which are then instantiated in the controlbox?
    """
    def add(self, obj: ContainedObject, slot=None):
        raise NotImplementedError()

    def remove(self, obj: ContainedObject, slot=None):
        raise NotImplementedError()


def fetch_dict(d: dict, k, generator):
    """
    Fetches a key from the given dictionary. If the value does not exist (is None)
    The generator is called with k to produce the value, which is then stored in the dictionary.
    :param d:
    :param k:
    :param generator:
    :return:
    """
    existing = d.get(k, None)
    if existing is None:
        d[k] = existing = generator(k)
    return existing


class ObjectTypeMapper:
    """
    Provides a mapping between class types in the API and type IDs sent to controlbox.
    """
    def __init__(self, mappings: dict=None):
        """
        :param: mappings    A dictionary mapping from type_id to class. These are additional
            mappings that can be added in addition to the types returned from all_types()
        """
        self._from_id = dict((self.as_id(x), x) for x in self.all_types())
        if mappings:
            self._from_id.update(mappings)
        self._to_id = {cls: id for id, cls in self._from_id.items()}

    def all_types(self):
        raise NotImplementedError()

    def instance_id(self, obj: TypedObject):
        """
        Retrieves the typeid of a controlbox object.
        """
        return obj.type_id

    def from_id(self, type_id) -> TypedObject:
        """
        Determines the class from the type id.
        """
        return self._from_id.get(type_id, None)

    def as_id(self, clazz):
        return self._to_id.get(clazz, None)
