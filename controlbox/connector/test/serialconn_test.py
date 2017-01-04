import logging
import unittest
from unittest.mock import Mock, patch
from hamcrest import calling, assert_that, raises, is_, instance_of
from serial import SerialException, time

from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent
from controlbox.conduit.serial_conduit import SerialConduit, serial_port_info, SerialDiscovery
from controlbox.connector.base import ConnectorError
from controlbox.connector.serialconn import SerialConnector, logger


class SerialConnectorTest(unittest.TestCase):

    def test_opened_serial(self):
        serial = Mock()
        serial.isOpen.return_value = True
        assert_that(calling(SerialConnector).with_args(serial), raises(ValueError))
        serial.isOpen.assert_called_once()

    def test_unopened_serial(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)
        serial.isOpen.assert_called_once()
        assert_that(conn.endpoint, is_(serial.name))

    def test_connected(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)
        serial.isOpen.reset_mock()
        assert_that(conn._connected(), is_(False))
        serial.isOpen.assert_called_once()

        serial.isOpen.reset_mock()
        serial.isOpen.return_value = True
        assert_that(conn._connected(), is_(True))
        serial.isOpen.assert_called_once()

    def test_try_open_when_already_open_does_nothing(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)
        serial.isOpen.return_value = True
        conn._try_open()
        serial.open.assert_not_called()

    def test_try_open_when_closed_calls_serial_open(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)
        conn._try_open()
        serial.open.assert_called_once()

    def test_serial_exception_is_converted_to_connect_exception(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)

        def bad_serial():
            raise SerialException("bad serial")

        serial.open.side_effect = bad_serial
        assert_that(calling(conn._try_open), raises(ConnectorError))

    def test_try_available(self):
        with patch("controlbox.connector.serialconn.serial_ports") as ports:
            serial = Mock()
            serial.isOpen.return_value = False
            conn = SerialConnector(serial)
            serial.name = "fred"
            ports.return_value = ["wilma"]
            assert_that(conn._try_available(), is_(False))
            ports.return_value = ["wilma", "fred"]
            assert_that(conn._try_available(), is_(True))

    def test_connect(self):
        serial = Mock()
        serial.isOpen.return_value = False
        conn = SerialConnector(serial)
        conduit = conn._connect()
        assert_that(conduit, is_(instance_of(SerialConduit)))
        assert_that(conduit.target, is_(serial))

    def test_disconnect(self):
        serial = Mock()
        serial.isOpen.return_value = False
        sut = SerialConnector(serial)
        conduit = Mock()
        conduit.close = Mock()
        sut._conduit = conduit
        sut.disconnect()


def log_connection_events(event):
    if isinstance(event, ResourceAvailableEvent):
        logger.info("Connected device on %s using protocol %s" %
                    (event.source, event.resource))
    elif isinstance(event, ResourceUnavailableEvent):
        logger.info("Disconnected device on %s" % event.source)
    else:
        logger.warn("Unknown event %s " % event)


def monitor():
    """ A helper function to monitor serial ports for manual testing. """
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())
    logger.info(serial_port_info())

    w = SerialDiscovery()
    w.listeners += log_connection_events
    while True:
        time.sleep(0.1)
        w.update()

if __name__ == '__main__':
    monitor()
