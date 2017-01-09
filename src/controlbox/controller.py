"""
Provides an object model interface to a controlbox instance.
The objects represent application state, and mirror the corresponding
objects running in the controller.

It is stateful.  For a stateless equivalent, see events.py and ControlboxEvents.
"""
from abc import abstractmethod

from controlbox.adapter import Controlbox, FailedOperationError, ProfileNotActiveError
from controlbox.protocol.async import FutureResponse
from controlbox.protocol.controlbox import signed_byte, unsigned_byte, longDecode
from controlbox.support.events import EventSource
from controlbox.support.mixins import CommonEqualityMixin


timeout = 10  # long enough to allow debugging, but not infinite so that build processes will eventually terminate
# todo - get rid of the timeout or make it part of the constructor


class BaseControlboxObject(CommonEqualityMixin, EventSource):
    """ A Controlbox object maintains a reference to the controller, and provides deep quality
        comparison and a source of events."""

    def __init__(self, controller: "TypedControlbox"):
        super().__init__()
        super(EventSource, self).__init__()
        self._controller = controller

    @property
    def controller(self)->"TypedControlbox":
        return self._controller

    @controller.setter
    def controller(self, controller):
        self._controller = controller

    @property
    def type(self):
        cls = self.__class__
        return self.controller.types.as_id(cls)


class ObjectReference(BaseControlboxObject):
    """ Describes a reference to an object in the controller.
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


class ObjectEvent():
    """
    Base class for object events.
    """
    def __init__(self, source, data=None):
        self.source = source
        self.data = data


class ObjectLifetimeEvent(ObjectEvent):
    """ Describes events that relate to the lifetime of an object. """


class ObjectCreatedEvent(ObjectLifetimeEvent):
    """ Event that is posted when an object has been created. """
    # todo - currently not used here


class ObjectDeletedEvent(ObjectLifetimeEvent):
    """ Event that is posted when an object has been deleted. """
    # todo - currently not used here


class ControlboxObject(BaseControlboxObject):
    """  A proxy to an object in a running container. """
    @property
    @abstractmethod
    def id_chain(self):
        """  all controlbox objects have an id chain that describes their location and id in the system. """
        raise NotImplementedError

    def file_object_event(self, type, data=None):
        self.fire(type(self, data))


class ContainerTraits:
    """
    A mixin that describes the expected behavior for container implementations.
    """
    @abstractmethod
    def id_chain_for(self, slot):
        """ retrieve the full chain for an ID composed of this container's ID and the given slot """
        raise NotImplementedError

    def item(self, slot) -> ControlboxObject:
        """
        Fetches the item at this container's location.
        """
        raise NotImplementedError

    def root_container(self):
        """
        Retrieve the root container from this container.
        """
        raise NotImplementedError


class TypedObject:
    """ A typed object has a type ID that is used to identify the object type to the controller. """
    def __init__(self):
        self.type_id = None


class InstantiableObject(ControlboxObject, TypedObject):
    """
    Base implementation for objects that can be instantiated.
    It provides class methods for converting between construction parameters in python and the binary representation.
    """
    def __init__(self, controller):
        super().__init__(controller)
        self.definition = None

    @classmethod
    @abstractmethod
    def decode_definition(cls, data_block: bytes, controller, *args, **kwargs):
        """ decodes the object's definition data block from the controller to python objects """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def encode_definition(cls, args) -> bytes:
        """ encodes the construction parameters for the object into a data block """
        raise NotImplementedError

    def delete(self):
        """ deletes the corresponding object on the controller then detaches this proxy from the controller. """
        if self.controller:
            self.controller.delete_object(self)
            self.controller = None
            # todo - should we post events on the controller instead?
            self.fire(ObjectDeletedEvent(self))


class ContainedObject(ControlboxObject):
    """ An object in a container. Contained objects have a slot that is the id relative to the container
        the object is in. The full id_chain is the container's id plus the object's slot in the container.
    """

    def __init__(self, controller: "TypedControlbox", container: ContainerTraits, slot: int):
        # todo - push the profile up to the root container and store controller
        # in that.
        """
            :param controller:  The controller containing this object.
            :param container:   The container hosting this object. Will be None if this is the root container.
            :param slot:        The slot in the container this object is stored at
            """
        super().__init__(controller)
        self.container = container
        self.slot = slot

    @property
    def id_chain(self):
        """ Retrieves the id_chain for this object as a iterable of integers.
        :return: The id-chain for this object
        :rtype:
        """
        return self.container.id_chain_for(self.slot)

    def parent(self):
        return self.container

    def root_container(self):
        return self.container.root_container()


