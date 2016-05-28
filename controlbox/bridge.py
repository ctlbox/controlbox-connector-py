"""
One layer above the decoded protocol.
Listens to events from the connector protocol and fires events to registered listeners
"""
from abc import abstractmethod

from controlbox.controller import Controlbox
from controlbox.protocol.controlbox import CommandResponse, Commands, ReadValueResponseDecoder, \
    WriteValueResponseDecoder, CreateObjectResponseDecoder, DeleteObjectResponseDecoder, ListProfileResponseDecoder, \
    CreateProfileResponseDecoder, DeleteProfileResponseDecoder, ActivateProfileResponseDecoder, ResetResponseDecoder, \
    LogValuesResponseDecoder, ListProfilesResponseDecoder, ReadSystemValueResponseDecoder, \
    WriteSystemValueResponseDecoder, WriteMaskedValueResponseDecoder
from controlbox.support.events import EventSource


class ConnectorCodec:
    """
    Knows how to convert object state to/from the on-wire data format.
    """

    @abstractmethod
    def decode(self, type, data, mask=None):
        """
        decodes an object state representation.
        realm: either constructor or state
        """
        raise NotImplementedError()

    @abstractmethod
    def encode(self, type, value):
        """ returns (type, data, mask)
            Encodes a given value as a data buffer and a mask.
         """
        raise NotImplementedError()


class ConnectorListener:
    """
    A listener interface that receives notifications of information from the controller.
    The object state is converted from on+the+wire binary format into an object representation.
    See ConnectorCodec.
    """

    def object_created(self, idchain, state):
        """
        notifies that an object was created.
        :param: idchain
        :param: state the construction state of the object.
        """

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
        notifies that the current state of a number of objects. (The state description is complete.)
        """

    def object_update(self, idchain, state):
        """
        notifies that the state of the object has changed in response to
        an update. Note that internal updates to state within the controller do not
        generate an update event. These state changes are made available via state events.
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


class ConnectorEvent:
    def __init__(self, connector):
        self.connector = connector

    @abstractmethod
    def apply(self, visitor: 'ConnectorEventVisitor'):
        raise NotImplementedError()


class ObjectEvent(ConnectorEvent):
    def __init__(self, connector, idchain):
        super().__init__(connector)
        self.idchain = idchain


class ObjectStateEvent(ObjectEvent):
    def __init__(self, connector, idchain, type, state):
        super().__init__(connector, idchain)
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
        super().__init__(connector, idchain, type, state)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_created(self)


class ObjectDeletedEvent(ObjectStateEvent):
    def __init__(self, connector, idchain, type, state=None):
        super().__init__(connector, idchain, type, state)

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_updated(self)


# todo - the fully qualified address of an object in a controller should include the profile_id, or -1 for
# system objects
# since the profile_id isn't sent with every update (at least, not at present), this does mean requiring
# some state, or simply reporting current profile with each object update.
class ObjectUpdatedEvent(ObjectStateEvent):
    """
    Describes the requested update and the resulting state of    the object.
    """

    def __init__(self, connector, idchain, type, state, requested_state=None):
        super().__init__(connector, idchain, type, state)
        self.requested_state = requested_state

    def apply(self, visitor: 'ConnectorEventVisitor'):
        return visitor.object_updated(self)


