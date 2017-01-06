import socket
import unittest
from multiprocessing import Semaphore
from multiprocessing.context import Process
from unittest.mock import Mock, call

from hamcrest import assert_that, is_

from controlbox.conduit.socket_conduit import SocketConduit


class EchoServer:  # pragma: no cover - run as an external process
    def __init__(self, host, port, mutex):
        backlog = 5
        size = 1024
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setblocking(True)
        try:
            s.bind((host, port))
            s.listen(backlog)
        finally:
            mutex.release()
        client, address = s.accept()

        data = client.recv(size)
        if data:
            client.send(data)
        client.shutdown(socket.SHUT_RDWR)
        client.close()
        s.close()


class HelloServer:  # pragma: no cover - run as an external process
    def __init__(self, host, port, mutex):
        backlog = 5
        size = 1024
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setblocking(True)
        try:
            s.bind((host, port))
            s.listen(backlog)
        finally:
            mutex.release()
        client, address = s.accept()

        msg = b"hello"
        client.sendall(msg)
        client.shutdown(socket.SHUT_WR)
        data = client.recv(size)
        client.shutdown(socket.SHUT_RD)
        client.close()
        s.close()

        if data != msg:
            raise ValueError("exoected hello, got %s " % data)


server_port = 51234
server_host = '127.0.0.1'


class ClientSocketTestCase(unittest.TestCase):
    """ functional test for the socket connectors. Creates both a server factory and a client factory, and verifies that
        data sent from one is received by the other, and that closing the socket from either end is gracefully handled.
    """

    def start_server(self, server_type):
        mutex = Semaphore()
        mutex.acquire()
        thread = Process(target=server_type, args=(server_host, server_port, mutex))
        # thread.setDaemon(True)
        thread.start()
        mutex.acquire()
        return thread

    def test_write_conduit(self):
        thread = self.start_server(EchoServer)
        sock = socket.socket()
        sock.connect((server_host, server_port))
        conduit = SocketConduit(sock)
        try:
            data = b'abcde'
            conduit.output.write(data)
            conduit.output.flush()
            result = conduit.input.read()
            assert_that(result, is_(data))
        finally:
            conduit.close()
            thread.join()

    def test_read_conduit(self):
        thread = self.start_server(HelloServer)
        sock = socket.socket()
        sock.setblocking(True)
        sock.settimeout(5)
        sock.connect((server_host, server_port))
        try:
            conduit = SocketConduit(sock)
            data = b'hello'
            result = conduit.input.read()
            conduit.output.write(data)
            conduit.output.flush()
            conduit.close()
            assert_that(result, is_(data))
            thread.join()
        except Exception as e:  # pragma: no cover
            print(e)
            raise e


class SocketConduitTest(unittest.TestCase):
    def test(self):
        sock = Mock()
        input = Mock()
        output = Mock()

        def makefile(mode):
            if mode == "rb":
                return input
            if mode == "wb":        # pragma no cover - bug doesn't track this call
                return output

        sock.makefile.side_effect = makefile

        sut = SocketConduit(sock)
        sock.makefile.assert_has_calls(
            [call("rb"), call("wb")]
        )
        sock.fileno.return_value = 1
        assert_that(sut.open, is_(True))
        sock.fileno.return_value = -1
        assert_that(sut.open, is_(False))

        assert_that(sut.target, is_(sock))
        assert_that(sut.input, is_(input))
        assert_that(sut.output, is_(output))

        input.close.assert_not_called()
        output.close.assert_not_called()

        def shutdown_error(arg):
            raise OSError("summat bad happened")

        sock.shutdown.side_effect = shutdown_error
        sut.close()

        input.close.assert_called_once()
        output.close.assert_called_once()
        sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        sock.close.assert_called_once()


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
