import unittest
from unittest.mock import Mock, patch

from hamcrest import assert_that, calling, instance_of, is_, raises
from serial.tools.list_ports_common import ListPortInfo

from controlbox.conduit.serial_conduit import SerialConduit, SerialDiscovery, detect_port, \
    find_recognised_device_ports, serial_connector_factory, serial_ports

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

    def test_assigns_flush_to_noflush(self):
        ser = Mock()
        sut = SerialConduit(ser)
        assert_that(ser.flush, is_(sut._no_flush))
        ser.flush()
