from unittest import TestCase
from unittest.mock import Mock, call

from hamcrest import assert_that, calling, equal_to, has_length, instance_of, is_, raises

from controlbox.protocol.async import FutureResponse, FutureValue
from controlbox.protocol.controlbox import CommandResponse, Commands
from controlbox.stateless.api import ActivateProfileEventFactory, CommandFailedEvent, ContainerObjectsLoggedEvent, \
    ContainerObjectsLoggedEventFactory, ControlboxApplicationAdapter, ControlboxApplicationEvent, ControllerResetEvent,\
    ControllerResetEventFactory, CreateObjectEventFactory, CreateProfileEventFactory, DeleteObjectEventFactory, \
    DeleteProfileEventFactory, FailedOperationError, ListProfileEventFactory, ListProfilesEventFactory, \
    NextFreeSlotEvent, NextFreeSlotEventFactory, ObjectCreatedEvent, ObjectDefinition, ObjectDeletedEvent, ObjectEvent,\
    ObjectState, ObjectStateEvent, ObjectUpdatedEvent, ProfileActivatedEvent, ProfileCreatedEvent, ProfileDeletedEvent,\
    ProfileEvent, ProfileListedEvent, ProfilesListedEvent, ReadSystemValueEventFactory, ReadValueEventFactory, \
    WriteMaskedValueEventFactory, WriteSystemMaskedValueEventFactory, WriteSystemValueEventFactory, \
    WriteValueEventFactory


class AbstractReadTest(TestCase):
    def read(self, factory, system):
        sut = factory
        connector = Mock()
        request = [1], 1, 1
        response = 0, [1]
        command = Mock()
        command_id = 1
        event = sut(connector, response, request, command_id, command)
        assert_that(event, is_(instance_of(ObjectStateEvent)))
        assert_that(event.system, is_(system))


class ReadSystemValueEventFactoryTest(AbstractReadTest):
    def test_call(self):
        self.read(ReadSystemValueEventFactory(), True)


class ReadValueEventFactoryTest(AbstractReadTest):
    def test_call(self):
        self.read(ReadValueEventFactory(), False)


class ControlboxApplicationEventTest(TestCase):
    def test_is_abstract(self):
        assert_that(calling(ControlboxApplicationEvent), raises(TypeError))

    def test_constructor(self):
        class TestEvent(ControlboxApplicationEvent):
            def apply(self, visitor: 'ControlboxEventVisitor'):
                pass    # pragma no cover

        controlbox = Mock()
        sut = TestEvent(controlbox)
        assert_that(sut.controlbox, is_(controlbox))


class ObjectEventTest(TestCase):
    @staticmethod
    def assert_object_event(sut, controlbox, system, idchain):
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.idchain, is_(idchain))
        assert_that(sut.system, is_(system))

    def test_constructor(self):
        class TestEvent(ObjectEvent):
            def apply(self, visitor: 'ControlboxEventVisitor'):
                pass    # pragma no cover

        controlbox, system, idchain = Mock(), Mock(), Mock()
        sut = TestEvent(controlbox, system, idchain)
        self.assert_object_event(sut, controlbox, system, idchain)


