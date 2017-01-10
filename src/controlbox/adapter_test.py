from unittest import TestCase
from unittest.mock import Mock

from hamcrest import assert_that, instance_of, is_, raises, calling, equal_to

from controlbox.adapter import ReadSystemValueEventFactory, ObjectStateEvent, ReadValueEventFactory, \
    ControlboxApplicationAdapter, ControlboxApplicationEvent, ObjectEvent, ProfileEvent, ObjectCreatedEvent, \
    ObjectDeletedEvent, ObjectUpdatedEvent, ProfileListedEvent, ProfileCreatedEvent, ProfileDeletedEvent, \
    ProfileActivatedEvent, ControllerResetEvent, ContainerObjectsLoggedEvent, ProfilesListedEvent, CommandFailedEvent, \
    FailedOperationError, ObjectState
from controlbox.protocol.async import FutureValue, FutureResponse
from controlbox.protocol.controlbox import Commands


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
                pass

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
                pass

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

    def test_visitor_sytem(self):
        visitor = Mock()
        sut = ObjectStateEvent(Mock(), True, Mock(), Mock(), Mock())
        sut.apply(visitor)
        visitor.system_object_state.assert_called_once_with(sut)


class ProfileEventTest(TestCase):
    @staticmethod
    def assert_profile_event(sut, controlbox, profile_id):
        assert_that(sut.controlbox, is_(controlbox))
        assert_that(sut.profile_id, is_(profile_id))

    def test_constructor(self):
        class TestEvent(ProfileEvent):
            def apply(self, visitor: 'ControlboxEventVisitor'):
                pass

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
    def test_ReadValueEventFactory(self):
        pass


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

    def test_wrap(self):
        command, future = (), FutureResponse(Mock())
        wrapper = self.sut.wrap(command, future)
        assert_that(wrapper, is_(instance_of(FutureValue)))
        assert_that(wrapper.source, is_(self.sut))
        assert_that(future.app_wrapper, is_(wrapper))
        assert_that(wrapper.command, is_(command))

    def test_wrapper_from_non_app_future(self):
        future = FutureValue()
        assert_that(self.sut._wrapper_from_futures([future]), is_(None))

    def test_wrapper_from_future_finds_first_app_future(self):
        request = Mock()
        futures = [FutureResponse(request), FutureResponse(request), FutureResponse(request)]
        futures[1].app_wrapper = Mock()
        futures[2].app_wrapper = Mock()
        assert_that(self.sut._wrapper_from_futures(futures), is_(futures[1].app_wrapper))

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
