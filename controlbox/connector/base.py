from abc import abstractmethod

from controlbox.conduit.base import Conduit
from controlbox.protocol.async import UnknownProtocolError
from controlbox.support.events import EventSource


class ConnectorError(Exception):
    """ Indicates an error condition with a connection. """


class ConnectionNotConnectedError(ConnectorError):
    """ Indicates a connection is in the disconnected state when a connection is required. """


class ConnectionNotAvailableError(ConnectorError):
    """ Indicates the connection is not available. """


class Connector():
    """ Maintains a connection with a controller.
      A connector provides the protocol, and conduit the protocol is transported over.
    """
    @property
    @abstractmethod
    def protocol(self):
        """ Retrieves the protocol instance associated with this connector. """
        return None

    @property
    @abstractmethod
    def connected(self):
        """
        Determines if this connector is connected to its underlying resource.
        :return: True if this connector is connected to it's underlying resource. False otherwise.
        :rtype: bool
        """
        return False

    @property
    @abstractmethod
    def conduit(self)->Conduit:
        """
        Retrieves the conduit for this connection.
        If the connection is not connected, raises NotConnectedError
        :return:
        :rtype:
        """
        raise ConnectionNotConnectedError

    @property
    @abstractmethod
    def available(self)->bool:
        """ Determines if the underlying resource for this connector is available.
        :return: True if the resource is available and can be connected to.
        If this resource is connected and available is true, then it means it is a multi-instance
        resource that can support multiple connections.
        :rtype: bool
        """
        return False

    @abstractmethod
    def connect(self):
        """
        Connects this connector to the underlying resource and determines the protocol.
        If the connection is already connected,
        this method returns silently.
        Raises ConnectionError if the connection cannot be established.
        :return:
        :rtype:
        """
        pass

    @abstractmethod
    def disconnect(self):
        pass


class ConnectorMonitorListener:

    @staticmethod
    def connection_available(connector: Connector):
        """ Notifies this listener that the given connection is available, but not connected. """
        pass

    @staticmethod
    def connection_connected(connector: Connector):
        """ Notifies this listener that the given connection has been established. """
        pass

    @staticmethod
    def connection_disconnected(connector: Connector):
        """ Notifies this listener that the given connection has been disconnected. """
        pass


class ConnectorMonitor:
    """ inspects a list of Connectors, and connects any that are available but not connected.
    """

    def __init__(self, connectors: list):
        self.connectors = connectors

    def scan(self):
        for connector in self.connectors:
            if connector.available and not connector.connected:
                connector.connect()


class AbstractConnector(Connector):
    """ Manages the connection cycle, using a protocol sniffer to determine the protocol
        of the connected device.
        :param: sniffer A callable that takes the conduit and returns a protocol or raises
            UnknownProtocolError
        """

    def __init__(self, sniffer):
        self.changed = EventSource()
        self._base_conduit = None
        self._conduit = None
        self._protocol = None
        self.sniffer = sniffer

    @property
    def available(self):
        return False if self.connected else self._try_available()

    @property
    def connected(self):
        return self._protocol is not None and self._connected()

    def connect(self):
        if self.connected:
            return
        if not self.available:
            raise ConnectionNotAvailableError
        try:
            self._base_conduit = self._connect()
            self._conduit = self._base_conduit
            self._protocol = self.sniffer.determine_protocol(self._conduit)
            if self._protocol is None:
                raise UnknownProtocolError("Protocol sniffer did not return a protocol.")
        except UnknownProtocolError as e:
            raise ConnectorError() from e
        finally:   # cleanup
            if not self._protocol:
                self.disconnect()

    def disconnect(self):
        if not self._conduit:
            return
        self._disconnect()
        if self._protocol:
            if hasattr(self._protocol, 'shutdown'):
                self._protocol.shutdown()
            self._protocol = None
        if self._conduit:
            self._conduit.close()
            self._conduit = None

    @abstractmethod
    def _connect(self) -> Conduit:
        """ Template method for subclasses to perform the connection.
            If connection is not possible, an exception should be thrown
        """
        raise NotImplementedError

    @abstractmethod
    def _try_available(self):
        """ Determine if this connection is available. This method is only called when
            the connection is disconnected.
        :return: True if the connection is available or False otherwise.
        :rtype: bool
        """
        raise NotImplementedError

    @abstractmethod
    def _disconnect(self):
        """ perform any actions needed on disconnection.
        The base class takes care of disposing the protocol and the conduit, which happens
        after this method has been called.
        """
        raise NotImplementedError

    @abstractmethod
    def _connected(self):
        raise NotImplementedError

    @property
    def conduit(self):
        self.check_connected()
        return self._conduit

    @property
    def protocol(self):
        self.check_connected()
        return self._protocol

    def check_connected(self):
        if not self.connected:
            raise ConnectionNotConnectedError