class ObjectStateEventTest(TestCase):
    @staticmethod
    def assert_object_state_event(sut: ObjectStateEvent, controlbox, system, idchain, type, state):
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.idchain, is_(idchain))
        assert_that(sut.system, is_(system))
        assert_that(sut.type, is_(type))
        assert_that(sut.state, is_(state))

    def test_constructor(self):
        controlbox, system, idchain, type, state = Mock(), Mock(), Mock(), Mock(), Mock()
        sut = ObjectStateEvent(controlbox, system, idchain, type, state)
        ObjectStateEventTest.assert_object_state_event(sut, controlbox, system, idchain, type, state)

    def test_visitor_user(self):
        visitor = Mock()
        sut = ObjectStateEvent(Mock(), False, Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.object_state.assert_called_once_with(sut)

    def test_visitor_system(self):
        visitor = Mock()
        sut = ObjectStateEvent(Mock(), True, Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.object_state.assert_called_once_with(sut)


class ProfileEventTest(TestCase):
    @staticmethod
    def assert_profile_event(sut, controlbox, profile_id):
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.profile_id, is_(profile_id))

    def test_constructor(self):
        class TestEvent(ProfileEvent):
            def apply(self, visitor: 'ControlboxEventVisitor'):
                pass  # pragma no cover

        controlbox, profile_id = Mock(), 5
        sut = TestEvent(controlbox, profile_id)
        self.assert_profile_event(sut, controlbox, profile_id)


class ObjectCreatedEventTest(TestCase):
    def test_constructor(self):
        controlbox, system, idchain, type, state = Mock(), Mock(), Mock(), Mock(), Mock()
        sut = ObjectCreatedEvent(controlbox, system, idchain, type, state)
        ObjectStateEventTest.assert_object_state_event(sut, controlbox, system, idchain, type, state)

    def test_visitor(self):
        visitor = Mock()
        sut = ObjectCreatedEvent(Mock(), Mock(), Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.object_created.assert_called_once_with(sut)


class ObjectDeletedEventTest(TestCase):
    def test_constructor(self):
        controlbox, system, idchain, type = Mock(), Mock(), Mock(), Mock()
        sut = ObjectDeletedEvent(controlbox, system, idchain, type)
        ObjectStateEventTest.assert_object_state_event(sut, controlbox, system, idchain, type, None)

    def test_visitor(self):
        visitor = Mock()
        sut = ObjectDeletedEvent(Mock(), Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.object_deleted.assert_called_once_with(sut)


class ObjectUpdatedEventTest(TestCase):
    def test_constructor(self):
        controlbox, system, idchain, type, state, requested = Mock(), Mock(), Mock(), Mock(), Mock(), Mock()
        sut = ObjectUpdatedEvent(controlbox, system, idchain, type, state, requested)
        ObjectStateEventTest.assert_object_state_event(sut, controlbox, system, idchain, type, state)
        assert_that(sut.requested_state, is_(requested))

    def test_visitor(self):
        visitor = Mock()
        sut = ObjectUpdatedEvent(Mock(), Mock(), Mock(), Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.object_updated.assert_called_once_with(sut)


class ProfileListedEventTest(TestCase):
    def test_constructor(self):
        controlbox, profile_id, definitions = Mock(), Mock(), Mock()
        sut = ProfileListedEvent(controlbox, profile_id, definitions)
        ProfileEventTest.assert_profile_event(sut, controlbox, profile_id)
        assert_that(sut.definitions, is_(definitions))

    def test_visitor(self):
        visitor = Mock()
        sut = ProfileListedEvent(Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.profile_listed.assert_called_once_with(sut)


class ProfileCreatedEventTest(TestCase):
    def test_constructor(self):
        controlbox, profile_id = Mock(), Mock()
        sut = ProfileCreatedEvent(controlbox, profile_id)
        ProfileEventTest.assert_profile_event(sut, controlbox, profile_id)

    def test_visitor(self):
        visitor = Mock()
        sut = ProfileCreatedEvent(Mock(), Mock())
        sut.apply(visitor)
        visitor.profile_created.assert_called_once_with(sut)


class ProfileDeletedEventTest(TestCase):
    def test_constructor(self):
        controlbox, profile_id = Mock(), Mock()
        sut = ProfileDeletedEvent(controlbox, profile_id)
        ProfileEventTest.assert_profile_event(sut, controlbox, profile_id)

    def test_visitor(self):
        visitor = Mock()
        sut = ProfileDeletedEvent(Mock(), Mock())
        sut.apply(visitor)
        visitor.profile_deleted.assert_called_once_with(sut)


class ProfileActivatedEventTest(TestCase):
    def test_constructor(self):
        controlbox, profile_id = Mock(), Mock()
        sut = ProfileActivatedEvent(controlbox, profile_id)
        ProfileEventTest.assert_profile_event(sut, controlbox, profile_id)

    def test_visitor(self):
        visitor = Mock()
        sut = ProfileActivatedEvent(Mock(), Mock())
        sut.apply(visitor)
        visitor.profile_activated.assert_called_once_with(sut)


class ControllerResetEventTest(TestCase):
    def test_constructor(self):
        controlbox, flags = Mock(), Mock()
        sut = ControllerResetEvent(controlbox, flags)
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.flags, is_(flags))

    def test_visitor(self):
        visitor = Mock()
        sut = ControllerResetEvent(Mock(), Mock())
        sut.apply(visitor)
        visitor.controller_reset.assert_called_once_with(sut)


class ContainerObjectsLoggedEventTest(TestCase):
    def test_constructor(self):
        controlbox, system, id_chain, values = Mock(), Mock(), Mock(), Mock()
        sut = ContainerObjectsLoggedEvent(controlbox, system, id_chain, values)
        ObjectEventTest.assert_object_event(sut, controlbox, system, id_chain)
        assert_that(sut.values, is_(values))

    def test_visitor(self):
        visitor = Mock()
        sut = ContainerObjectsLoggedEvent(Mock(), Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.objects_logged.assert_called_once_with(sut)


class ProfilesListedEventTest(TestCase):
    def test_constructor(self):
        controlbox, active, available = Mock(), Mock(), Mock()
        sut = ProfilesListedEvent(controlbox, active, available)
        ProfileEventTest.assert_profile_event(sut, controlbox, active)
        assert_that(sut.available_profile_ids, is_(available))

    def test_visitor(self):
        visitor = Mock()
        sut = ProfilesListedEvent(Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.profiles_listed.assert_called_once_with(sut)


class NextFreeSlotEventTest(TestCase):
    def test_constructor(self):
        controlbox, id_chain, slot = Mock(), Mock(), Mock()
        sut = NextFreeSlotEvent(controlbox, id_chain, slot)
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.idchain, is_(id_chain))
        assert_that(sut.slot, is_(slot))
        assert_that(sut.system, is_(False))

    def test_visitor(self):
        visitor = Mock()
        sut = NextFreeSlotEvent(Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.next_free_slot_found.assert_called_once_with(sut)


class CommandFailedEventTest(TestCase):
    def test_constructor(self):
        controlbox, command, reason, event = Mock(), Mock(), Mock(), Mock()
        sut = CommandFailedEvent(controlbox, command, reason, event)
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.command, is_(command))
        assert_that(sut.reason, is_(reason))
        assert_that(sut.event, is_(event))

    def test_visitor(self):
        visitor = Mock()
        sut = CommandFailedEvent(Mock(), Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.command_failed.assert_called_once_with(sut)

    def test_as_exception(self):
        controlbox, command, reason, event = Mock(), Mock(), Mock(), Mock()
        sut = CommandFailedEvent(controlbox, command, reason, event)
        exception = sut.as_exception()
        assert_that(exception, is_(instance_of(FailedOperationError)))
        assert_that(exception.event, is_(sut))


class ObjectStateTest(TestCase):
    @staticmethod
    def assert_object_state(sut, system, idchain, type, state):
        assert_that(sut.system, is_(system))
        assert_that(sut.idchain, is_(idchain))
        assert_that(sut.type, is_(type))
        assert_that(sut.state, is_(state))

    def test_constructor(self):
        system, idchain, type, state = Mock(), Mock(), Mock(), Mock()
        sut = ObjectState(system, idchain, type, state)
        self.assert_object_state(sut, system, idchain, type, state)


class ControlboxEventFactoryTest(TestCase):
    def setUp(self):
        self.controlbox = Mock()
        self.command = (Mock(), (1, 2, 3))
        self.decode_state = Mock()      # 1st return value from first call to decode a state/definition
        self.decode_state2 = Mock()     # 2nd return value
        self.controlbox._decode_state = Mock(side_effect=[self.decode_state, self.decode_state2])
        self.controlbox._decode_object_definition = Mock(side_effect=[self.decode_state, self.decode_state2])
        self.controlbox._decode_object_value = lambda system, defn: \
            ControlboxApplicationAdapter._decode_object_value(self.controlbox, system, defn)

    def test_ReadValueEventFactory(self):
        self.assert_read_value(ReadValueEventFactory, False)

    def test_ReadSystemValueEventFactory(self):
        self.assert_read_value(ReadSystemValueEventFactory, True)

    def assert_read_value(self, factory, system):
        sut = factory()
        id_chain, type, datalen = Mock(), Mock(), Mock()
        request = id_chain, type, datalen
        status, data = 10, Mock()
        response = status, data
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(
            ObjectUpdatedEvent(self.controlbox, system, id_chain, type, self.decode_state))))
        self.controlbox._decode_state.assert_called_with(type, data)

    def test_ReadValueEventFactory_fail(self):
        sut = ReadValueEventFactory()
        id_chain, type, datalen = Mock(), Mock(), Mock()
        request = id_chain, type, datalen
        status, data = -10, []
        response = status, data
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ObjectUpdatedEvent(self.controlbox, False, id_chain, type, None)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))
        self.controlbox._decode_state.assert_not_called()

    def test_WriteValueEventFactory(self):
        self.assert_write_value(WriteValueEventFactory, False)

    def test_WriteMaskedValueEventFactory(self):
        self.assert_write_value(WriteMaskedValueEventFactory, False, bytes([7, 8, 9]))

    def test_WriteSystemValueEventFactory(self):
        self.assert_write_value(WriteSystemValueEventFactory, True)

    def test_WriteSystemMaskedValueEventFactory(self):
        self.assert_write_value(WriteSystemMaskedValueEventFactory, True, bytes([7, 8, 9]))

    def assert_write_value(self, factory, system, mask=None):
        sut = factory()
        id_chain, type, request_data = Mock(), Mock(), bytes([4, 5, 6])
        request = (id_chain, type, request_data) if mask is None else (id_chain, type, request_data, mask)
        status, data = 10, bytes([1, 2, 3])
        response = status, data
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ObjectUpdatedEvent(self.controlbox, system, id_chain, type, self.decode_state2,
                                                           self.decode_state))))
        decode_request_call = call(type, request_data) if mask is None else call(type, request_data, mask)
        assert_that(self.controlbox._decode_state.mock_calls, equal_to([decode_request_call, call(type, data)]))

    def test_WriteValueEventFactory_fail(self):
        self.assert_write_value_fail(WriteValueEventFactory, False)

    def test_WriteMaskValueEventFactory_fail(self):
        self.assert_write_value_fail(WriteMaskedValueEventFactory, False, bytes([7, 8, 9]))

    def assert_write_value_fail(self, factory, system, mask=None):
        sut = factory()
        id_chain, type, request_data = Mock(), Mock(), bytes([4, 5, 6])
        request = (id_chain, type, request_data) if mask is None else (id_chain, type, request_data, mask)
        status, data = -10, bytes([1, 2, 3])    # the buffer is ignored on error
        response = status, data
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ObjectUpdatedEvent(self.controlbox, system, id_chain, type, None, self.decode_state)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))
        decode_call = call(type, request_data) if mask is None else call(type, request_data, mask)
        assert_that(self.controlbox._decode_state.mock_calls, is_(equal_to([decode_call])))

    def test_CreateObjectEventFactory(self):
        sut = CreateObjectEventFactory()
        id_chain, type, request_data = Mock(), Mock(), bytes([4, 5, 6])
        request = id_chain, type, request_data
        status = 10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ObjectCreatedEvent(self.controlbox, False, id_chain, type, 3))))
        self.controlbox._decode_state.assert_not_called()

    def test_CreateObjectEventFactory_fail(self):
        sut = CreateObjectEventFactory()
        id_chain, type, request_data = Mock(), Mock(), bytes([4, 5, 6])
        request = id_chain, type, request_data
        status = -10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ObjectCreatedEvent(self.controlbox, False, id_chain, type, 3)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))
        self.controlbox._decode_state.assert_not_called()

    def test_DeleteObjectEventFactory(self):
        sut = DeleteObjectEventFactory()
        id_chain, type = Mock(), Mock()
        request = id_chain, type
        status = 10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ObjectDeletedEvent(self.controlbox, False, id_chain, type))))
        self.controlbox._decode_state.assert_not_called()

    def test_DeleteObjectEventFactory_fail(self):
        sut = DeleteObjectEventFactory()
        id_chain, type = Mock(), Mock()
        request = id_chain, type
        status = -10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ObjectDeletedEvent(self.controlbox, False, id_chain, type)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))
        self.controlbox._decode_state.assert_not_called()

    def test_ListProfileEventFactory(self):
        self.assert_list_profile(20, False)

    def test_ListProfileEventFactory_system(self):
        self.assert_list_profile(-1, True)

    def assert_list_profile(self, profile_id, system):
        sut = ListProfileEventFactory()
        request = profile_id,
        status, definitions = 10, [bytes([1]), bytes([2])]
        response = status, definitions

        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ProfileListedEvent(self.controlbox, profile_id,
                                                           [self.decode_state, self.decode_state2]))))
        assert_that(self.controlbox._decode_object_definition.mock_calls,
                    is_(equal_to([call(system, definitions[0]), call(system, definitions[1])])))

    def test_ListProfileEventFactory_fail(self):
        sut = ListProfileEventFactory()
        profile_id = Mock()
        request = profile_id,
        status, definitions = -10, None
        response = status, definitions
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ProfileListedEvent(self.controlbox, profile_id, None)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))
        self.controlbox._decode_object_definition.assert_not_called()

    def test_ListProfilesEventFactory(self):
        sut = ListProfilesEventFactory()
        request = tuple()
        active, available = Mock(), Mock()
        response = active, available
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ProfilesListedEvent(self.controlbox, active, available))))

    def test_ListProfilesEventFactory_fail(self):
        sut = ListProfilesEventFactory()
        request = tuple()
        active, available = Mock(), Mock()
        response = active, available
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ProfilesListedEvent(self.controlbox, active, available))))

    def test_CreateProfileEventFactory(self):
        self.assert_profile_event(CreateProfileEventFactory, ProfileCreatedEvent, None, (4,))

    def test_CreateProfileEventFactory_fail(self):
        self.assert_profile_event_fail(CreateProfileEventFactory, ProfileCreatedEvent, None, (-10,))

    def test_DeleteProfileEventFactory(self):
        self.assert_profile_event(DeleteProfileEventFactory, ProfileDeletedEvent, (4,), (0,))

    def test_DeleteProfileEventFactory_fail(self):
        self.assert_profile_event_fail(DeleteProfileEventFactory, ProfileDeletedEvent, (4,), (-10,))

    def test_ActivateProfileEventFactory(self):
        self.assert_profile_event(ActivateProfileEventFactory, ProfileActivatedEvent, (4,), (0,))

    def test_ActivateProfileEventFactory_fail(self):
        self.assert_profile_event_fail(ActivateProfileEventFactory, ProfileActivatedEvent, (4,), (-10,))

    def assert_profile_event(self, factory, event_class, request, response):
        sut = factory()
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(event_class(self.controlbox, 4))))

    def assert_profile_event_fail(self, factory, event_class, request, response):
        sut = factory()
        profile_id = request[0] if request else None
        status = response[0]
        event = sut(self.controlbox, response, request, 1, self.command)

        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status,
                                                           event_class(self.controlbox, profile_id)))))

    def test_ControllerResetEventFactory(self):
        sut = ControllerResetEventFactory()
        flags = Mock()
        request = flags,
        status = 10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ControllerResetEvent(self.controlbox, flags))))

    def test_ControllerResetEventFactory_fail(self):
        sut = ControllerResetEventFactory()
        flags = Mock()
        request = flags,
        status = -10
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = ControllerResetEvent(self.controlbox, flags)
        assert_that(event, is_(equal_to(CommandFailedEvent(self.controlbox, self.command, status, failed))))

    def test_ContainerObjectsLoggedEvent(self):
        self.assert_container_logged(0, False)

    def test_ContainerObjectsLoggedEvent_system(self):
        self.assert_container_logged(0x02, True)

    def test_ContainerObjectsLoggedEvent_empty(self):
        self.assert_container_logged(0, False, True)

    def assert_container_logged(self, flags, system, no_values=False):
        sut = ContainerObjectsLoggedEventFactory()
        id_chain = Mock()
        request = flags, id_chain
        status, definitions = 10, [([1], 1, bytes([1])), ([2], 2, bytes([2]))] if not no_values else None
        response = status, definitions
        if no_values:
            values = None
        else:
            values = [ObjectState(system, [1], 1, self.decode_state),
                      ObjectState(system, [2], 2, self.decode_state2)]
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(equal_to(ContainerObjectsLoggedEvent(self.controlbox, system, id_chain, values))))
        if no_values:
            assert_that(self.controlbox._decode_state.mock_calls, has_length(0))
        else:
            assert_that(self.controlbox._decode_state.mock_calls,  # id_chain is not passed, just type and buffer
                        is_(equal_to([call(*definitions[0][1:]), call(*definitions[1][1:])])))

    def test_NextFreeSlotEventFactory(self):
        sut = NextFreeSlotEventFactory()
        id_chain, status = Mock(), 10
        request = id_chain,
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        assert_that(event, is_(NextFreeSlotEvent(self.controlbox, id_chain, status)))

    def test_NextFreeSlotEventFactory_fail(self):
        sut = NextFreeSlotEventFactory()
        id_chain, status = Mock(), -10
        request = id_chain,
        response = status,
        event = sut(self.controlbox, response, request, 1, self.command)
        failed = NextFreeSlotEvent(self.controlbox, id_chain, None)
        assert_that(event, is_(CommandFailedEvent(self.controlbox, self.command, status, failed)))


