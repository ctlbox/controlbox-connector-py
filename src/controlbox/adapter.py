"""
The protocol in terms of application values that are not bound to the controller.
Maps between application state and the encoded binary representation via a set of codecs.

Listens to events from the connector protocol for object updates,
and fires events to registered listeners. The raw event data
is decoded to application state.

"""
from abc import ABCMeta, abstractmethod

from controlbox.codecs import ConnectorCodec
from controlbox.protocol.async import FutureResponse, FutureValue
from controlbox.protocol.controlbox import ActivateProfileResponseDecoder, CommandResponse, Commands, Controlbox, \
    CreateObjectResponseDecoder, CreateProfileResponseDecoder, DeleteObjectResponseDecoder, \
    DeleteProfileResponseDecoder, ListProfileResponseDecoder, ListProfilesResponseDecoder, LogValuesResponseDecoder, \
    ReadSystemValueResponseDecoder, ReadValueResponseDecoder, ResetResponseDecoder, WriteMaskedValueResponseDecoder, \
    WriteSystemValueResponseDecoder, WriteValueResponseDecoder
from controlbox.support.events import EventSource
from controlbox.support.mixins import StringerMixin


class ConnectorListener:
    """
    A listener interface that receives notifications of information from the controller.
    The object state is converted from binary format into an object representation.
    See Codec. Presently unused.
    """

    def object_created(self, idchain, type, state):
        """
        notifies that an object was created.
        :param: idchain The location of the object
        :param: type the type of the object (an integer)
        :param: state the construction state of the object.
        """

    # todo - object definition?
    # def object_definition(self, idchain, type, config):
    #     """
    #     notifies about the definition of an object
    #     :param idchain:
    #     :param type:
    #     :param config:
    #     :return:
    #     """

    def object_deleted(self, idchain):
        """
        notifies that an object was deleted.
        """

    # def object_states(self, updates):
    #     """
    #     notifies that the current state of a number of objects. (The state description is complete.)
    #     """
    #     for update in updates:
    #         self.object_state(update.idchain, update.state)
    # not needed - left in as a reminder to reconsider and remove when requirements have stabilized.

    def object_state(self, idchain, state):
        """
        notifies that the current state of an object. This is in response to a
        read request.
        """

    def object_update(self, idchain, state):
        """
        notifies the state of the object response to
        an update (object write). Note that internal updates to state within the controller do not
        generate an update event. These state changes are made available via object_state events.
        # todo - perhaps in the python layer we do away with the user/system split in events and read/write
        and instead include the profile?
        """

    def system_object_update(self, idchain, state):
        """
        notifies that the state of the system object has changed in response to an
        external update.
        """

    def system_object_state(self, idchain, state):
        """
        notifies the state of a system object.
        """

    def profile_created(self, profile_id):
        """
        notifies that a profile was created.
        """

    def profile_deleted(self, profile_id):
        """
        notifies that profile was deleted.
        """

    def profile_activated(self, profile_id):
        """
        notifies that a profile has been activated.
        """

    def profiles_available(self, ids, active):
        """
        notifies the profiles available and which one is active.
        """

    def device_reset(self):
        """
        notifies that the device will reset.
        """


class ControlboxApplicationEvent(StringerMixin, metaclass=ABCMeta):
    """
    The base event class for all connector events.
    """
    def __init__(self, controlbox):
        self.controlbox = controlbox

    @abstractmethod
    def apply(self, visitor: 'ControlboxEventVisitor'):
        pass


class ObjectEvent(ControlboxApplicationEvent):
    """
    Describes an event that pertains to an object in the controller.
    """
    def __init__(self, controlbox, system, idchain):
        super().__init__(controlbox)
        self.idchain = idchain
        self.system = system


class ObjectStateEvent(ObjectEvent):
    """
    Describes the state of a user or system object.
    """
    def __init__(self, controlbox, system, idchain, type, state):
        super().__init__(controlbox, system, idchain)
        self.type = type
        self.state = state

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.system_object_state(self) if self.system else visitor.object_state(self)


