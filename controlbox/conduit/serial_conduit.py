"""
Implements a conduit over a serial port.
"""

import logging
import re

import serial
from serial.tools import list_ports

from controlbox.conduit.base import Conduit
from controlbox.conduit.discovery import PolledResourceDiscovery

logger = logging.getLogger(__name__)




class SerialConduit(Conduit):
    """
    A conduit that provides comms via a serial port.
    """

    def __init__(self, ser: serial.Serial):
        self.ser = ser
        # patch flushing since this causes a lockup if the serial is disconnected during
        # the flush.
        ser.flush = self._no_flush

    def _no_flush(self, *args, **kwargs):
        pass

    @property
    def target(self):
        return self.ser

    @property
    def input(self):
        return self.ser

    @property
    def output(self):
        return self.ser

    @property
    def open(self) -> bool:
        return self.ser.isOpen()

    def close(self):
        self.ser.close()


def serial_ports():
    """
    Returns a generator for all available serial port device names.
    """
    for port in serial_port_info():
        yield port[0]


def serial_connector_factory(*args, **kwargs):
    """
    Creates a factory function that connects via the serial port.
    All arguments are passed directly to `serial.Serial`
    :return: a factory for serial connectors
    """
    ser = serial.Serial(*args, **kwargs)

    def open_serial_connector():
        return SerialConduit(ser)

    return open_serial_connector


arduino_devices = {
    (r"%mega2560\.name%.*", "USB VID\:PID=2341\:0010.*"): "Arduino Mega2560",
    (r"Arduino.*Leonardo.*", "USB VID\:PID=2341\:8036.*"): "Arduino Leonardo",
    (r'Arduino Uno.*', 'USB VID:PID=2341:0043.*'): "Arduino Uno"
}

particle_devices = {
    (r"Spark Core.*Arduino.*", "USB VID\:PID=1D50\:607D.*"): "Spark Core",
    (r".*Photon.*", "USB VID\:PID=2b04\:c006.*"): "Particle Photon",
    (r".*P1.*", "USB VID\:PID=2b04\:c008.*"): "Particle P1",
    (r".*Electron.*", "USB VID\:PID=2b04\:c00a.*"): "Particle Electron"
}

known_devices = dict((k, v) for d in [arduino_devices, particle_devices] for k, v in d.items())


# 'USB VID:PID=2B04:C006 SER=00000000050C LOCATION=20-5'
def matches(text, regex):
    """
    >>> bool(matches("A", "a"))
    True
    >>> bool(matches("A", "b"))
    False
    >>> bool(matches("USB VID:PID=2B04:C006 SER=00000000050C LOCATION=20-5", "USB VID\:PID=2b04\:c006.*"))
    True
    """
    return re.match(regex, text, flags=re.IGNORECASE)


def is_recognised_device(p):
    """
    >>> is_recognised_device(("abc", "Blah", "USB VID:PID=2B04:C006 SER=00000000050C"))
    True
    """
    port, name, desc = p
    for d in known_devices.keys():
        # used to match on name and desc, but under linux only desc is
        # returned, compard
        if matches(desc, d[1]):
            return True  # to name and desc on windows
    return False


def find_recognised_device_ports(ports):
    for p in ports:
        if is_recognised_device(p):
            yield p


def serial_port_info():
    """
    :return: a tuple of serial port info tuples,
    :rtype:
    """
    return tuple(list_ports.comports())


def detect_port(port):
    """
    attempts to detect the given serial port. If the port is not auto, it is returned as is.
    otherwise, the first port found is returned.
    """
    if port == "auto":
        all_ports = serial_port_info()
        ports = tuple(find_recognised_device_ports(all_ports))
        if not ports:
            raise ValueError("Could not find a compatible device in available ports. %s" % repr(all_ports))
        return ports[0]
    return port


class SerialDiscovery(PolledResourceDiscovery):
    """ Monitors local serial ports for known devices. """

    def __init__(self):
        super().__init__()

    def _is_allowed(self, key, device: serial.tools.list_ports_common.ListPortInfo):
        return is_recognised_device(device)

    def _fetch_available(self):
        """ computes the available serial port/device map from a list of tuples (port, name, desc). """
        all_ports = tuple(self._fetch_ports())
        available = {p.device: p for p in all_ports}
        return available

    def _fetch_ports(self):
        return serial_port_info()
