"""
One layer above the parsed protocol.
Maps between state and the encoded binary representation
via a set of codecs.

Listens to events from the connector protocol for object updates,
and fires events to registered listeners. The raw event data
is decoded to application state.

"""
from abc import abstractmethod

from controlbox.codecs import ConnectorCodec
from controlbox.controller import Controlbox
from controlbox.protocol.controlbox import CommandResponse, Commands, ReadValueResponseDecoder, \
    WriteValueResponseDecoder, CreateObjectResponseDecoder, DeleteObjectResponseDecoder, ListProfileResponseDecoder, \
    CreateProfileResponseDecoder, DeleteProfileResponseDecoder, ActivateProfileResponseDecoder, ResetResponseDecoder, \
    LogValuesResponseDecoder, ListProfilesResponseDecoder, ReadSystemValueResponseDecoder, \
    WriteSystemValueResponseDecoder, WriteMaskedValueResponseDecoder
from controlbox.support.events import EventSource
from controlbox.support.mixins import StringerMixin


class ConnectorListener:
    """
    A listener interface that receives notifications of information from the controller.
    The object state is converted from binary format into an object representation.
    See Codec.
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


class ConnectorEvent(StringerMixin):
    """
    The base event class for all connector events.
    """
    def __init__(self, connector):
        self.connector = connector

    @abstractmethod
    def apply(self, visitor: 'ConnectorEventVisitor'):
        raise NotImplementedError()


class ObjectEvent(ConnectorEvent):
    """
    Describes an event that pertains to an object in the controller.
    """
    def __init__(self, connector, system, idchain):
        super().__init__(connector)
        self.idchain = idchain
        self.system = system


class ObjectStateEvent(ObjectEvent):
    # todo - either need separate events for user/system objects, or we need to
    # include the profile, with a special value for the system profile.
    def __init__(self, connector, system, idchain, type, state):
        super().__init__(connector, system, idchain)
        self.type = type
        self.state = state


class ProfileEvent(ConnectorEvent):
    def __init__(self, connector, profile_id):
        super().__init__(connector)
        self.profile_id = profile_id


class ObjectCreatedEvent(ObjectStateEvent):
    """
    Event notifying that an object was created in the currently active profile.
    """
    def __init__(self, connector, idchain, type, state):
        super().__init__(connector, False, idchain, type, state)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_created(self)


class ObjectDeletedEvent(ObjectStateEvent):
    def __init__(self, connector, idchain, type, state=None):
        super().__init__(connector, False, idchain, type, state)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_deleted(self)


class ObjectUpdatedEvent(ObjectStateEvent):
    """
    Describes the requested update and the resulting state of the object.
    The object itself may veto state changes, hence the requested state is not always the
    same as the actual state.
    """

    def __init__(self, connector, idchain, type, state, requested_state=None):
        super().__init__(connector, False, idchain, type, state)
        self.requested_state = requested_state

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_updated(self)


class ProfileListedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectDefinition instance (id_chain, type, config).
    """

    def __init__(self, connector, profile_id, definitions):
        super().__init__(connector, profile_id)
        self.definitions = definitions

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.profile_listed(self)


class ProfileCreatedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectState instance.
    """

    def __init__(self, connector, profile_id):
        super().__init__(connector, profile_id)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.profile_created(self)


class ProfileDeletedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectState instance.
    """

    def __init__(self, connector, profile_id):
        super().__init__(connector, profile_id)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.profile_deleted(self)


class ProfileActivatedEvent(ProfileEvent):
    """
    Notification that a profile has become active.
    todo - should also notify which profile became inactive?
    """
    def __init__(self, connector, profile_id):
        super().__init__(connector, profile_id)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.profile_activated(self)


class ControllerResetEvent(ConnectorEvent):
    def __init__(self, connector, flags, status):
        super().__init__(connector)
        self.flags = flags
        self.status = status

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.controller_reset(self)


class ContainerObjectsLoggedEvent(ObjectEvent):
    # todo - should this include the logged values too?
    def __init__(self, connector, flags, id_chain, values):
        super().__init__(connector, False, id_chain)
        self.values = values

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.objects_logged(self)


class ProfilesListedEvent(ProfileEvent):
    def __init__(self, connector, active_profile_id, available_profile_ids):
        super().__init__(connector, active_profile_id)
        self.available_profile_ids = available_profile_ids

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.profiles_listed(self)