class UserObject(InstantiableObject, ContainedObject):
    """ An object that is instantiated in a profile and managed by a container.
        (In contrast to system objects which are automatically instantiated by the system.)
    """
    def __init__(self, controller: Controlbox, container: ContainerTraits, slot: int):
        super(InstantiableObject, self).__init__(controller, container, slot)
        super(ContainedObject, self).__init__(controller)


class SystemObject(ContainedObject):
    def __init__(self, controller: Controlbox, container: ContainerTraits, slot: int):
        super(ContainedObject, self).__init__(controller)


class Container(ContainedObject, ContainerTraits):
    """ A generic non-root container. Being a non-root container, the container is always contained within a parent
    container. """

    def __init__(self, controller, container, slot):
        super().__init__(controller, container, slot)
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
    def add(self, obj: ContainedObject):
        raise NotImplementedError()

    def remove(self, obj: ContainedObject):
        raise NotImplementedError()

    def notify_added(self, obj: ContainedObject):
        """ Notification from the controller that this object will be added to this container. This is called
            after the object has been added in the controller. """

    def notify_removed(self, obj: ContainedObject):
        """ Notification from the controller that this object will be removed from this container. This is called
            prior to removing the object from the container in the controller and clearing the container member in the
            contained object. """


class RootContainerTraits(ContainerTraits):
    """ Describes the traits of a root container implementation. """
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


class SystemProfile(BaseControlboxObject):
    """ represents a system profile - storage for a root container and contained objects. """

    def __init__(self, controller: Controlbox, profile_id):
        super().__init__(controller)
        self.profile_id = profile_id
        self._objects = dict()  # map of object id to object. These objects are proxy objects to
        # objects in the controller
        # todo - should we store all objects here or store them in each container?

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
        self._add(ControllerLoopContainer(self))
        for ref in self.controller.list_objects(self):
            self.controller._instantiate_stub(
                ref.obj_class, ref.container, ref.id_chain, ref.args)

    def _add(self, obj: ControlboxObject):
        self._objects[tuple(obj.id_chain)] = obj

    def _remove(self, id_chain):
        self._objects.pop(id_chain, None)


class RootContainer(RootContainerTraits, OpenContainerTraits, ControlboxObject):
    """ A root container is the top-level container in a profile."""
    # todo - add the profile that this object is contained in
    def __init__(self, profile: SystemProfile):
        super().__init__(profile.controller)
        self.profile = profile


class SystemRootContainer(RootContainerTraits, ControlboxObject):
    """ Represents the container for system objects. """

    def __init__(self, controller):
        super().__init__(controller)


class Decoder:
    @abstractmethod
    def encoded_len(self):
        """ The number of byte expected for in the encoding of this value.  """
        raise NotImplementedError

    @abstractmethod
    def decode(self, buf):
        raise NotImplementedError

    # todo - why no decode_mask?
    # with the current use case, this would only be used to decode
    # the encoded command response back into an object, which isn't currently
    # needed.


class ValueDecoder(Decoder):
    """ Interface expected of decoders. """

    def decode(self, buf):
        return self._decode(buf)

    @abstractmethod
    def _decode(self, buf):
        """ Decodes a buffer into the value for this object. """
        raise NotImplementedError


class ForwardingDecoder(Decoder):
    """ Decoder implementation that forwards to another decoder instance. This allows the encoding implementation to be
    changed at runtime. """
    decoder = None

    def __init__(self, decoder=None):
        if decoder:
            self.decoder = decoder

    def encoded_len(self):
        return self.decoder.encoded_len()

    def decode(self, buf):
        return self.decoder.decode(buf)


def make_default_mask(buf):
    """
    >>> make_default_mask(bytearray(3))
    bytearray(b'\xff\xff\xff')
    """
    for x in range(len(buf)):
        buf[x] = 0xFF
    return buf


class Encoder:
    @abstractmethod
    def encoded_len(self):
        """ The number of byte expected for the encoding of this value.  """
        raise NotImplementedError

    @abstractmethod
    def encode(self, value):
        raise NotImplementedError

    @abstractmethod
    def encode_masked(self, value):
        raise NotImplementedError


