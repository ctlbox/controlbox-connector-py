import socket
import unittest
from multiprocessing.context import Process
from hamcrest import assert_that, is_
from multiprocessing import Semaphore

from controlbox.conduit.socket_conduit import SocketConduit


class EchoServer:
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


class HelloServer:
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
        except Exception as e:
            print(e)
            raise e

if __name__ == '__main__':
    unittest.main()