class CommandFailedEvent(ConnectorEvent):
    """
    Indicates that a command failed.
    :param: command_id the integer ID of the command
    :param: event The event that would have been fired if the operation had succeeded.
    Note that the event itself may implicitly signal an error condition. For example,
    create profile listing a created profile ID of -1.
    """
    def __init__(self, connector, command_id, event):
        super().__init__(connector)
        self.command_id = command_id
        self.event = event

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.command_failed(self)


class ConnectorEventVisitor:
    """
    A visitor to handle the various types of events.
    """

    def object_created(self, event: ObjectCreatedEvent):
        """
        notifies that an object was created.
        """

    def object_deleted(self, event: ObjectDeletedEvent):
        """
        notifies that an object was deleted.
        """

    def object_state(self, event: ObjectStateEvent):
        """
        notifies that the current state of an object.
        """

    def object_updated(self, event: ObjectUpdatedEvent):
        """
        notifies that the state of the object has changed in response to
        an update. Note that internal updates to state within the controller do not
        generate an update event. These state changes are made available via state events.
        """

    def system_object_update(self, event: ObjectUpdatedEvent):
        """
        notifies that the state of the system object has changed in response to an
        external update.
        """

    def system_object_state(self, event: ObjectStateEvent):
        """
        notifies the state of a system object.
        """

    def objects_logged(self, event: ContainerObjectsLoggedEvent):
        """
        notifies the state of all objects in a container.
        """

    def profile_created(self, event: ProfileCreatedEvent):
        """
        notifies that a profile was created.
        """

    def profile_deleted(self, event: ProfileDeletedEvent):
        """
        notifies that profile was deleted.
        """

    def profile_listed(self, event: ProfileListedEvent):
        """ notifies the definition of objects in a given profile. """

    def profile_activated(self, event: ProfileActivatedEvent):
        """
        notifies that a profile has been activated.
        """

    def profiles_listed(self, event: ProfilesListedEvent):
        """
        notifies the profiles available and which one is active.
        """

    def controller_reset(self, event: ControllerResetEvent):
        """
        notifies that the device will reset.
        """

    def command_failed(self, event: CommandFailedEvent):
        """
        notifies that a command failed in some way.
        The command that failed is available in the event.
        """


class ObjectState:
    """
    Describes the state of an object.
    """
    def __init__(self, idchain, type, state):
        """
        :param idchain  The identifier for the object
        """
        self.idchain = idchain
        self.type = type
        self.state = state


class ObjectDefinition(ObjectState):
    """
    Describes the construction state of an object.
    """


class ConnectorEventFactory:
    """
    Responsible for creating an event from a command response. The request
    and command_id are provided for context.
    :param request the decoded request.
    """
    @abstractmethod
    def __call__(self, connector: "ControlboxEvents", response, request, command_id):
        raise NotImplementedError()


class ReadValueEventFactory(ConnectorEventFactory):
    decoder = ReadValueResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, data_length = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, value)


class WriteValueEventFactory(ConnectorEventFactory):
    decoder = WriteValueResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, data = request
        buffer, = response
        requested_value = connector.decode_state(type, buffer)
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, set_value, requested_value)


class CreateObjectEventFactory(ConnectorEventFactory):
    decoder = CreateObjectResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, data = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        return ObjectCreatedEvent(connector, id_chain, type, value)


class DeleteObjectEventFactory(ConnectorEventFactory):
    decoder = DeleteObjectResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type = request
        code, = response
        return ObjectDeletedEvent(connector, id_chain, type)


class ListProfileEventFactory(ConnectorEventFactory):
    decoder = ListProfileResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        profile_id, = request
        definitions, = response
        object_defs = [connector.decode_definition(x) for x in definitions]
        return ProfileListedEvent(connector, profile_id, object_defs)


class CreateProfileEventFactory(ConnectorEventFactory):
    decoder = CreateProfileResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        profile_id, = response
        event = ProfileCreatedEvent(connector, profile_id)
        # todo factor valid/invalid id logic for profiles to a central method
        if profile_id < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class DeleteProfileEventFactory(ConnectorEventFactory):
    decoder = DeleteProfileResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        profile_id, = request
        status, = response
        event = ProfileDeletedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class ActivateProfileEventFactory(ConnectorEventFactory):
    decoder = ActivateProfileResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        profile_id, = request
        status, = response
        event = ProfileActivatedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class ResetEventFactory(ConnectorEventFactory):
    decoder = ResetResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        flags, = request
        status, = response
        return ControllerResetEvent(connector, flags, status)