class ValueEncoder(Encoder):
    """ Interface expected of encoders. """

    def encode(self, value):
        """ Encodes an object into a buffer. """
        buf = bytearray(self.encoded_len())
        return bytes(self._encode(value, buf))

    def encode_masked(self, value):
        """ Encodes a tuple representing a value and a mask into a a pair of byte buffers encoding the value and the
            write mask. This is used to provide an encoding of a smaller part of the value.
        """
        buf, mask = self._encode_mask(value, bytearray(
            self.encoded_len()), bytearray(self.encoded_len()))
        return bytes(buf), bytes(mask)

    def _encode_mask(self, value, buf_value, buf_mask):
        """
        :param value: the value and mask to encode as a sequence
        :param buf_value: The buffer to encode the value into
        :param buf_mask: The buffer to encode the mask into
        :return: a tuple of the encoded value and encoded mask.
        """
        self._encode(value[0], buf_value)
        self._encode(value[1], buf_mask)
        return buf_value, buf_mask

    def _encode(self, value, buf):
        raise NotImplementedError()

    @staticmethod
    def mask_none(cls, value):
        return value or 0, -1 if value is not None else 0


class ForwardingEncoder(Encoder):
    """ Encoder implementation that forwards to another encoder instance. This allows the encoding implementation to
    be changed at runtime. """
    encoder = None

    def __init__(self, encoder: Encoder=None):
        if encoder:
            self.encoder = encoder

    def encoded_len(self):
        return self.encoder.encoded_len()

    def encode(self, value):
        return self.encoder.encode(value)

    def encode_masked(self, value):
        return self.encoder.encode_masked(value)


class Codec(Encoder, Decoder):
    pass


class CompositeCodec(Codec):
    """
    Creates a codec from separate encoder/decoder instances
    """
    def __init__(self, encoder: Encoder, decoder: Decoder):
        self.encoder = encoder
        self.decoder = decoder

    def encoded_len(self):
        return self.encoder.encoded_len()

    def decode(self, buf):
        return self.decoder.decode(buf)

    def encode(self, value):
        raise self.encoder.encode(value)


class ValueChangedEvent(ObjectEvent):

    def __init__(self, source, before, after):
        super().__init__(source, (before, after))

    def before(self):
        return self.data[0]

    def after(self):
        return self.data[1]


class ValueObject(ContainedObject):
    """
    Describes an object in the container with an associated value
    The value is typically a decoded/application-centric representation of the data sent over the wire
    rather than raw data bytes.
    """
    def __init__(self, controller, container, slot):
        super().__init__(controller, container, slot)
        self.previous = None

    def _update_value(self, new_value):
        """
        Updates the value associated with this object
        If the value has changed, a ValueChangedEvent is fired.
        """
        p = self.previous
        self.previous = new_value
        if p != new_value:
            self.fire(ValueChangedEvent(self, p, new_value))
        return new_value


class ReadableObject(ValueObject, ValueDecoder):
    """
    A readable object knows how to
    """

    def read(self):
        return self.controller.read_value(self)


class WritableObject(ValueObject, ValueDecoder, ValueEncoder):

    def write(self, value):
        fn = self.controller.write_masked_value if self.is_masked_write(
            value) else self.controller.write_value
        return fn(self, value)

    def is_masked_write(self, value):
        return False


class MaskedWritableObject(WritableObject):

    def is_masked_write(self, value):
        return True


class UnsignedLongDecoder(ValueDecoder):

    def _decode(self, buf):
        return ((((buf[3] * 256) + buf[2]) * 256) + buf[1]) * 256 + buf[0]

    def encoded_len(self):
        return 2


class UnsignedShortDecoder(ValueDecoder):

    def _decode(self, buf):
        return ((buf[1]) * 256) + buf[0]

    def encoded_len(self):
        return 2


class ShortEncoder(ValueEncoder):

    def _encode(self, value, buf):
        if value < 0:
            value += 64 * 1024
        buf[1] = unsigned_byte(int(value / 256))
        buf[0] = value % 256
        return buf

    def encoded_len(self):
        return 2


class ShortDecoder(ValueDecoder):

    def _decode(self, buf):
        return (signed_byte(buf[1]) * 256) + buf[0]

    def encoded_len(self):
        return 2


class ShortCodec(CompositeCodec):
    def __init__(self):
        super().__init__(ShortEncoder(), ShortDecoder())


class ByteDecoder(ValueDecoder):

    def _decode(self, buf):
        return signed_byte(buf[0])

    def encoded_len(self):
        return 1


class ByteEncoder(ValueEncoder):

    def _encode(self, value, buf):
        buf[0] = unsigned_byte(value)
        return buf

    def encoded_len(self):
        return 1