class ResultFromEventTest(TestCase):
    def setUp(self):
        self.sut = ControlboxApplicationAdapter.ResultFromEvent()
        self.controlbox = Mock()

    def result(self, event):
        return event.apply(self.sut)

    def test_profile_created(self):
        event = ProfileCreatedEvent(self.controlbox, 23)
        assert_that(self.result(event), is_(23))

    def test_object_state(self):
        event = ObjectStateEvent(Mock(), False, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.state))

    def test_object_deleted(self):
        event = ObjectDeletedEvent(Mock(), False, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(None))

    def test_object_updated(self):
        event = ObjectUpdatedEvent(Mock(), False, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.state))

    def test_system_object_updated(self):
        event = ObjectUpdatedEvent(Mock(), True, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.state))

    def test_object_created(self):
        event = ObjectCreatedEvent(Mock(), False, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.idchain))

    def test_profile_activated(self):
        event = ProfileActivatedEvent(Mock(), Mock())
        assert_that(self.result(event), is_(None))

    def test_next_free_slot(self):
        event = NextFreeSlotEvent(Mock(), Mock(), Mock())
        assert_that(self.result(event), event.slot)

    def test_controller_reset(self):
        event = ControllerResetEvent(Mock(), Mock())
        assert_that(self.result(event), is_(None))

    def test_command_failed(self):
        event = CommandFailedEvent(Mock(), Mock(), Mock(), Mock())
        exception = Mock()
        event.as_exception = Mock(return_value=exception)
        assert_that(self.result(event), is_(exception))
        event.as_exception.assert_called_once()

    def test_objects_logged(self):
        event = ContainerObjectsLoggedEvent(Mock(), Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.values))

    def test_system_object_state(self):
        event = ObjectStateEvent(Mock(), True, Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.state))

    def test_profile_listed(self):
        event = ProfileListedEvent(Mock(), Mock(), Mock())
        assert_that(self.result(event), is_(event.definitions))

    def test_profiles_listed(self):
        event = ProfilesListedEvent(Mock(), Mock(), Mock())
        assert_that(self.result(event), is_((event.profile_id, event.available_profile_ids)))

    def test_profiles_deleted(self):
        event = ProfileDeletedEvent(Mock(), Mock())
        assert_that(self.result(event), is_(None))


