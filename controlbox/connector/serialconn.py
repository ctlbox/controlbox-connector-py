import logging

from serial import Serial, SerialException

from controlbox.conduit.base import Conduit
from controlbox.conduit.serial_conduit import SerialConduit, serial_ports
from controlbox.connector.base import ConnectorError, AbstractConnector

logger = logging.getLogger(__name__)


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

    @property
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
                logger.warn("error opening serial port %s: %s" % (self._serial.port, e))
                raise ConnectorError from e

    def _connect(self)->Conduit:
        self._try_open()
        conduit = SerialConduit(self._serial)
        return conduit

    def _try_available(self):
        n = self._serial.name
        return n in serial_ports()