class ByteCodec(CompositeCodec):
    def __init__(self):
        super().__init__(ByteEncoder(), ByteDecoder())


class LongEncoder(ValueEncoder):

    def _encode(self, value, buf):
        if value < 0:
            value += 1 << 32
        value = int(value)
        for x in range(0, 4):
            buf[x] = value % 256
            value = int(value / 256)
        return buf

    def encoded_len(self):
        return 4


class UnsignedLongEncoder(LongEncoder):
    pass


class LongDecoder(ValueDecoder):

    def _decode(self, buf):
        return longDecode(buf)

    def encoded_len(self):
        return 4


class LongCodec(CompositeCodec):
    def __init__(self):
        super().__init__(LongEncoder(), LongDecoder())


class UnsignedLongCodec(CompositeCodec):
    def __init__(self):
        super().__init__(UnsignedLongEncoder(), UnsignedLongDecoder())


class BufferDecoder(ValueDecoder):

    def decode(self, buf):
        return buf


class BufferEncoder(ValueEncoder):

    def encode(self, value):
        return bytes(value)

    def encode_masked(self, value):
        return bytes(value[0]), bytes(value[1])


class ReadWriteBaseObject(ReadableObject, WritableObject):
    pass


class ReadWriteUserObject(ReadWriteBaseObject, UserObject):
    pass


class ReadWriteSystemObject(ReadWriteBaseObject):
    pass


def mask(value, byte_count):
    """
    >>> mask(None, 2)
    0
    >>> mask(0, 2)
    65535
    >>> mask(0, 4)
    4294967295
    """
    if value is None:
        return 0
    r = 0
    for x in range(0, byte_count):
        r = r << 8 | 0xFF
    return r


class ObjectDefinition:
    """ The definition codec for an object. Converts between the byte array passed to the protocol and higher-level
        argument types used in python code. """

    @classmethod
    @abstractmethod
    def decode_definition(cls, data_block, controller):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def encode_definition(cls, arg):
        raise NotImplementedError


class EmptyDefinition(ObjectDefinition):

    @classmethod
    def decode_definition(cls, data_block):
        raise ValueError("object does not require a definition block")

    @classmethod
    def encode_definition(cls, arg):
        raise ValueError("object does not require a definition block")


class AnyBlockDefinition(ObjectDefinition):

    @classmethod
    def decode_definition(cls, data_block):
        return data_block

    @classmethod
    def encode_definition(cls, arg):
        return arg or b''


class NonEmptyBlockDefinition(ObjectDefinition):

    @classmethod
    def encode_definition(cls, arg):
        if not arg:
            raise ValueError("requires a non-zero length block")
        return arg

    @classmethod
    def decode_definition(cls, data_block, controller):
        return cls.encode_definition(data_block)


class EncoderDecoderDefinition(ObjectDefinition):
    """ An definition codec that delegates to a class-defined encoder and decoder. """
    encoder = None
    decoder = None

    @classmethod
    def encode_definition(cls, arg):
        return cls.encoder.encode(arg)

    @classmethod
    def decode_definition(cls, data_block, controller):
        return cls.decoder.decode(data_block)


class ReadWriteValue(ReadWriteBaseObject):

    @property
    def value(self):
        return self.read()

    @value.setter
    def value(self, v):
        self.write(v)


class DynamicContainer(EmptyDefinition, UserObject, OpenContainerTraits, Container):
    type_id = 4
    # todo - the application defines the type IDs, not the system, so
    # remove this.


class ControllerLoopState(CommonEqualityMixin):

    def __init__(self, enabled=None, log_period=None, period=None):
        if log_period is not None and (log_period < 0 or log_period > 7):
            raise ValueError("invalid log period " + str(log_period))
        if period is not None and (period < 0 or period > 65535):
            raise ValueError("invalid period " + period)
        self._enabled = enabled
        # range from 0..7. The log period is 0 if zero, else 2^(n-1)
        self._log_period = log_period
        self._period = period

    @staticmethod
    def log_periods():
        return {x: 1 << (x - 1) if x else x for x in range(8)}

    @staticmethod
    def encoded_len():
        return 3

    def decode(self, buf):
        self._enabled = (buf[0] & 0x08) != 0
        self._log_period = buf[0] & 0x07
        self._period = ShortDecoder().decode(buf[1:3])
        return self

    def encode_mask(self, buf_value, buf_mask):
        flags = 0
        flags_mask = 0
        if self._log_period is not None:
            flags |= (self._log_period & 0x7)
            flags_mask |= 7
        if self._enabled is not None:
            flags |= 8 if self._enabled else 0
            flags_mask |= 8
        buf_value[0], buf_mask[0] = flags, flags_mask
        buf_value[1:3] = ShortEncoder().encode(self._period or 0)
        buf_mask[1:3] = ShortEncoder().encode(mask(self._period, 2))
        return bytes(buf_value), bytes(buf_mask)


