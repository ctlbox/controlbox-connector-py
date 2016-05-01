import logging
import socket

from controlbox.conduit.base import Conduit
from controlbox.conduit.socket_conduit import SocketConduit
from controlbox.connector.base import AbstractConnector, ConnectorError

logger = logging.getLogger(__name__)


class TCPServerEndpoint:
    """
    Describes a TCP server endpoint.
    At least one of name or ip_address should be given. If both are given, the ip_address is used
    to connect.
    """
    def __init__(self, hostname, ip_address, port):
        self.hostname = hostname
        self.ip_address = ip_address
        self.port = port


class SocketConnector(AbstractConnector):
    """
    A connector that communicates data via a socket
    """
    def __init__(self, sock_args, connect_args):
        """
        Creates a new serial connector.
        :param sock The socket that defines the socket protocol to connect to.
        :param connect_args connection arguments for the socket.connect() call
        """
        super().__init__()
        self._sock_args = sock_args
        self._connect_args = connect_args

    def endpoint(self):
        return self._connect_args

    def _connect(self)->Conduit:
        try:
            sock = socket.socket(*self._sock_args)
            sock.connect(*self._connect_args)
            logger.info("opened socket to %s" % self._connect_args)
            return SocketConduit(sock)
        except socket.error as e:
            logger.warn("error opening socket to %s: %s" % self._connect_args, e)
            raise ConnectorError from e

    def _disconnect(self):
        pass

    def _try_available(self):
        # could try pinging the host?
        return True
