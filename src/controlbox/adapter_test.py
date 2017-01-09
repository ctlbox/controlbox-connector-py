from unittest import TestCase
from unittest.mock import Mock

from hamcrest import assert_that, instance_of, is_

from controlbox.adapter import ReadSystemValueEventFactory, ObjectStateEvent, Controlbox, ReadValueEventFactory, \
    ControlboxApplicationAdapter
from controlbox.protocol.async import FutureValue
from controlbox.protocol.controlbox import Commands


class ControlboxTest(TestCase):

    def test_connector_protocol(self):
        connector = Mock()
        protocol = "123"
        connector.protocol = protocol
        sut = Controlbox(connector)
        self.assertEqual(sut.protocol, protocol)


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
