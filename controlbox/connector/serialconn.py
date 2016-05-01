import logging
import time

from serial import Serial, SerialException
from serial.tools.list_ports_common import ListPortInfo

from controlbox.conduit.base import Conduit
from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent
from controlbox.conduit.serial_conduit import SerialConduit, serial_ports, serial_port_info, SerialDiscovery
from controlbox.connector.base import ConnectorError, AbstractConnector
from controlbox.support.mixins import __str__

logger = logging.getLogger(__name__)

# make ListPortInfo printable
ListPortInfo.__str__ = __str__


class SerialConnector(AbstractConnector):
    """
    Implements a connector that communicates data via a Serial link.
    """
    def __init__(self, serial: Serial):
        """
        Creates a new serial connector.
        :param serial - the serial object defining the serial port to connect to.
                The serial instance should not be open.
        """
        super().__init__()
        self._serial = serial
        if serial.isOpen():
            raise ValueError("serial object should be initially closed")

    def endpoint(self):
        return self._serial

    def _connected(self):
        return self._serial.isOpen()

    def _try_open(self):
        """
        :return: True if the serial port is connected.
        :rtype: bool
        """
        s = self._serial
        if not s.isOpen():
            try:
                s.open()
                logger.info("opened serial port %s" % self._serial.port)
            except SerialException as e:
                logger.warn("error opening serial port %s: %s" % self._serial.port, e)
                raise ConnectorError from e

    def _connect(self)->Conduit:
        self._try_open()
        conduit = SerialConduit(self._serial)
        return conduit

    def _disconnect(self):
        """ No special actions needed """

    def _try_available(self):
        n = self._serial.name
        try:
            return n in serial_ports()
        except SerialException:
            return False


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
