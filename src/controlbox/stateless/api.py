"""
The protocol in terms of application values that are not bound to the controller.
Maps between application state and the encoded binary representation via a set of codecs.

Listens to events from the connector protocol for object updates,
and fires events to registered listeners. The raw event data
is decoded to application state.

"""
from abc import ABCMeta, abstractmethod

from controlbox.protocol.async import FutureResponse, FutureValue, Request
from controlbox.protocol.controlbox import ActivateProfileResponseDecoder, CommandErrors, CommandResponse, Commands, \
    Controlbox, CreateObjectResponseDecoder, CreateProfileResponseDecoder, DeleteObjectResponseDecoder, \
    DeleteProfileResponseDecoder, ListProfileResponseDecoder, ListProfilesResponseDecoder, LogValuesResponseDecoder, \
    NextFreeSlotResponseDecoder, ReadSystemValueResponseDecoder, ReadValueResponseDecoder, ResetResponseDecoder, \
    WriteMaskedValueResponseDecoder, WriteSystemValueResponseDecoder, WriteValueResponseDecoder
from controlbox.stateless.codecs import Codec
from controlbox.support.events import EventSource
from controlbox.support.mixins import CommonEqualityMixin, StringerMixin


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


class ControlboxApplicationEvent(StringerMixin, CommonEqualityMixin, metaclass=ABCMeta):
    """
    The base event class for all connector events.
    These events describe a command and the result of executing it.
    They have many similarities to the Command pattern (and they may later be refactored as such.)
    For example, we might add an execute() method to retry the command.
    """

    def __init__(self, controlbox):
        self.controlbox = controlbox

    @abstractmethod
    def apply(self, visitor: 'ControlboxEventVisitor'):
        """
        :param visitor: the object on which to call the appropriate method that pertains to this type of event
        :return: the result of calling that method
        """


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
        return visitor.object_state(self)


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
        return visitor.objects_logged(self)


class ProfilesListedEvent(ProfileEvent):
    def __init__(self, controlbox, active_profile_id, available_profile_ids):
        super().__init__(controlbox, active_profile_id)
        self.available_profile_ids = available_profile_ids

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.profiles_listed(self)


