import unittest
from unittest.mock import Mock

from hamcrest import assert_that, is_, raises, calling, instance_of

from controlbox.conduit.base import StreamErrorReportingConduit
from controlbox.connector.base import ConnectorEvent, ConnectorConnectedEvent, ConnectorDisconnectedEvent, Connector, \
    AbstractConnector, ConnectionNotAvailableError, ConnectorError, ConnectionNotConnectedError, DelegateConnector, \
    CloseOnErrorConnector, ProtocolConnector
from controlbox.protocol.async import UnknownProtocolError
from controlbox.support.events import EventSource


class ConnectorEventsTest(unittest.TestCase):

    def test_connector_event(self):
        self.assert_event(ConnectorEvent)
        self.assert_event(ConnectorConnectedEvent)
        self.assert_event(ConnectorDisconnectedEvent)

    def assert_event(self, event_class):
        source = Mock()
        event = event_class(source)
        assert_that(event.connector, is_(source))
        source.assert_not_called()


class ConnectorTest(unittest.TestCase):
    def test_abstract_methods(self):
        sut = Connector()
        assert_that(sut.events, is_(instance_of(EventSource)))
        assert_that(calling(sut.disconnect), raises(NotImplementedError))
        assert_that(calling(sut.connect), raises(NotImplementedError))
        # testing properties is a little strange since the property access has to be deffered
        # or it will throw an exception outside the scope of the assert test.
        assert_that(calling(getattr).with_args(sut, 'endpoint'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'connected'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'available'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'conduit'), raises(NotImplementedError))


class AbstractTestConnector(AbstractConnector):
    """
    patching properties is a pain, so we just implement them here as attributes
    """
    def __init__(self):
        super().__init__()
        self._connected_value = False
        self._available_value = True

    @property
    def connected(self):
        return self._connected_value

    @property
    def available(self):
        return self._available_value


class AbstractConnectorTest(unittest.TestCase):
    def test_constructor(self):
        sut = AbstractConnector()
        assert_that(sut.events, is_(instance_of(EventSource)))
        assert_that(sut._conduit, is_(None))

    def test_abstract_methods(self):
        sut = AbstractConnector()
        assert_that(calling(sut._connect), raises(NotImplementedError))
        assert_that(calling(sut._try_available), raises(NotImplementedError))
        assert_that(calling(sut._disconnect), raises(NotImplementedError))

    def test_conduit(self):
        sut = AbstractConnector()
        conduit = Mock()
        sut._conduit = conduit
        sut.check_connected = Mock()
        assert_that(sut.conduit, is_(conduit))
        sut.check_connected.assert_called_once()

    def test_connected_no_conduit(self):
        sut = AbstractConnector()
        assert_that(sut._connected(), is_(False))

    def connected_conduit_open(self, open):
        sut = AbstractConnector()
        sut._conduit = Mock()
        sut._conduit.open = Mock(return_value=open)
        assert_that(sut._connected(), is_(open))

    def test_connected_conduit_open(self):
        self.connected_conduit_open(True)

    def test_connected_conduit_not_open(self):
        self.connected_conduit_open(False)

    def test_check_connected(self):
        sut = AbstractTestConnector()
        sut._connected_value = True
        sut.check_connected()

    def test_check_connected_false(self):
        sut = AbstractTestConnector()
        sut._connected_value = False
        assert_that(calling(sut.check_connected), raises(ConnectionNotConnectedError))

    def test_available_connected(self):
        class LocalConnector(AbstractConnector):
            @property
            def connected(self):
                return True

        sut = LocalConnector()
        assert_that(sut.available, is_(False))

    def test_available_not_connected(self):
        class LocalConnector(AbstractConnector):
            def __init__(self):
                super().__init__()

            @property
            def connected(self):
                return False

        sut = LocalConnector()
        sut._try_available = Mock(return_value=True)
        assert_that(sut.available, is_(True))
        sut._try_available.assert_called_once()

    def test_connected_with_conduit(self):
        sut = AbstractConnector()
        sut._conduit = object()
        sut._connected = Mock(return_value=True)
        assert_that(sut.connected, is_(True))
        sut._connected = Mock(return_value=False)
        assert_that(sut.connected, is_(False))

    def test_connect_already_connected(self):
        sut = AbstractTestConnector()
        sut._connected_value = True
        sut._available_value = False
        sut.connect()
        # no exception is success

    def test_connect_not_available(self):
        sut = AbstractTestConnector()
        sut._connected_value = False
        sut._available_value = False
        assert_that(calling(sut.connect), raises(ConnectionNotAvailableError))

    def test_connect(self):
        sut = AbstractTestConnector()
        sut.events = Mock()
        sut._connected_value = False
        sut._available_value = True
        sut._connect = Mock(return_value=object())
        # when
        sut.connect()
        # then
        sut._connect.assert_called_once()
        sut.events.fire.assert_called_once_with(ConnectorConnectedEvent(sut))

    def test_connect_exception(self):
        sut = AbstractTestConnector()
        sut.events = Mock()
        sut._connected_value = False
        sut._available_value = True
        sut._connect = Mock(side_effect=ConnectorError())
        sut.disconnect = Mock()
        # when
        assert_that(calling(sut.connect), raises(ConnectorError))
        # then
        sut._connect.assert_called_once()
        sut._connect.assert_called_once()
        sut.events.assert_not_called()
        sut.disconnect.assert_called_once()

    def test_disconnect(self):
        sut = AbstractConnector()
        sut.events = Mock()
        conduit = Mock()
        sut._conduit = conduit
        sut._disconnect = Mock()
        sut.disconnect()
        conduit.close.assert_called_once()
        assert_that(sut._conduit, is_(None))
        sut.events.fire.assert_called_once_with(ConnectorDisconnectedEvent(sut))

    def test_disconnect_already_disconnected(self):
        sut = AbstractConnector()
        sut.events = Mock()
        sut._conduit = None
        sut._disconnect = Mock()
        sut.disconnect()
        assert_that(sut._conduit, is_(None))
        sut.events.fire.assert_not_called()
        sut._disconnect.assert_not_called()