class ControlboxApplicationAdapterTest(TestCase):
    def setUp(self):
        self.controlbox = Mock()
        self.constructor_codec = Mock()
        self.state_codec = Mock()
        self.sut = ControlboxApplicationAdapter(self.controlbox, self.constructor_codec, self.state_codec)

    def test__response_handler_no_futures(self):
        sut = self.sut
        event = ObjectStateEvent(sut, False, [1], 23, {})
        sut._event_response = Mock(return_value=event)
        response = Mock()
        response.command_id = Commands.read_value
        response.parsed_request = [1], 0, 1
        response.parsed_response = 1, [1, 2, 3]

        listener = Mock()
        sut.listeners.add(listener)
        sut._response_handler(response, [])
        listener.assert_called_once_with(event)

    def test__response_handler_no_futures_no_event(self):
        sut = self.sut
        sut._event_response = Mock(return_value=None)
        response = Mock()
        response.command_id = Commands.read_value
        response.parsed_request = [1], 0, 1
        response.parsed_response = 1, [1, 2, 3]

        listener = Mock()
        sut.listeners.add(listener)
        sut._response_handler(response, [])
        listener.assert_not_called()

    def test__response_handler_wrapper_no_event(self):
        sut = self.sut
        response, listener, wrapper = Mock(), Mock(), Mock()
        sut._event_response = Mock(return_value=None)

        sut.listeners.add(listener)
        sut._response_handler_wrapper(response, wrapper)
        sut._event_response.assert_called_once_with(response, wrapper.command)
        wrapper.set_result.assert_called_once_with(None)
        listener.assert_not_called()

    def test__response_handler_wrapper_no_wrapper_no_event(self):
        sut = self.sut
        response, listener, wrapper, event = Mock(), Mock(), None, None
        sut._event_response = Mock(return_value=event)
        sut.listeners.add(listener)
        sut._response_handler_wrapper(response, wrapper)
        sut._event_response.assert_called_once_with(response, None)
        listener.assert_not_called()

    def test__response_handler_with_future(self):
        sut = self.sut
        event = ObjectStateEvent(sut, False, [1], 23, {})
        sut._event_response = Mock(return_value=event)
        event_result = 'event_result'
        sut._event_result = Mock(return_value=event_result)
        response = Mock()
        response.command_id = Commands.read_value
        response.parsed_request = [1], 0, 1
        response.parsed_response = 1, [1, 2, 3]
        listener = Mock()
        sut.listeners.add(listener)
        future = FutureValue()
        future.app_wrapper = FutureValue()
        command = 'wrapper_command'
        future.app_wrapper.command = command
        sut._response_handler(response, [future])
        listener.assert_called_once_with(event)
        assert_that(future.done(), is_(False))
        assert_that(future.app_wrapper.done(), is_(True))
        assert_that(future.app_wrapper.result(), is_(event_result))
        sut._event_result.assert_called_once_with(event)
        sut._event_response.assert_called_once_with(response, command)

    def test_event_response(self):
        command = Mock()
        response = CommandResponse([1], 2, 3)
        event = Mock()
        factory = Mock(return_value=event)
        self.sut._event_factory = Mock(return_value=factory)
        result = self.sut._event_response(response, command)
        assert_that(result, is_(event))
        self.sut._event_factory.assert_called_once_with(1)

    def test_event_factory(self):
        event = Mock()
        command_id = 23
        self.sut.event_factories = Mock()
        self.sut.event_factories.get = Mock(return_value=event)
        result = self.sut._event_factory(command_id)
        assert_that(result, is_(event))
        self.sut.event_factories.get.assert_called_once_with(command_id)

    def test_encode_state(self):
        state, encoded = Mock(), Mock()
        type = 23
        self.sut.state_codec = Mock()
        self.sut.state_codec.encode = Mock(return_value=encoded)
        result = self.sut._encode_state(type, state)
        assert_that(result, is_(encoded))
        self.sut.state_codec.encode.assert_called_once_with(type, state)

    def test_decode_state(self):
        buffer, decoded = Mock(), Mock()
        type = 23
        self.sut.state_codec = Mock()
        self.sut.state_codec.decode = Mock(return_value=decoded)
        result = self.sut._decode_state(type, buffer)
        assert_that(result, is_(decoded))
        self.sut.state_codec.decode.assert_called_once_with(type, buffer, None)

    def test_encode_config(self):
        state, encoded = Mock(), Mock()
        type = 23
        self.sut.constructor_codec = Mock()
        self.sut.constructor_codec.encode = Mock(return_value=encoded)
        result = self.sut._encode_config(type, state)
        assert_that(result, is_(encoded))
        self.sut.constructor_codec.encode.assert_called_once_with(type, state)

    def test_decode_config(self):
        buffer, decoded = Mock(), Mock()
        type = 23
        self.sut.constructor_codec = Mock()
        self.sut.constructor_codec.decode = Mock(return_value=decoded)
        result = self.sut._decode_config(type, buffer)
        assert_that(result, is_(decoded))
        self.sut.constructor_codec.decode.assert_called_once_with(type, buffer)

    def test_decode_definition(self):
        system, idchain, buffer, config = Mock(), Mock(), Mock(), Mock()
        type = 23
        defn = idchain, type, buffer
        self.sut._decode_config = Mock(return_value=config)
        result = self.sut._decode_object_definition(system, defn)
        assert_that(result, is_(equal_to(ObjectDefinition(system, idchain, type, config))))
        self.sut._decode_config.assert_called_once_with(type, buffer)

    def test_create_partial_state(self):
        id_chain, type, config = Mock(), Mock(), Mock()
        self.sut._encode_config = Mock(return_value=(bytes(), bytes()))
        assert_that(calling(self.sut.create).with_args(id_chain, type, config), raises(ValueError, 'not complete'))

    def test_create(self):
        id_chain, type, config = Mock(), Mock(), Mock()
        self.sut._encode_config = Mock(return_value=(bytes(), None))
        self.sut.controlbox.protocol.create_object = Mock(return_value=FutureValue())
        result = self.sut.create(id_chain, type, config)
        self.sut._encode_config.assert_called_once_with(type, config)
        assert_that(result.command, is_((self.sut.create, (id_chain, type, config))))

    def test_delete(self):
        id_chain, type = Mock(), Mock()
        self.sut.controlbox.protocol.delete_object = Mock(return_value=FutureValue())
        result = self.sut.delete(id_chain, type)
        assert_that(result.command, is_((self.sut.delete, (id_chain, type))))

    def test_read(self):
        id_chain, type = Mock(), Mock()
        self.sut.controlbox.protocol.read_value = Mock(return_value=FutureValue())
        result = self.sut.read(id_chain, type)
        assert_that(result.command, is_((self.sut.read, (id_chain, type))))

    def test_read_system(self):
        id_chain, type = Mock(), Mock()
        self.sut.controlbox.protocol.read_system_value = Mock(return_value=FutureValue())
        result = self.sut.read_system(id_chain, type)
        assert_that(result.command, is_((self.sut.read_system, (id_chain, type))))

    def test_write(self):
        id_chain, state = Mock(), Mock()
        self.sut._write = Mock()
        self.sut.write(id_chain, state)
        self.sut._write.assert_called_once_with(self.sut.write, False, id_chain, state, 0)

    def test_write_system(self):
        id_chain, state = Mock(), Mock()
        self.sut._write = Mock()
        self.sut.write_system(id_chain, state)
        self.sut._write.assert_called_once_with(self.sut.write_system, True, id_chain, state, 0)

    def test_profile_definitions(self):
        profile_id = Mock()
        self.sut.controlbox.protocol.list_profile = Mock(return_value=FutureValue())
        result = self.sut.profile_definitions(profile_id)
        assert_that(result.command, is_((self.sut.profile_definitions, (profile_id,))))

    def test_wrap(self):
        command, future = (), FutureResponse(Mock())
        wrapper = self.sut.wrap(command, future)
        assert_that(wrapper, is_(instance_of(FutureValue)))
        assert_that(wrapper.source, is_(self.sut))
        assert_that(future.app_wrapper, is_(wrapper))
        assert_that(wrapper.command, is_(command))

    def test_wrapper_from_empty_list(self):
        assert_that(self.sut._wrapper_from_futures([]), is_(None))

    def test_wrapper_from_non_app_future(self):
        future = FutureValue()
        assert_that(self.sut._wrapper_from_futures([future]), is_(None))

    def test_wrapper_from_future_finds_first_app_future(self):
        request = Mock()
        futures = [FutureResponse(request), FutureResponse(request), FutureResponse(request)]
        futures[1].app_wrapper = Mock()
        futures[2].app_wrapper = Mock()
        assert_that(self.sut._wrapper_from_futures(futures), is_(futures[1].app_wrapper))

    def test__write(self):
        caller, system, id_chain, state, type = Mock(), Mock(), Mock(), Mock(), Mock()
        buf, mask = Mock(), Mock()
        fn_result = Mock()
        fn, args, wrapped = Mock(return_value=fn_result), Mock(), Mock()

        command = (caller, (id_chain, state, type))
        self.sut._encode_state = Mock(return_value=(buf, mask))
        self.sut._write_args = Mock(return_value=(fn, args))
        self.sut.wrap = Mock(return_value=wrapped)
        result = self.sut._write(caller, system, id_chain, state, type)
        assert_that(result, is_(wrapped))
        fn.assert_called_with(args)
        self.sut._encode_state.assert_called_once_with(type, state)
        self.sut._write_args.assert_called_once_with(system, id_chain, type, buf, mask)
        self.sut.wrap.assert_called_once_with(command, fn_result)
        fn.assert_called_once_with(args)

    def test_write_args(self):
        self.assert_write_args(False, False, self.sut.controlbox.protocol.write_value)
        self.assert_write_args(False, True, self.sut.controlbox.protocol.write_masked_value)
        self.assert_write_args(True, False, self.sut.controlbox.protocol.write_system_value)
        self.assert_write_args(True, True, self.sut.controlbox.protocol.write_system_masked_value)

    def assert_write_args(self, system, use_mask, expected_fn):
        id_chain, type, buf = Mock(), Mock(), Mock()
        mask = Mock() if use_mask else None
        expected_args = (id_chain, type, buf) if not use_mask else (id_chain, type, buf, mask)

        fn, args = self.sut._write_args(system, id_chain, type, buf, mask)
        assert_that(fn, is_(expected_fn))
        assert_that(args, is_(equal_to(expected_args)))
