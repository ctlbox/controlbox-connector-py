import unittest
from unittest.mock import patch, Mock
from hamcrest import assert_that, equal_to, is_, instance_of, calling, raises
from mockito import verify
from serial.tools.list_ports_common import ListPortInfo

from controlbox.conduit.serial_conduit import detect_port, SerialDiscovery, serial_connector_factory, SerialConduit, \
    serial_ports, find_recognised_device_ports
from controlbox.conduit.test.async_test import AsyncConnectorTest
from controlbox.config.config import configure_module
import serial
import sys

port = None
virtualPortPair = None
invalid_port = "ABC___not_found"
arduino_port_detect = None
baud = 57600

configure_module(sys.modules[__name__])


class ConnectorSerialIntegrationTest(unittest.TestCase):

    def __init__(self, methodName='runTest'):
        super().__init__(methodName)
        self.connection = None

    def setup(self):
        self.connection = None

    def tearDown(self):
        self.connection and self.connection.close()

    def test_detect_port_given(self):
        assert_that(detect_port("COM2"), is_(equal_to("COM2")))

    @unittest.skipUnless(arduino_port_detect, "arduino_port_detect not defined")
    def test_detect_port_not_given(self):
        assert_that(detect_port("auto"), is_(equal_to(arduino_port_detect)))

    test_detect_port_not_given.os = 'windows'

    def test_factory_method_returns_callable(self):
        try:
            factory = serial_connector_factory(invalid_port, baud, timeout=1)
            assert callable(factory)
        except Exception:
            pass

    def test_invalid_arguments_fail(self):
        try:
            factory = serial_connector_factory(invalid_port, baud, timeout=1)
            self.assertRaises(serial.SerialException, factory)
        except Exception:
            pass

    @unittest.skipUnless(port, "arduino port not defined")
    def test_read_serial(self):
        p = detect_port(port)
        factory = serial_connector_factory(p, baud, timeout=1)
        self.connection = factory()
        input = self.connection.input
        line = input.read()
        self.assertIsNotNone(line)

    @unittest.skipUnless(port, "arduino port not defined")
    def test_write_serial(self):
        p = detect_port(port)
        factory = serial_connector_factory(p, baud, timeout=1)
        self.connection = factory()
        self.connection.output.write("abc".encode())

    @unittest.skip("cannot get writelines to work - raises TypeError: 'int' object is not iterable")
    def test_writelines_serial(self):
        factory = serial_connector_factory(port, baud, timeout=1)
        self.connection = factory()
        s = "abc".encode()
        self.connection.output.writelines(s)


@unittest.skipUnless(virtualPortPair, "need virtual serial ports defined")
class VirtualPortSerialTestCase(AsyncConnectorTest, unittest.TestCase):

    def createConnections(self):
        return [(lambda port: serial_connector_factory(port, baud, timeout=0.1)())(p) for p in virtualPortPair]

    def test_connections_are_open(self):
        for c in self.connections:
            self.assertTrue(c.open, "connection %s should be open" % c)

    def test_comms(self):
        self.assertWriteRead("some line\nand another", self.connections)
        self.assertWriteRead("more stuff\n", self.connections)
        self.assertWriteRead("reverse direction\nline\n",
                             self.connections[::-1])


arduino_device = (r"Arduino Leonardo", r"USB VID:PID=2341:8036")


class CallableMock(object):
    """ a work-around for mocks not being callable. https://code.google.com/p/mockito-python/issues/detail?id=5 """

    def __init__(self, mock):
        self.mock = mock

    def __call__(self, *args, **kwargs):
        return self.mock.__call__(*args, **kwargs)

    def __getattr__(self, method_name):
        return self.mock.__getattr__(method_name)


def verify_disconnected(mock):
    verify(mock).__exit__()


def verify_connected(mock):
    verify(mock).__enter__()


test_ports = [("port", "name", "desc")]


class SerialDiscoveryTest(unittest.TestCase):

    def test_discovery_allowed(self):
        sut = SerialDiscovery()
        device = ('abcd', 'blah', 'USB VID:PID=2341:0043 blah blah')
        assert_that(sut._is_allowed('abcd', device), is_(True))

    def test_discovery_not_allowed(self):
        sut = SerialDiscovery()
        device = ('abcd', 'blah', 'USB VID:PID=234X:0043')
        assert_that(sut._is_allowed('abcd', device), is_(False))

    def test_fetch_available(self):
        sut = SerialDiscovery()
        ports = [ListPortInfo("port")]
        sut._fetch_ports = Mock(return_value=ports)
        assert_that(sut._fetch_available(), is_({'port': ports[0]}))

    @patch('serial.tools.list_ports.comports', return_value=test_ports)
    def test_fetch_ports(self, list_ports_mock):
        sut = SerialDiscovery()
        ports = sut._fetch_ports()
        assert_that(ports, is_(tuple(test_ports)))
        list_ports_mock.assert_called_once()


class SerialConduitTest(unittest.TestCase):
    def test(self):
        serial = Mock()
        sut = SerialConduit(serial)

        assert_that(sut.target, is_(serial))
        assert_that(sut.input, is_(serial))
        assert_that(sut.output, is_(serial))

        serial.isOpen = Mock(return_value=True)
        assert_that(sut.open, is_(True))
        serial.isOpen.assert_called_once()

        serial.close = Mock()
        sut.close()
        serial.close.assert_called_once()

    def test_function_serial_ports(self):
        with patch('controlbox.conduit.serial_conduit.serial_port_info') as mock:
            mock.return_value = [(1, "1"), (2, "2")]
            ports = [p for p in serial_ports()]
            assert_that(ports, is_([1, 2]))

    @patch('controlbox.conduit.serial_conduit.serial')
    def test_function_serial_connector_factory(self, serial):
        """ the factory creates a new serial instance and passes that to a new conduit. """
        factory = serial_connector_factory(1, a="b")
        conduit = factory()
        serial.Serial.assert_called_once_with(1, a="b")
        assert_that(conduit, is_(instance_of(SerialConduit)))
        assert_that(conduit.target, is_(serial.Serial.return_value))

    def test_function_find_recognised_device_ports(self):
        known = ["abc", "Blah", "USB VID:PID=2B04:C006 SER=00000000050C"]
        generator = find_recognised_device_ports([("1", "2", "3"), known])
        result = tuple(generator)
        assert_that(result, is_((known,)))

    def test_function_detect_port_non_auto(self):
        assert_that(detect_port("abc"), is_("abc"))

    def test_function_detect_port_auto_none(self):
        with patch('controlbox.conduit.serial_conduit.serial_port_info') as mock:
            mock.return_value = tuple()
            assert_that(calling(detect_port).with_args("auto"), raises(ValueError))

    def test_function_detect_port_auto_some(self):
        with patch('controlbox.conduit.serial_conduit.serial_port_info') as mock:
            mock.return_value = tuple([
                ("abc", "Blah", "not me"),
                ("def", "Blah", "USB VID:PID=2B04:C006 SER=00000000050C"),
                ("3", "Blah", "USB VID:PID=2B04:C006 SER=00000000050C")
            ])
            assert_that(detect_port("auto"), is_(mock.return_value[1]))