class ProfileEvent(ControlboxApplicationEvent):
    def __init__(self, controlbox, profile_id):
        super().__init__(controlbox)
        self.profile_id = profile_id


class ObjectCreatedEvent(ObjectStateEvent):
    """
    Event notifying that an object was created. If it is a system object
    the system itself was responsible for creating it. If it is a user object
    it may have been created by the system or the user.
    """
    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.object_created(self)


class ObjectDeletedEvent(ObjectStateEvent):
    def __init__(self, controlbox, system, idchain, type, state=None):
        super().__init__(controlbox, system, idchain, type, state)

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.object_deleted(self)


class ObjectUpdatedEvent(ObjectStateEvent):
    """
    Describes the requested update and the resulting state of the object.
    The object itself may veto state changes, hence the requested state is not always the
    same as the actual state.
    """

    def __init__(self, controlbox, system, idchain, type, state, requested_state=None):
        super().__init__(controlbox, system, idchain, type, state)
        self.requested_state = requested_state

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.object_updated(self)


class ProfileListedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectDefinition instance (id_chain, type, config).
    """
    # todo - since this will also list the contents of the system container
    # a name that applies to system and user cases would fit better
    # ObjectDefinitionsEvent?
    def __init__(self, controlbox, profile_id, definitions):
        super().__init__(controlbox, profile_id)
        self.definitions = definitions

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profile_listed(self)


class ProfileCreatedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectState instance.
    """

    def __init__(self, controlbox, profile_id):
        super().__init__(controlbox, profile_id)

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profile_created(self)


class ProfileDeletedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectState instance.
    """

    def __init__(self, controlbox, profile_id):
        super().__init__(controlbox, profile_id)

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profile_deleted(self)


class ProfileActivatedEvent(ProfileEvent):
    """
    Notification that a profile has become active.
    todo - should also notify which profile became inactive?
    """
    def __init__(self, controlbox, profile_id):
        super().__init__(controlbox, profile_id)

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profile_activated(self)


class ControllerResetEvent(ControlboxApplicationEvent):
    # todo - profile constants for the flags
    def __init__(self, controlbox, flags):
        super().__init__(controlbox)
        self.flags = flags

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.controller_reset(self)


class ContainerObjectsLoggedEvent(ObjectEvent):
    def __init__(self, controlbox, system, id_chain, values):
        super().__init__(controlbox, system, id_chain)
        self.values = values

    def apply(self, visitor: 'ControlboxEventVisitor'):
        # todo - separate methods for system logs?
        return visitor.objects_logged(self)


class ProfilesListedEvent(ProfileEvent):
    def __init__(self, controlbox, active_profile_id, available_profile_ids):
        super().__init__(controlbox, active_profile_id)
        self.available_profile_ids = available_profile_ids

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profiles_listed(self)


class CommandFailedEvent(ControlboxApplicationEvent):
    """
    Indicates that a command failed.
    :param controlbox: The controlbox instance the command was invoked on
    :param command: a tuple (method, args) where args is also a tuple of args passed to the method
    :param reason:
    :param event The event that would have been fired if the operation had succeeded.
    Note that the event itself may implicitly signal an error condition. For example,
    create profile listing a created profile ID of -1.

    """
    def __init__(self, controlbox: 'ControlboxApplicationAdapter', command, reason, event):
        super().__init__(controlbox)
        self.command = command
        self.reason = reason
        self.event = event

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.command_failed(self)

    def as_exception(self):
        """converts this event to an exception"""
        exception = FailedOperationError()
        exception.event = self
        return exception


class ControlboxEventVisitor(metaclass=ABCMeta):  # pragma no cover - trivial
    """
    A visitor to handle the various types of events.
    """
    @abstractmethod
    def object_created(self, event: ObjectCreatedEvent):
        """
        notifies that an object was created.
        """

    @abstractmethod
    def object_deleted(self, event: ObjectDeletedEvent):
        """
        notifies that an object was deleted.
        """

    @abstractmethod
    def object_state(self, event: ObjectStateEvent):
        """
        notifies that the current state of an object.
        """

    @abstractmethod
    def object_updated(self, event: ObjectUpdatedEvent):
        """
        notifies that the state of the object has changed in response to
        an update. Note that internal updates to state within the controller do not
        generate an update event. These state changes are made available via state events.
        """

    @abstractmethod
    def system_object_update(self, event: ObjectUpdatedEvent):
        """
        notifies that the state of the system object has changed in response to an
        external update.
        """

    @abstractmethod
    def system_object_state(self, event: ObjectStateEvent):
        """
        notifies the state of a system object.
        """

    @abstractmethod
    def objects_logged(self, event: ContainerObjectsLoggedEvent):
        """
        notifies the state of all objects in a container.
        """

    @abstractmethod
    def profile_created(self, event: ProfileCreatedEvent):
        """
        notifies that a profile was created.
        """

    @abstractmethod
    def profile_deleted(self, event: ProfileDeletedEvent):
        """
        notifies that profile was deleted.
        """

    @abstractmethod
    def profile_listed(self, event: ProfileListedEvent):
        """ notifies the definition of objects in a given profile. """

    @abstractmethod
    def profile_activated(self, event: ProfileActivatedEvent):
        """
        notifies that a profile has been activated.
        """

    @abstractmethod
    def profiles_listed(self, event: ProfilesListedEvent):
        """
        notifies the profiles available and which one is active.
        """

    @abstractmethod
    def controller_reset(self, event: ControllerResetEvent):
        """
        notifies that the device will reset.
        """

    @abstractmethod
    def command_failed(self, event: CommandFailedEvent):
        """
        notifies that a command failed in some way.
        The command that failed is available in the event.
        """


class ControlboxEventVisitorSupport(ControlboxEventVisitor):  # pragma no cover - trivial

    def system_object_update(self, event: ObjectUpdatedEvent):
        pass

    def object_state(self, event: ObjectStateEvent):
        pass

    def profiles_listed(self, event: ProfilesListedEvent):
        pass

    def profile_deleted(self, event: ProfileDeletedEvent):
        pass

    def profile_activated(self, event: ProfileActivatedEvent):
        pass

    def command_failed(self, event: CommandFailedEvent):
        pass

    def system_object_state(self, event: ObjectStateEvent):
        pass

    def controller_reset(self, event: ControllerResetEvent):
        pass

    def profile_created(self, event: ProfileCreatedEvent):
        pass

    def objects_logged(self, event: ContainerObjectsLoggedEvent):
        pass

    def profile_listed(self, event: ProfileListedEvent):
        pass

    def object_updated(self, event: ObjectUpdatedEvent):
        pass

    def object_deleted(self, event: ObjectDeletedEvent):
        pass

    def object_created(self, event: ObjectCreatedEvent):
        pass


class ObjectState:
    """
    Identifies an object in the container
     todo - system objects also have state
    """
    def __init__(self, system, idchain, type, state):
        """
        :param system   True if this is an object in the system space.
            False if the object is in the user space (profile not specified here
            assumed is available in the context.)
        :param idchain  The identifier for the object
        """
        self.idchain = idchain
        self.type = type
        self.state = state
        self.system = system


class ObjectDefinition(ObjectState):
    """
    Describes the construction state of an object.
    """


class ControlboxEventFactory:
    """
    Responsible for creating an event from a command response. The request
    and command_id are provided for context.
    :param request the decoded request.
    """
    @abstractmethod
    def __call__(self, connector: "ControlboxApplicationAdapter", response, request, command_id, command):
        raise NotImplementedError()


class ReadValueEventFactory(ControlboxEventFactory):
    """
    Constructs a ObjectUpdatedEvent from a read value command.
    The decoder is given for reference so you can see what the result contents are
    """
    decoder = ReadValueResponseDecoder
    system = False

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data_length = request
        status, buffer = response

        value = connector._decode_state(status, buffer) if len(buffer) else None
        event = ObjectUpdatedEvent(connector, self.system, id_chain, type, value)
        if value is None:
            event = CommandFailedEvent(connector, command, status, event)
        return event


class WriteValueEventFactory(ControlboxEventFactory):
    decoder = WriteValueResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data = request
        status, buffer = response

        requested_value = connector._decode_state(status, buffer) if status > 0 else None
        set_value = connector._decode_state(type, buffer) if len(buffer) else None
        event = ObjectUpdatedEvent(connector, False, id_chain, type, set_value, requested_value)
        if set_value is None:
            event = CommandFailedEvent(connector, command, status, event)
        return event


class CreateObjectEventFactory(ControlboxEventFactory):
    decoder = CreateObjectResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data = request
        status_code, = response
        value = command[1][2]
        event = ObjectCreatedEvent(connector, id_chain, type, value)
        if status_code < 0:
            event = CommandFailedEvent(connector, command, status_code, event)
        return event


class DeleteObjectEventFactory(ControlboxEventFactory):
    decoder = DeleteObjectResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type = request
        code, = response
        event = ObjectDeletedEvent(connector, id_chain, type)
        if code < 0:
            event = CommandFailedEvent(connector, command, response, event)
        return event


class ListProfileEventFactory(ControlboxEventFactory):
    decoder = ListProfileResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, definitions = response
        system = profile_id == -1
        object_defs = [connector._decode_definition(system, x) for x in definitions]
        event = ProfileListedEvent(connector, profile_id, object_defs)
        if status < 0:
            event = CommandFailedEvent(connector, command, status, event)
        return event


class CreateProfileEventFactory(ControlboxEventFactory):
    decoder = CreateProfileResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = response
        event = ProfileCreatedEvent(connector, profile_id)
        # todo factor valid/invalid id logic for profiles to a central method
        if profile_id < 0:
            event = CommandFailedEvent(connector, command, response, event)
        return event


class DeleteProfileEventFactory(ControlboxEventFactory):
    decoder = DeleteProfileResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, = response
        event = ProfileDeletedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command, response, event)
        return event


class ActivateProfileEventFactory(ControlboxEventFactory):
    decoder = ActivateProfileResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, = response
        event = ProfileActivatedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command, response, event)
        return event


class ResetEventFactory(ControlboxEventFactory):
    decoder = ResetResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        flags, = request
        status, = response
        event = ControllerResetEvent(connector, flags, status)
        if status < 0:
            event = CommandFailedEvent(connector, command, response, event)
        return event


class NoOpEventFactory(ControlboxEventFactory):
    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        pass


class LogValuesEventFactory(ControlboxEventFactory):
    decoder = LogValuesResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        flags, id_chain = request
        # todo - complete parsing response
        return ContainerObjectsLoggedEvent(connector, flags, id_chain)


class ListProfilesEventFactory(ControlboxEventFactory):
    decoder = ListProfilesResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        active_profile, profile_ids = response
        return ProfilesListedEvent(connector, active_profile, profile_ids)


class ReadSystemValueEventFactory(ReadValueEventFactory):
    decoder = ReadSystemValueResponseDecoder
    system = True


class WriteSystemValueEventFactory(ControlboxEventFactory):
    decoder = WriteSystemValueResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, to_write = request
        buffer, = response
        requested_value = connector._decode_state(type, buffer)
        set_value = connector._decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, True, id_chain, type, requested_value, set_value)


class WriteMaskedValueEventFactory(ControlboxEventFactory):
    decoder = WriteMaskedValueResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, _ = request
        buffer, = response
        set_value = connector._decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, False, id_chain, type, set_value)


class WriteSystemMaskedValueEventFactory(ControlboxEventFactory):
    decoder = WriteMaskedValueResponseDecoder

    def __call__(self, connector: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, _ = request
        buffer, = response
        set_value = connector._decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, True, id_chain, type, set_value)


class AsyncLogValuesEventFactory(LogValuesEventFactory):
    pass


class FailedOperationError(Exception):
    """The requested controlbox operation could not be performed."""


class ProfileNotActiveError(FailedOperationError):
    """raised when an operation that requires an active profile is attempted, and no profile is currently active."""


class ControlboxApplicationAdapter:
    """
    Higher level, stateless interface to the controlbox protocol.
    Works in terms of python objects rather than protocol buffers.
    This is a "lightweight" version of the api in controller.py which attempts to build an
    object tree with distinct classes for each class type, and maintaining instances in a hiearchy
    that proxy the corresponding remote instances in the controller.
    This class does none of that, and provides an applciation-level view of the
    controlbox functionality. For example, setting an object state is done by providing the state as
    an appropriate python object. This is then encoded to the on the wire format by the codec.
    """
    eventFactories = {
        # todo - a visitor pattern would help ensure all commands are handled
        Commands.read_value: ReadValueEventFactory(),
        Commands.write_value: WriteValueEventFactory(),
        Commands.create_object: CreateObjectEventFactory(),
        Commands.delete_object: DeleteObjectEventFactory(),
        Commands.list_profile: ListProfileEventFactory(),
        Commands.next_free_slot: NoOpEventFactory(),  # NextFreeSlotEventFactory,
        Commands.create_profile: CreateProfileEventFactory(),
        Commands.delete_profile: DeleteProfileEventFactory(),
        Commands.activate_profile: ActivateProfileEventFactory(),
        Commands.reset: ResetEventFactory(),
        Commands.log_values: LogValuesEventFactory(),
        Commands.next_free_slot_root: NoOpEventFactory(),
        Commands.list_profiles: ListProfilesEventFactory(),
        Commands.read_system_value: ReadSystemValueEventFactory(),
        Commands.write_system_value: WriteSystemValueEventFactory(),
        Commands.write_masked_value: WriteMaskedValueEventFactory(),
        Commands.write_system_masked_value: WriteSystemMaskedValueEventFactory(),
        Commands.async_log_values: AsyncLogValuesEventFactory()
    }

    class ResultFromEvent(ControlboxEventVisitor):
        """
        Turns an event into the corresponding command result.
        """

        def profile_created(self, event: ProfileCreatedEvent):
            return event.profile_id

        def system_object_state(self, event: ObjectStateEvent):
            return event.state

        def object_deleted(self, event: ObjectDeletedEvent):
            return None

        def object_updated(self, event: ObjectUpdatedEvent):
            return event.state

        def object_created(self, event: ObjectCreatedEvent):
            return event.idchain

        def profile_activated(self, event: ProfileActivatedEvent):
            return None

        def controller_reset(self, event: ControllerResetEvent):
            return None

        def command_failed(self, event: CommandFailedEvent):
            raise event.as_exception()

        def objects_logged(self, event: ContainerObjectsLoggedEvent):
            return event.values

        def system_object_update(self, event: ObjectUpdatedEvent):
            return event.state

        def profile_listed(self, event: ProfileListedEvent):
            return event.definitions

        def object_state(self, event: ObjectStateEvent):
            return event.state

        def profiles_listed(self, event: ProfilesListedEvent):
            return event.profile_id, event.available_profile_ids

        def profile_deleted(self, event: ProfileDeletedEvent):
            return None

    def __init__(self, controlbox: Controlbox, constructor_codec: ConnectorCodec, state_codec: ConnectorCodec):
        """
        listens for events from the given protocol, decodes them and reposts them
        as application events.
        :param: constructor_codec  Describes the initial state of an object.
        :param: state_codec An object that knows to encode/decode from application objects to
            the the wire format for any give type of object.
        """
        self.controlbox = controlbox
        self.constructor_codec = constructor_codec
        self.state_codec = state_codec
        self.listeners = EventSource()
        self.controlbox.protocol.response_handlers.add(self._response_handler)
        self.event_result_visitor = ControlboxApplicationAdapter.ResultFromEvent()

    def _response_handler(self, response: CommandResponse, futures):
        """
        The listener method for responses received from the protocol.
        :param: response The response value is the response structure, parsed to separate out the semantically
        distinct parts of the protocol. The response key is the command request data.
        """
        wrapper = None
        for f in futures:
            wrapper = f.app_wrapper
            if wrapper:
                break
        # find the command that was invoked, will be none for
        # unsolicited events
        command = wrapper.command if wrapper else None
        event = self._event_response(response, command)
        if event is not None:
            result = self._event_result(event)
            if wrapper:
                wrapper.set_result_or_exception(result)
            self.listeners.fire(event)
        else:
            if wrapper:
                wrapper.set_result(None)

    def _event_result(self, event: ControlboxApplicationEvent):
        return event.apply(self.event_result_visitor)

    def _event_response(self, response: CommandResponse, command):
        """
        Fetches the command details and passes these to a decoder, which converts them
        into an appropriate event object.
        :param response: The response from the lower level.
        :param command_args: The arguments passed to this instance
        """
        command_id = response.command_id
        request = response.parsed_request
        response = response.parsed_response
        factory = self._event_factory(command_id)  # type: ControlboxEventFactory
        return factory(self, response, request, command_id, command)

    def _event_factory(self, command_id) -> ControlboxEventFactory:
        """
        fetches the event factory for a given command.
        """
        return self.eventFactories.get(command_id)

    def _encode_state(self, type, state):
        return self.state_codec.encode(type, state)

    def _decode_state(self, type, buffer, mask=None):
        return self.state_codec.decode(type, buffer, mask)

    def _decode_config(self, type, buffer):
        return self.constructor_codec.decode(type, buffer)

    def _encode_config(self, type, config):
        return self.constructor_codec.encode(type, config)

    def _decode_definition(self, system, object_def):
        id_chain, type, data = object_def
        return ObjectState(system, id_chain, type, self._decode_config(type, data))

    def create(self, id_chain, object_type, config):
        """create a new instance on the controller with the given initial state"""
        data, mask = self._encode_config(type, config)
        if mask is not None:
            raise ValueError("object definition is not complete: %s", config)
        return self.wrap((self.create, (id_chain, object_type, config)),
                         self.controlbox.protocol.create_object(id_chain, object_type, data))

    def delete(self, id_chain, object_type=0):
        """Delete the object at the given location in the current profile."""
        return self.wrap((self.delete, (id_chain, object_type)),
                         self.controlbox.protocol.delete_object(id_chain, object_type))

    def read(self, id_chain, type=0):
        """read the state of a system object. the result is available via the returned
            future and also via the listener. """
        return self.wrap((self.read, (id_chain, type)),
                         self.controlbox.protocol.read_value(id_chain, type))

    def read_system(self, id_chain, type=0):
        """read the state of a system object. the result is available via the returned
            future and also via the listener. """
        return self.wrap((self.read_system, (id_chain, type)),
                         self.controlbox.protocol.read_system_value(id_chain, type))

    def write(self, id_chain, state, type=0):
        """Update the state of a given user object."""
        return self._write(self.write, False, id_chain, state, type)

    def write_system(self, id_chain, state, type=0):
        """Update the state of a given object."""
        return self._write(self.write_system, True, id_chain, state, type)

    def _write(self, caller, system, id_chain, state, type):
        buf, mask = self.state_codec.encode(type, state)
        fn = self.controlbox.protocol.write_system_value if system else self.controlbox.protocol.write_value
        args = (id_chain, type, buf)
        if mask is not None:
            fn = self.controlbox.protocol.write_system_masked_value \
                if system else self.controlbox.protocol.write_masked_value
            args = (id_chain, type, buf, mask)
        return self.wrap((caller, (id_chain, state, type)), fn(args))

    def profile_definitions(self, profile_id):
        """
        Retrieve an iterable of all the defined objects in the profile.
        """
        return self.wrap((self.profile_definitions, (profile_id,)), self.controlbox.protocol.list_profile(profile_id))

    def current_state(self):
        """
        Retrieve an iterator of all objects in the current profile.
        """

    def wrap(self, command: tuple, future: FutureResponse):
        """Wrap the protocol result future.
        :param command: the method and the args (as a tuple)
        :param future: the future result from the protocol decoder layer
        """
        wrapper = FutureValue()
        wrapper.source = self
        wrapper.command = command
        future.app_wrapper = wrapper
        return wrapper

    def __str__(self):
        return super().__str__()