class MockConnector(Connector):
    """ mock out all the properties """
    def __init__(self):
        super().__init__()
        self._available = Mock()
        self._connected = Mock()
        self._conduit = Mock()
        self._endpoint = Mock()

    @property
    def available(self):
        return self._available()

    @property
    def connected(self):
        return self._connected()

    @property
    def endpoint(self):
        return self._endpoint()

    @property
    def conduit(self):
        return self._conduit()


class DelegateConnectorTest(unittest.TestCase):
    def test_constructor(self):
        delegate = object()
        sut = DelegateConnector(delegate)
        assert_that(sut.delegate, is_(delegate))

    def delegate(self):
        delegate = MockConnector()
        sut = DelegateConnector(delegate)
        return sut

    def test_available(self):
        sut = self.delegate()
        sut.delegate._available.return_value = "abcd"
        assert_that(sut.available, is_("abcd"))
        sut.delegate._available.assert_called_once()

    def test_conduit(self):
        sut = self.delegate()
        sut.delegate._conduit.return_value = "abcd"
        assert_that(sut.conduit, is_("abcd"))
        sut.delegate._conduit.assert_called_once()

    def test_endpoint(self):
        sut = self.delegate()
        sut.delegate._endpoint.return_value = "abcd"
        assert_that(sut.endpoint, is_("abcd"))
        sut.delegate._endpoint.assert_called_once()

    def test_connected(self):
        sut = self.delegate()
        sut.delegate._connected.return_value = "abcd"
        assert_that(sut.connected, is_("abcd"))
        sut.delegate._connected.assert_called_once()

    def test_connect(self):
        sut = self.delegate()
        sut.delegate.connect = Mock(return_value="abcd")
        sut.connect()
        sut.delegate.connect.assert_called_once()

    def test_disconnect(self):
        sut = self.delegate()
        sut.delegate.disconnect = Mock(return_value="abcd")
        sut.disconnect()
        sut.delegate.disconnect.assert_called_once()