class NextFreeSlotEvent(ObjectEvent):
    def __init__(self, controlbox, id_chain, slot):
        super().__init__(controlbox, False, id_chain)
        self.slot = slot

    def apply(self, visitor: 'ControlboxEventVisitor'):
        return visitor.next_free_slot_found(self)


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
    def next_free_slot_found(self, event: NextFreeSlotEvent):
        """
        notify that a free slot has been found in a container.
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


class ObjectState(CommonEqualityMixin, StringerMixin):
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


class ControlboxEventFactory(metaclass=ABCMeta):
    """
    Responsible for creating an event from a command response. The request
    and command_id are provided for context.
    :param request the decoded request.
    """

    @abstractmethod
    def __call__(self, controlbox: "ControlboxApplicationAdapter", response: CommandResponse, request: Request,
                 command_id: int, command):
        """
        :param controlbox:  the controlbox link to the remote device
        :param response:    the response from the controlbox protocol (a CommandResponse)
        :param request:     The originating request
        :param command_id:
        :param command:     a tuple of command method on the controlbox instance, and the parameters to the command
        :return: the created events
        """


class ReadValueEventFactory(ControlboxEventFactory):
    """
    Constructs a ObjectUpdatedEvent from a read value command.
    The decoder is given for reference so you can see what the result contents are
    """
    decoder = ReadValueResponseDecoder
    system = False

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data_length = request
        status, buffer = response

        value = controlbox._decode_state(type, buffer) if not CommandErrors.failure(status) else None
        event = ObjectUpdatedEvent(controlbox, self.system, id_chain, type, value)
        if value is None:
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class WriteValueEventFactory(ControlboxEventFactory):
    decoder = WriteValueResponseDecoder
    system = False

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data = request
        status, buffer = response

        requested_value = controlbox._decode_state(type, data) if len(data) else None
        set_value = controlbox._decode_state(type, buffer) if not CommandErrors.failure(status) else None
        event = ObjectUpdatedEvent(controlbox, self.system, id_chain, type, set_value, requested_value)
        if set_value is None:
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class CreateObjectEventFactory(ControlboxEventFactory):
    decoder = CreateObjectResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, data = request
        status_code, = response
        value = command[1][2]
        event = ObjectCreatedEvent(controlbox, False, id_chain, type, value)
        if CommandErrors.failure(status_code):
            event = CommandFailedEvent(controlbox, command, status_code, event)
        return event


class DeleteObjectEventFactory(ControlboxEventFactory):
    decoder = DeleteObjectResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type = request
        status_code, = response
        event = ObjectDeletedEvent(controlbox, False, id_chain, type)
        if CommandErrors.failure(status_code):
            event = CommandFailedEvent(controlbox, command, status_code, event)
        return event


class ListProfileEventFactory(ControlboxEventFactory):
    decoder = ListProfileResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, definitions = response
        system = profile_id == -1
        object_defs = None
        if definitions is not None:
            object_defs = [controlbox._decode_object_definition(system, x) for x in definitions]
        event = ProfileListedEvent(controlbox, profile_id, object_defs)
        if CommandErrors.failure(status):
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class NextFreeSlotEventFactory(ControlboxEventFactory):
    decoder = NextFreeSlotResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, = request
        status, = response
        slot = None if CommandErrors.failure(status) else status
        event = NextFreeSlotEvent(controlbox, id_chain, slot)
        if slot is None:
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class CreateProfileEventFactory(ControlboxEventFactory):
    decoder = CreateProfileResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = response
        event = ProfileCreatedEvent(controlbox, profile_id if not CommandErrors.failure(profile_id) else None)
        if CommandErrors.failure(profile_id):
            event = CommandFailedEvent(controlbox, command, profile_id, event)
        return event


class DeleteProfileEventFactory(ControlboxEventFactory):
    decoder = DeleteProfileResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, = response
        event = ProfileDeletedEvent(controlbox, profile_id)
        if CommandErrors.failure(status):
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class ActivateProfileEventFactory(ControlboxEventFactory):
    decoder = ActivateProfileResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        profile_id, = request
        status, = response
        event = ProfileActivatedEvent(controlbox, profile_id)
        if CommandErrors.failure(status):
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class ControllerResetEventFactory(ControlboxEventFactory):
    decoder = ResetResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        flags, = request
        status, = response
        event = ControllerResetEvent(controlbox, flags)
        if status < 0:
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


# class NoOpEventFactory(ControlboxEventFactory):
#     def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
#         pass


class ContainerObjectsLoggedEventFactory(ControlboxEventFactory):
    decoder = LogValuesResponseDecoder
    event = ContainerObjectsLoggedEvent

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        flags, id_chain = request
        status, encoded_values = response
        system = bool(flags & 0x02)  # todo - move the ad hoc value to an spec for the log command
        values = None
        if encoded_values is not None:
            values = [controlbox._decode_object_value(system, x) for x in encoded_values]
        return self.event(controlbox, system, id_chain, values)


class ListProfilesEventFactory(ControlboxEventFactory):
    decoder = ListProfilesResponseDecoder

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        active_profile, profile_ids = response
        return ProfilesListedEvent(controlbox, active_profile, profile_ids)


class ReadSystemValueEventFactory(ReadValueEventFactory):
    decoder = ReadSystemValueResponseDecoder
    system = True


class WriteSystemValueEventFactory(WriteValueEventFactory):
    decoder = WriteSystemValueResponseDecoder
    system = True


class WriteMaskedValueEventFactory(ControlboxEventFactory):
    decoder = WriteMaskedValueResponseDecoder
    system = False

    def __call__(self, controlbox: 'ControlboxApplicationAdapter', response, request, command_id, command):
        id_chain, type, buf, mask = request
        status, buffer = response
        requested_value = controlbox._decode_state(type, buf, mask)
        set_value = controlbox._decode_state(type, buffer) if CommandErrors.success(status) else None
        event = ObjectUpdatedEvent(controlbox, self.system, id_chain, type, set_value, requested_value)
        if CommandErrors.failure(status):
            event = CommandFailedEvent(controlbox, command, status, event)
        return event


class WriteSystemMaskedValueEventFactory(WriteMaskedValueEventFactory):
    decoder = WriteMaskedValueResponseDecoder
    system = True


class AsyncContainerObjectsLoggedEventFactory(ContainerObjectsLoggedEventFactory):
    pass


class FailedOperationError(Exception):
    """The requested controlbox operation could not be performed."""


class ProfileNotActiveError(FailedOperationError):
    """raised when an operation that requires an active profile is attempted, and no profile is currently active."""


class ControlboxApplicationAdapter(Controlbox):
    """
    Higher level, stateless interface to the controlbox protocol.
    Works in terms of python objects rather than protocol buffers.
    This is a "lightweight" version of the stateful in controller.py which attempts to build an
    object tree with distinct classes for each class type, and maintaining instances in a hiearchy
    that proxy the corresponding remote instances in the controller.
    This class does none of that, and provides an applciation-level view of the
    controlbox functionality. For example, setting an object state is done by providing the state as
    an appropriate python object. This is then encoded to the on the wire format by the codec.
    """
    event_factories = {
        # todo - a visitor pattern would help ensure all commands are handled
        Commands.read_value: ReadValueEventFactory(),
        Commands.write_value: WriteValueEventFactory(),
        Commands.create_object: CreateObjectEventFactory(),
        Commands.delete_object: DeleteObjectEventFactory(),
        Commands.list_profile: ListProfileEventFactory(),
        Commands.next_free_slot: NextFreeSlotEventFactory(),
        Commands.create_profile: CreateProfileEventFactory(),
        Commands.delete_profile: DeleteProfileEventFactory(),
        Commands.activate_profile: ActivateProfileEventFactory(),
        Commands.reset: ControllerResetEventFactory(),
        Commands.log_values: ContainerObjectsLoggedEventFactory(),
        Commands.next_free_slot_root: NextFreeSlotEventFactory(),
        Commands.list_profiles: ListProfilesEventFactory(),
        Commands.read_system_value: ReadSystemValueEventFactory(),
        Commands.write_system_value: WriteSystemValueEventFactory(),
        Commands.write_masked_value: WriteMaskedValueEventFactory(),
        Commands.write_system_masked_value: WriteSystemMaskedValueEventFactory(),
        Commands.async_log_values: AsyncContainerObjectsLoggedEventFactory()
    }

    class ResultFromEvent(ControlboxEventVisitor):
        """
        Turns an event into the corresponding command result.
        """

        def profile_created(self, event: ProfileCreatedEvent):
            return event.profile_id

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
            return event.as_exception()

        def objects_logged(self, event: ContainerObjectsLoggedEvent):
            return event.values

        def object_state(self, event: ObjectStateEvent):
            return event.state

        def profile_listed(self, event: ProfileListedEvent):
            return event.definitions

        def profiles_listed(self, event: ProfilesListedEvent):
            return event.profile_id, event.available_profile_ids

        def profile_deleted(self, event: ProfileDeletedEvent):
            return None

        def next_free_slot_found(self, event: NextFreeSlotEvent):
            return event.slot

    def __init__(self, controlbox: Controlbox, constructor_codec: Codec, state_codec: Codec):
        """
        listens for events from the given protocol, decodes them and reposts them
        as application events.
        :param: constructor_codec  Describes the initial state of an object.
        :param: state_codec An object that knows to encode/decode from application objects to
            the the wire format for any give type of object.
        """
        super().__init__(controlbox.connector)
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
        wrapper = self._wrapper_from_futures(futures)
        self._response_handler_wrapper(response, wrapper)

    def _response_handler_wrapper(self, response, wrapper):
        """
        Converts the response to an event and a result.

        The result is set as the result of the wrapper future (if defined)
        The event is propagated to listeners.

        :param response:    The response from the lower level. This is decoded into a ControlboxApplicationEvent
        :param wrapper:     The future wrapper from _wrap() or None if this is an unsolicited response.
        :return:    None
        """
        # find the command that was invoked, will be none for
        # unsolicited events
        command = wrapper.command if wrapper else None
        event = self._event_response(response, command)  # type: ControlboxApplicationEvent
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
        Fetches the command response and passes these to an even factory, which decodes and converts them
        into an appropriate event object.
        :param response: The response from the lower level.
        :param command: A tuple (method, (args,...)) which describe the command invoked. This is used to provide the
            command to the event factory. Will be None if this response is unsolicited.
        """
        # passing the request and the command method/args is redundant since they encode the same information
        # however we have these details available so no reason not to use them.
        command_id = response.command_id    # always set, even for unsolicited responses
        request = response.parsed_request
        response = response.parsed_response
        factory = self._event_factory(command_id)  # type: ControlboxEventFactory
        return factory(self, response, request, command_id, command)

    def _event_factory(self, command_id) -> ControlboxEventFactory:
        """
        fetches the event factory for a given command.
        """
        return self.event_factories.get(command_id)

    def _encode_state(self, type, state):
        """turns an application provided object into a byte buffer"""
        return self.state_codec.encode(type, state)

    def _decode_state(self, type, buffer, mask=None):
        """turns a byte buffer and optional into an application provided object"""
        return self.state_codec.decode(type, buffer, mask)

    def _decode_config(self, type, buffer):
        """turns a buffer encoding an object configuration into an application provided object"""
        return self.constructor_codec.decode(type, buffer)

    def _encode_config(self, type, config):
        """turns an application provided object configuration into a buffer and mask"""
        return self.constructor_codec.encode(type, config)

    def _decode_object_definition(self, system, object_def) -> ObjectDefinition:
        """decodes an object definition into an ObjectDefinition instance"""
        id_chain, type, data = object_def
        return ObjectDefinition(system, id_chain, type, self._decode_config(type, data))

    def _decode_object_value(self, system, encoded) -> ObjectState:
        """decodes an object value into an ObjectState """
        id_chain, type, data = encoded
        return ObjectState(system, id_chain, type, self._decode_state(type, data))

    def create(self, id_chain, object_type, config):
        """create a new instance on the controller with the given initial state"""
        data, mask = self._encode_config(object_type, config)
        if mask is not None:
            raise ValueError("object definition is not complete: %s", config)
        return self._wrap((self.create, (id_chain, object_type, config)),
                          self.controlbox.protocol.create_object(id_chain, object_type, data))

    def delete(self, id_chain, object_type=0):
        """Delete the object at the given location in the current profile."""
        return self._wrap((self.delete, (id_chain, object_type)),
                          self.controlbox.protocol.delete_object(id_chain, object_type))

    def read(self, id_chain, type=0):
        """read the state of a system object. the result is available via the returned
            future and also via the listener. """
        return self._wrap((self.read, (id_chain, type)),
                          self.controlbox.protocol.read_value(id_chain, type))

    def read_system(self, id_chain, type=0):
        """read the state of a system object. the result is available via the returned
            future and also via the listener. """
        return self._wrap((self.read_system, (id_chain, type)),
                          self.controlbox.protocol.read_system_value(id_chain, type))

    def write(self, id_chain, state, type=0):
        """Update the state of a given user object."""
        return self._write(self.write, False, id_chain, state, type)

    def write_system(self, id_chain, state, type=0):
        """Update the state of a given object."""
        return self._write(self.write_system, True, id_chain, state, type)

    def _write(self, caller, system, id_chain, state, type):
        """low-level write that handles the permutation of system/user write and
        the case where the mask is empty"""
        buf, mask = self._encode_state(type, state)
        fn, args = self._write_args(system, id_chain, type, buf, mask)
        return self._wrap((caller, (id_chain, state, type)), fn(args))

    def _write_args(self, system, id_chain, type, buf, mask):
        fn_regular = (self.controlbox.protocol.write_system_value, self.controlbox.protocol.write_value)
        fn_mask = (self.controlbox.protocol.write_system_masked_value, self.controlbox.protocol.write_masked_value)
        args = (id_chain, type, buf) if mask is None else (id_chain, type, buf, mask)
        fn_select = fn_regular if mask is None else fn_mask
        fn = fn_select[0 if system else 1]
        return fn, args

    def list_profiles(self) -> FutureValue:
        return self._wrap((self.list_profiles, tuple()), self.controlbox.protocol.list_profiles())

    def profile_definitions(self, profile_id) -> FutureValue:
        """
        Retrieve an iterable of all the defined objects in the profile.
        """
        return self._wrap((self.profile_definitions, (profile_id,)), self.controlbox.protocol.list_profile(profile_id))

    def create_profile(self) -> FutureValue:
        return self._wrap((self.create_profile, tuple()), self.controlbox.protocol.create_profile())

    def delete_profile(self, profile_id) -> FutureValue:
        return self._wrap((self.delete_profile, (profile_id,)), self.controlbox.protocol.delete_profile(profile_id))

    def current_state(self, system=False, id_chain=None):
        """
        Retrieve an iterable of all objects in the current profile.
        """

    def _wrap(self, command: tuple, future: FutureResponse):
        """Wrap the protocol result future as a FutureValue. This is used to provide the decoded value as the result of
        the future.
        :param command: the method and the args (as method, (args, ...))
        :param future: the future result from the protocol decoder layer
        """
        wrapper = FutureValue()
        wrapper.source = self
        wrapper.command = command
        future.app_wrapper = wrapper
        return wrapper

    def _wrapper_from_futures(self, futures):
        """
        finds the wrapper future that was added to one of the futures given
        :param futures: The set of futures waiting of a particular command invocation.
            This is provided by the lower layers. One of these may have a wrapper FutureValue
            associated with it, if it is the future that was the result of a
            command invocation from this class.
        :return:
        """
        wrapper = None
        for f in futures:
            if hasattr(f, 'app_wrapper'):
                wrapper = f.app_wrapper
                break
        return wrapper

    def discard_future(self, f: FutureValue):
        """
        Notification from the caller that it is no longer interested in the result of this future
        :param future:
        :return:
        """
        if hasattr(f, 'app_wrapper'):
            wrapper = f.app_wrapper
            del f.app_wrapper
            self.controlbox.protocol.discard_future(wrapper)
