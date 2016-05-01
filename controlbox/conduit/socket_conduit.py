import socket

from controlbox.conduit import base


class SocketConduit(base.Conduit):
    """
    A conduit that provides communication via a socket.
    :param sock The open, connected socket
    """
    def __init__(self, sock: socket.socket):
        """
        :param sock: the client socket that represents the connection
        :type sock: socket
        """
        self.sock = sock
        self.read = sock.makefile('rb')
        self.write = sock.makefile('wb')

    @property
    def open(self) -> bool:
        return self.sock.fileno() > 0

    @property
    def target(self):
        return self.sock

    @property
    def output(self):
        return self.write

    @property
    def input(self):
        return self.read

    def close(self):
        self.read.close()
        self.write.close()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass
        finally:
            self.sock.close()
            # swallow it - the peer may have closed the socket


# def client_socket_connector_factory(socket_opts, address):
#     """
#     Factory that produces a client socket connector.
#     :param socket_opts: options for constructing the socket
#     :type socket_opts: tuple
#     :param args: args passed to the socket connection
#     :param kwargs: kwargs passed to the socket connection
#     :return: a callable that creates new connections to via a client socket
#     :rtype: callable
#     """
#     def open_socket_connector():
#         sock = socket.socket(*socket_opts)
#         sock.setblocking(True)
#         sock.connect(address)
#         return SocketConduit(sock)
#
#     return open_socket_connector
#
#
# def server_socket_connector_factory(socket_opts, address):
#     """
#     Factory that produces a socket connector.
#     :param socket_opts: options for constructing the socket
#     :type socket_opts: tuple
#     :param args: args passed to the socket connection
#     :param kwargs: kwargs passed to the socket connection
#     :return: a callable that creates new connections to via a client socket
#     :rtype: callable
#     """
#
#     def open_socket_connector():
#         sock = socket.socket(*socket_opts)
#         sock.setblocking(True)
#         sock.bind(address)
#         return SocketConduit(sock)
#
#     return open_socket_connector