class ProfileListedEvent(ProfileEvent):
    """
    Describes the requested update and the resulting state of the object.
    :param: definitions an iterable of object definitions. Each definition is a
        ObjectState instance.
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


class ContainerObjectsLeggedEvent(ObjectEvent):
    def __init__(self, connector, flags, id_chain):
        super().__init__(connector, id_chain, )

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
    A listener interface that receives notifications of information from the controller.
    The object state is converted from on+the+wire binary format into an object representation.
    See ConnectorCodec.
    """

    def object_created(self, event: ObjectCreatedEvent):
        """
        notifies that an object was created.
        """

    def object_deleted(self, event: ObjectDeletedEvent):
        """
        notifies that an object was deleted.
        """

    def object_read(self, event: ObjectUpdatedEvent):
        """
        notifies that the current state of a number of objects. (The state description is complete.)
        """

    def object_updated(self, event: ObjectUpdatedEvent):
        """
        notifies that the state of the object has changed in response to
        an update. Note that internal updates to state within the controller do not
        generate an update event. These state changes are made available via state events.
        """

    def system_object_update(self, event: ObjectUpdatedEvent):
        # todo - should we keep distinguishing system vs profile objects like this?
        # would it be cleaner to use a profile_id field, which is 0 for system objects?
        """
        notifies that the state of the system object has changed in response to an
        external update.
        """

    def system_object_state(self, event: ObjectUpdatedEvent):
        """
        notifies the state of a system object.
        """

    def objects_logged(self, event: ContainerObjectsLeggedEvent):
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
    Describes the state of an object. It's really just an association of something with an
    object ID.
    """

    def __init__(self, idchain, type, state):
        self.idchain = idchain
        self.type = type
        self.state = state


class ConnectorEventFactory:
    """
    Responsible for creating an event.
    """

    @abstractmethod
    def __call__(self, *args, **kwargs):
        raise NotImplementedError()


class ReadValueEventFactory(ConnectorEventFactory):
    decoder = ReadValueResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, data_length = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, value)


class WriteValueEventFactory(ConnectorEventFactory):
    decoder = WriteValueResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, data = request
        buffer, = response
        requested_value = connector.decode_state(type, buffer)
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, set_value, requested_value)


class CreateObjectEventFactory(ConnectorEventFactory):
    decoder = CreateObjectResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, data = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        return ObjectCreatedEvent(connector, id_chain, type, value)


class DeleteObjectEventFactory(ConnectorEventFactory):
    decoder = DeleteObjectResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type = request
        code, = response
        return ObjectDeletedEvent(connector, id_chain, type)


class ListProfileEventFactory(ConnectorEventFactory):
    decoder = ListProfileResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        profile_id, = request
        definitions, = response
        object_defs = [connector.decode_definition(x) for x in definitions]
        return ProfileListedEvent(connector, profile_id, object_defs)


class CreateProfileEventFactory(ConnectorEventFactory):
    decoder = CreateProfileResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        profile_id, = response
        event = ProfileCreatedEvent(connector, profile_id)
        # todo factor valid/invalid id logic for profiles to a central method
        if profile_id < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class DeleteProfileEventFactory(ConnectorEventFactory):
    decoder = DeleteProfileResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        profile_id, = request
        status, = response
        event = ProfileDeletedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class ActivateProfileEventFactory(ConnectorEventFactory):
    decoder = ActivateProfileResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        profile_id, = request
        status, = response
        event = ProfileActivatedEvent(connector, profile_id)
        if status < 0:
            event = CommandFailedEvent(connector, command_id, event)
        return event


class ResetEventFactory(ConnectorEventFactory):
    decoder = ResetResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        flags, = request
        status, = response
        return ControllerResetEvent(connector, flags, status)


class NoOpEventFactory(ConnectorEventFactory):
    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        pass


class LogValuesEventFactory(ConnectorEventFactory):
    decoder = LogValuesResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        flags, id_chain = request
        # todo - complete parsing response
        return ContainerObjectsLeggedEvent(connector, flags, id_chain)


class ListProfilesEventFactory(ConnectorEventFactory):
    decoder = ListProfilesResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        active_profile, profile_ids = response
        return ProfilesListedEvent(connector, active_profile, profile_ids)


class ReadSystemValueEventFactory(ConnectorEventFactory):
    decoder = ReadSystemValueResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, data_length = request
        buffer, = response
        value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, value)


class WriteSystemValueEventFactory(ConnectorEventFactory):
    decoder = WriteSystemValueResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, to_write = request
        buffer, = response
        requested_value = connector.decode_state(type, buffer)
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, requested_value, set_value)


class WriteMaskedValueEventFactory(ConnectorEventFactory):
    decoder = WriteMaskedValueResponseDecoder

    def __call__(self, connector: 'ConnectorEvents', response, request, command_id):
        id_chain, type, _ = request
        buffer, = response
        set_value = connector.decode_state(type, buffer)
        return ObjectUpdatedEvent(connector, id_chain, type, set_value)


class WriteSystemMaskedValueEventFactory(WriteMaskedValueEventFactory):
    pass
    # todo - this should at least set a flag to indicate the object changed is in the system namespace.


class AsyncLogValuesEventFactory(LogValuesEventFactory):
    pass


class ConnectorEvents:
    """
    Higher level, stateless interface to the controlbox protocol.
    Works in terms of python objects rather than protocol buffers.
    """
    eventFactories = {
        Commands.read_value: ReadValueEventFactory,
        Commands.write_value: WriteValueEventFactory,
        Commands.create_object: CreateObjectEventFactory,
        Commands.delete_object: DeleteObjectEventFactory,
        Commands.list_profile: ListProfileEventFactory,
        Commands.next_free_slot: NoOpEventFactory,  # NextFreeSlotEventFactory,
        Commands.create_profile: CreateProfileEventFactory,
        Commands.delete_profile: DeleteProfileEventFactory,
        Commands.activate_profile: ActivateProfileEventFactory,
        Commands.reset: ResetEventFactory,
        Commands.log_values: LogValuesEventFactory,
        Commands.next_free_slot_root: NoOpEventFactory,
        Commands.list_profiles: ListProfilesEventFactory,
        Commands.read_system_value: ReadSystemValueEventFactory,
        Commands.write_system_value: WriteSystemValueEventFactory,
        Commands.write_masked_value: WriteMaskedValueEventFactory,
        Commands.write_system_masked_value: WriteSystemMaskedValueEventFactory,
        Commands.async_log_values: AsyncLogValuesEventFactory
    }

    def __init__(self, controlbox: Controlbox, constructor_codec: ConnectorCodec, state_codec: ConnectorCodec):
        """
        listens for events from the given protocol, decodes them and reposts them
        as application events.
        :param: initial_codec  Describes the initial state of an object.
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
        fetches the decoder for a given command.
        """
        return self.eventFactories.get(command_id)

    def encode_state(self, type, state):
        return self.state_codec.encode(type, state)

    def decode_state(self, type, buffer, mask=None):
        return self.state_codec.decode(type, buffer, mask)

    def decode_config(self, type, buffer):
        return self.constructor_codec.decode(type, buffer)

    def encode_config(self, type, state):
        return self.constructor_codec.encode(type, state)

    def decode_definition(self, object_def):
        id_chain, type, data = object_def
        return ObjectState(id_chain, type, self.decode_config(type, data))

    def create(self, id_chain, object_type, state):
        """ creates a new instance on the controller with the given initial state"""
        data = self.encode_config(type, state)
        self.controlbox.protocol.create_object(id_chain, object_type, data)

    def delete(self, idchain):
        """
        Deletes the object at the given location in the current profile.
        """

    def read(self, idchain):
        """ read the state of the object. the result is avaailble via the returned
            future and also via the listener. """

    def write(self, idchain, state):
        """
        updates the state of a given object.
        """

    def profile(self, profile_id):
        """
        Retrieves an array of all the defined object states in the profile.
        """

    def current_state(self):
        """
        retrieves an iterator of all objects in the current profile.
        """
