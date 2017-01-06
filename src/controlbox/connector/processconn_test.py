import unittest

import sys

from controlbox.connector.base import ConnectorError
from controlbox.connector.processconn import ProcessConnector


class ProcessConnectorTest(unittest.TestCase):
    def test_is_executable_non_file(self):
        self.expectExecutable('blahblah', False)

    def test_is_executable_file_not_executable(self):
        self.expectExecutable(__file__, False)

    def test_is_executable_file_executable(self):
        self.expectExecutable(sys.executable, True)

    def expectExecutable(self, file, executable):
        self.assertEqual(executable, ProcessConnector._is_executable(file))

    def test_constructor(self):
        file = sys.executable
        cwd = 'a/b/c'
        args = ['1', '2']
        sut = ProcessConnector(file, args, cwd)
        self.assertEqual(sut.image, file, cwd)
        self.assertEqual(sut.args, args)
        self.assertEqual(sut.cwd, cwd)

    def test_try_available(self):
        sut = ProcessConnector(sys.executable)
        self.assertEqual(sut._try_available(), True)

    def test_endpoint(self):
        sut = ProcessConnector(sys.executable)
        self.assertEqual(sut.endpoint, sys.executable)

    def test_connect_disconnect(self):
        sut = ProcessConnector(sys.executable)
        sut.connect()
        sut.disconnect()

    def test_connect_invalid(self):
        sut = ProcessConnector("$$$")
        # fake availability so it tries to call _connect and create the ProcessConduit
        sut._try_available = lambda: True
        self.assertRaises(ConnectorError, sut.connect)