class ControllerLoop(MaskedWritableObject, ReadWriteUserObject, ReadWriteValue):
    """ Represents a control loop in the ControllerLoopContainer. """

    def encoded_len(self):
        return ControllerLoopState.encoded_len()

    def _encode_mask(self, value: ControllerLoopState, buf_value, buf_mask):
        value.encode_mask(buf_value, buf_mask)
        return buf_value, buf_mask

    def _decode(self, buf):
        return ControllerLoopState().decode(buf)


class ControllerLoopContainer(RootContainer):
    """
    Describves a controller loop container.
    """
    def __init__(self, profile):
        super().__init__(profile)
        self.config_container = DynamicContainer(self.controller, self, 0)
        self.configs = dict()

    def configuration_for(self, o: ContainedObject) -> ControllerLoop:
        if o.container != self:
            raise ValueError()
        return self.configurations[o.slot]

    @property
    def configurations(self):
        """
        :return: a dictionary mapping item slots to the ControllerLoop object that controls that loop.
        """
        return self.configs

    def notify_added(self, obj: ContainedObject):
        """ When an object is added, the controller also adds a config object to the config container. """
        self.configs[obj.slot] = ControllerLoop(
            self.controller, self.config_container, obj.slot)

    def notify_removed(self, obj: ContainedObject):
        del self.configs[obj.slot]


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


def is_value_object(obj):
    return obj is not None and hasattr(obj, 'decode') and hasattr(obj, '_update_value')


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


