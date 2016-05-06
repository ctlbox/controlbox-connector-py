import unittest
from unittest.mock import Mock, patch, DEFAULT

from hamcrest import is_, assert_that, instance_of, raises, calling

from controlbox.conduit.socket_conduit import SocketConduit
from controlbox.connector.base import ConnectorError
from controlbox.connector.socketconn import SocketConnector


class SocketConnectorTest(unittest.TestCase):
    def test_constructor(self):
        sut = SocketConnector(1, 2)
        assert_that(sut._sock_args, is_(1))
        assert_that(sut._connect_args, is_(2))

    def test_endpoint(self):
        sut = SocketConnector(Mock(), Mock())
        assert_that(sut.endpoint, is_(sut._connect_args))

    def test_successful_connect(self):
        sock_args = (1, 2)
        connect_args = (3, 4)
        sut = SocketConnector(sock_args, connect_args)
        # patch the socket module
        with patch('controlbox.connector.socketconn.socket', socket=DEFAULT) as socket:
            socket.error = OSError
            sock_instance = Mock()
            socket.socket = Mock()
            socket.socket.return_value = sock_instance
            conduit = sut._connect()
            assert_that(conduit, is_(instance_of(SocketConduit)))
            assert_that(conduit.target, is_(socket.socket.return_value))
            socket.socket.assert_called_once_with(*sock_args)
            sock_instance.connect.assert_called_once_with(connect_args)

    def test_unsuccessful_connect(self):
        sock_args = (1, 2)
        connect_args = (3, 4)
        sut = SocketConnector(sock_args, connect_args)
        # patch the socket module
        with patch('controlbox.connector.socketconn.socket', socket=DEFAULT) as socket:
            socket.error = OSError
            sock_instance = Mock()
            socket.socket = Mock()
            socket.socket.return_value = sock_instance
            sock_instance.connect.side_effect = socket.error("cannot connect to imagination land")

            assert_that(calling(sut._connect), raises(ConnectorError))
            socket.socket.assert_called_once_with(*sock_args)
            sock_instance.connect.assert_called_once_with(connect_args)

    def test_available(self):
        sut = SocketConnector(1, 2)
        assert_that(sut._try_available(), is_(True))
