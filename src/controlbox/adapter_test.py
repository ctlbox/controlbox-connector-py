from unittest import TestCase
from unittest.mock import Mock

from hamcrest import assert_that, instance_of, is_

from controlbox.adapter import ReadSystemValueEventFactory, ObjectStateEvent, Controlbox, ReadValueEventFactory


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
        response = [1],
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