class TypedControlbox(Controlbox):
    """ Provides a stateful object API to controlbox. The controller and proxy objects provides
       the application view of the external controller.
    :param: connector  The connector that provides the transport stream to the remote controller
    :param: object_types  A mapper between object classes and type ids
    """
    def __init__(self, connector, object_types: ObjectTypeMapper):
        """
        :param connector:       The connector that provides the v0.3.x protocol over a conduit.
        :param object_types:    The factory describing the object types available in the controller.
        """
        super().__init__(connector)
        self._sysroot = SystemRootContainer(self)
        # todo - populate system root with system objects
        self._object_types = object_types
        self._profiles = dict()
        self._current_profile = None
        self.log_events = EventSource()

    @property
    def types(self)->ObjectTypeMapper:
        return self._object_types

    def handle_async_log_values(self, log_info):
        """ Handles the asynchronous logging values from each object.
            This method looks up the corresponding object in the hierarchy and uses that to decode the log data,
            converting it into a value. The value is then applied to the object.
        :param values: The log_info (id_chain, log_values)
        """
        p = self._current_profile
        if p is not None:
            time, id_chain, values = log_info
            time = UnsignedLongDecoder().decode(time)
            object_values = []
            for suffix_chain, data in values:
                full_chain = id_chain + suffix_chain
                obj = p.object_at(full_chain, True)
                if is_value_object(obj):
                    new_value = obj.decode(data)
                    object_values.append((obj, new_value))
            self._update_objects(time, object_values)
            self.log_events.fire((time, object_values))

    def _update_objects(self, time, object_values):
        for obj, value in object_values:
            obj._update_value(value)

    def initialize(self, load_profile=True):
        self._profiles = dict()
        self._current_profile = None
        if load_profile:
            self._set_current_profile(self.active_and_available_profiles()[0])
        self.protocol.async_log_handlers += lambda x: self.handle_async_log_values(x.value)

    def full_erase(self):
        """
        Erases all profiles in the device.
        """
        available = self.active_and_available_profiles()
        for p in available[1]:
            self.delete_profile(p)

    def read_value(self, obj: ReadableObject):
        fn = self.protocol.read_system_value if self.is_system_object(
            obj) else self.protocol.read_value
        data = self._fetch_data_block(fn, obj.id_chain, obj.type, obj.encoded_len())
        return obj.decode(data)

    def write_value(self, obj: WritableObject, value):
        fn = self.protocol.write_system_value if self.is_system_object(
            obj) else self.protocol.write_value
        return self._write_value(obj, value, fn)

    def write_masked_value(self, obj: WritableObject, value):
        fn = self.protocol.write_system_masked_value if self.is_system_object(
            obj) else self.protocol.write_masked_value
        return self._write_masked_value(obj, value, fn)

    def delete_object(self, obj: ContainedObject):
        self._delete_object_at(obj.id_chain)

    def next_slot(self, container) -> int:
        return self._handle_error(self._connector.protocol.next_slot, container.id_chain)

    def create_profile(self):
        profile_id = self._handle_error(
            self._connector.protocol.create_profile)
        return self.profile_for(profile_id)

    def delete_profile(self, p: SystemProfile):
        self._handle_error(self.protocol.delete_profile, p.profile_id)
        if self._current_profile == p:
            self._set_current_profile(None)
        # profile may have already been deleted
        self._profiles.pop(p.profile_id, None)

    def activate_profile(self, p: SystemProfile or None):
        """ activates the given profile. if p is None, the current profile is deactivated. """
        self._handle_error(self.protocol.activate_profile, SystemProfile.id_for(p))
        self._set_current_profile(p)

    def active_and_available_profiles(self):
        """
            returns a tuple - the first element is the active profile, or None if no profile is active.
            the second element is a sequence of profiles.
        """
        future = self.protocol.list_profiles()
        data = TypedControlbox.result_from(future)
        activate = self.profile_for(data[0], True)
        available = tuple([self.profile_for(x) for x in data[1]])
        return activate, available

    def is_active_profile(self, p: SystemProfile):
        active = self.active_and_available_profiles()[0]
        return False if not active else active.profile_id == p.profile_id

    def list_objects(self, p: SystemProfile):
        future = self.protocol.list_profile(p.profile_id)
        data = TypedControlbox.result_from(future)
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
        encoded = obj.encode(value)
        # todo - retrieve object type
        # also use a code as used in the bridge code to separate encoding/decoding from the objects themselves.
        data = self._fetch_data_block(fn, obj.id_chain, 0, encoded)
        if data != encoded:
            raise FailedOperationError("could not write value")
        new_value = obj.decode(data)
        obj._update_value(new_value)
        return value

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

    def create_object(self, obj_class, args=None, container=None, slot=None) -> InstantiableObject:
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
        dec = args and obj_class._decode_definition(data, controller=self)
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

    @staticmethod
    def _handle_error(fn, *args, allow_fail=False):
        future = fn(*args)
        error = TypedControlbox.result_from(future)
        if error < 0 and not allow_fail:
            raise FailedOperationError("errorcode %d" % error)
        return error

    @staticmethod
    def _fetch_data_block(fn, *args):
        """
        fetches the future using the given function and then retrieves
        the associated data block, which provides the response for the
        associated command.
        """
        future = fn(*args)
        data = TypedControlbox.result_from(future)
        if not data:
            raise FailedOperationError("no data")
        return data

    @property
    def root_container(self):
        p = self._check_current_profile()
        return p.root

    @staticmethod
    def result_from(future: FutureResponse):
        # todo - on timeout, unregister the future from the async protocol handler to avoid
        # a memory leak
        return None if future is None else future.value(timeout)

    def profile_for(self, profile_id, may_be_negative=False):
        if profile_id < 0:
            if may_be_negative:
                return None
            raise ValueError("negative profile id")
        return fetch_dict(self._profiles, profile_id, lambda x: SystemProfile(self, x))

    def container_at(self, id_chain):
        o = self.object_at(id_chain)
        return o

    def object_at(self, id_chain, optional=False):
        p = self._check_current_profile()
        return p.object_at(id_chain, optional)

    @staticmethod
    def container_chain_and_id(id_chain):
        """
        >>> TypedControlbox.container_chain_and_id(b'\x50\x51\x52')
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
        return ObjectReference(self, container, slot, cls, args)

    def ref(self, obj_class, args, id_chain):
        """ helper method to create an object reference from the class, args and id_chain. """
        container, slot = self._container_slot_from_id_chain(id_chain)
        return ObjectReference(self, container, slot, obj_class, args)

    def _check_current_profile(self) -> SystemProfile:
        if not self._current_profile:
            raise FailedOperationError("no current profile")
        return self._current_profile

    # noinspection PyProtectedMember
    def _set_current_profile(self, profile: SystemProfile):
        if self._current_profile:
            self._current_profile._deactivate()
        self._current_profile = None
        if profile:
            self._current_profile = profile
            profile._activate()

    @property
    def current_profile(self):
        return self._current_profile