class NoOpEventFactory(ConnectorEventFactory):
    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        pass


class LogValuesEventFactory(ConnectorEventFactory):
    decoder = LogValuesResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        flags, id_chain = request
        # todo - complete parsing response
        return ContainerObjectsLoggedEvent(connector, flags, id_chain)


class ListProfilesEventFactory(ConnectorEventFactory):
    decoder = ListProfilesResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        active_profile, profile_ids = response
        return ProfilesListedEvent(connector, active_profile, profile_ids)


class ReadSystemValueEventFactory(ConnectorEventFactory):
    decoder = ReadSystemValueResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, data_length = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        # todo - distinguish system vs profile objects
        return ObjectUpdatedEvent(connector, id_chain, type, value)


class WriteSystemValueEventFactory(ConnectorEventFactory):
    decoder = WriteSystemValueResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, to_write = request
        buffer, = response
        requested_value = connector.decode_state(type, buffer)
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, requested_value, set_value)


class WriteMaskedValueEventFactory(ConnectorEventFactory):
    decoder = WriteMaskedValueResponseDecoder

    def __call__(self, connector: 'ControlboxEvents', response, request, command_id):
        id_chain, type, _ = request
        buffer, = response
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, set_value)


class WriteSystemMaskedValueEventFactory(WriteMaskedValueEventFactory):
    pass
    # todo - this should at least set a flag to indicate the object changed is in the system namespace.


class AsyncLogValuesEventFactory(LogValuesEventFactory):
    pass


class ControlboxEvents:
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

    def _response_handler(self, response: CommandResponse, futures):
        """
        The listener method for responses received from the protocol.
        :param: response The response value is the response structure, parsed to separate out the semantically
        distinct parts of the protocol. The response key is the command request data.
        """
        event = self.event_response(response)
        if event is not None:
            self.listeners.fire(event)

    def event_response(self, response: CommandResponse):
        """
        Fetches the command details and passes these to a decoder, which converts them
        into an appropriate event object.
        """
        command_id = response.command_id
        request = response.parsed_request
        response = response.parsed_response
        factory = self._event_factory(command_id)
        return factory(self, response, request, command_id)

    def _event_factory(self, command_id):
        """
        fetches the event factory for a given command.
        """
        return self.eventFactories.get(command_id)

    def encode_state(self, type, state):
        return self.state_codec.encode(type, state)

    def decode_state(self, type, buffer, mask=None):
        return self.state_codec.decode(type, buffer, mask)

    def decode_config(self, type, buffer):
        return self.constructor_codec.decode(type, buffer)

    def encode_config(self, type, config):
        return self.constructor_codec.encode(type, config)

    def decode_definition(self, object_def):
        id_chain, type, data = object_def
        return ObjectState(id_chain, type, self.decode_config(type, data))

    def create(self, id_chain, object_type, config):
        """ creates a new instance on the controller with the given initial state"""
        data, mask = self.encode_config(type, config)
        if mask is not None:
            raise ValueError("object definition is not complete: %s", config)
        return self.controlbox.protocol.create_object(id_chain, object_type, data)

    def delete(self, id_chain, object_type=0):
        """
        Deletes the object at the given location in the current profile.
        """
        return self.controlbox.protocol.delete_object(id_chain, object_type)

    def read(self, id_chain, type=0):
        """ read the state of a system object. the result is available via the returned
            future and also via the listener. """
        # todo - how to wrap the result from the future to apply the decoding?
        # will need a future wrapper with a mapping function to wrap the result.
        return self.controlbox.protocol.read_value(id_chain, type)

    def read_system(self, id_chain, type=0):
        """ read the state of the object. the result is available via the returned
            future and also via the listener. """
        # todo - how to wrap the result from the future to apply the decoding?
        # will need a future wrapper with a mapping function to wrap the result.
        return self.controlbox.protocol.read_system_value(id_chain, type)

    def write(self, id_chain, state, type=0):
        """
        updates the state of a given object.
        """
        buf = self.state_codec.encode(state)
        return self.controlbox.protocol.write_value(id_chain, type, buf)

    def profile(self, profile_id):
        """
        Retrieves an array of all the defined object states in the profile.
        """

    def current_state(self):
        """
        retrieves an iterator of all objects in the current profile.
        """

    def __str__(self):
        return super().__str__()