class CloseOnErrorConnectorTest(unittest.TestCase):
    def test_constructor(self):
        delegate = object()
        sut = CloseOnErrorConnector(delegate)
        assert_that(sut.conduit, is_(None))
        assert_that(sut.delegate, is_(delegate))

        assert_that(sut.connected, is_(False))
        assert_that(sut.conduit, is_(None))

    def test_connected(self):
        sut = CloseOnErrorConnector(None)
        sut._conduit = object()
        assert_that(sut.connected, is_(True))

    def test_connect_already_connected(self):
        delegate = Mock()
        sut = CloseOnErrorConnector(delegate)
        sut._conduit = object()
        sut.connect()
        delegate.connect.assert_not_called()

    def test_connect(self):
        delegate = Mock()
        sut = CloseOnErrorConnector(delegate)
        sut.connect()
        delegate.connect.assert_called_once()
        conduit = sut.conduit
        assert_that(conduit, is_(instance_of(StreamErrorReportingConduit)))
        assert_that(sut.conduit, is_(sut._conduit))

    def test_disconnect(self):
        delegate = Mock()
        sut = CloseOnErrorConnector(delegate)
        sut._conduit = object()
        sut.disconnect()
        assert_that(sut._conduit, is_(None))
        delegate.disconnect.assert_called_once()

    def test_on_stream_exception(self):
        delegate = Mock()
        sut = CloseOnErrorConnector(delegate)
        sut.disconnect = Mock()
        sut.on_stream_exception()
        sut.disconnect.assert_called_once()


class ProtocolConnectorTest(unittest.TestCase):
    def test_constructor(self):
        delegate = Mock()
        sniffer = Mock()
        sut = ProtocolConnector(delegate, sniffer)
        assert_that(sut.delegate, is_(delegate))
        assert_that(sut._sniffer, is_(sniffer))
        assert_that(sut._protocol, is_(None))
        assert_that(sut.connected, is_(False))

        delegate.events.add.assert_called()  # with(weakref.ref(sut._delegate_events))

    def test_delegate_events_disconnect(self):
        sut = ProtocolConnector(Mock(), None)
        sut.disconnect = Mock()
        sut._delegate_events(ConnectorDisconnectedEvent(None))
        sut.disconnect.assert_called_once()

    def test_delegate_events_connect(self):
        sut = ProtocolConnector(Mock(), None)
        sut.disconnect = Mock()
        sut._delegate_events(ConnectorConnectedEvent(None))
        sut.disconnect.assert_not_called()

    def test_connect_already_connected(self):
        delegate = Mock()
        sut = ProtocolConnector(delegate, None)
        sut._protocol = object()
        delegate.connect = Mock()
        sut.connect()
        delegate.connect.assert_not_called()

    def test_connect(self):
        self.connect_protocol(Mock(return_value=Mock()), False)

    def test_connect_none(self):
        self.connect_protocol(Mock(return_value=None), True)

    def test_connect_unkown_protocol(self):
        self.connect_protocol(Mock(side_effect=UnknownProtocolError), True)

    def connect_protocol(self, sniffer, protocol_except):
        delegate = Mock()
        delegate.conduit = Mock()
        delegate.disconect = Mock()

        def connected():
            delegate.connected = True

        delegate.connect = Mock(side_effect=connected)
        sut = ProtocolConnector(delegate, sniffer)
        if protocol_except:
            assert_that(calling(sut.connect), raises(ConnectorError))
            delegate.disconnect.assert_called_once()
            assert_that(sut.connected, is_(False))
        else:
            sut.connect()
            delegate.disconnect.assert_not_called()
            assert_that(sut.connected, is_(True))
            assert_that(sut.protocol, is_(sniffer.return_value))

        delegate.connect.assert_not_called()
        sniffer.assert_called_with(delegate.conduit)

    def test_disconnect_no_protocol(self):
        """ disconnect always calls the delegate even if not connected """
        delegate = Mock()
        sut = ProtocolConnector(delegate, None)
        delegate.disconnect = Mock()
        # when
        sut.disconnect()
        # then
        delegate.disconnect.assert_called_once()

    def test_disconnect_protocol(self):
        self.disconnect(False)

    def test_disconnect_protocol_with_shutdown(self):
        self.disconnect(True)

    def disconnect(self, with_shutdown):
        """ sets up a protocol for disconnection, with optional shutdown method """
        delegate = Mock()
        sut = ProtocolConnector(delegate, None)

        protocol = Mock()
        if with_shutdown:
            protocol.shutdown = Mock()
        else:
            del protocol.shutdown

        sut._protocol = protocol
        delegate.disconnect = Mock()
        # when
        sut.disconnect()
        # then
        assert_that(sut.protocol, is_(None))
        delegate.disconnect.assert_called_once()
        if with_shutdown:
            protocol.shutdown.assert_called_once()
