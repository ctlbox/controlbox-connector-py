import sys
import unittest
from unittest.mock import patch, Mock

import subprocess
from hamcrest import assert_that, equal_to, is_

from controlbox.conduit.process_conduit import ProcessConduit
# todo - these tests will need to be made OS-agnostic
# they are also not good unit tests
from controlbox.config.config import configure_module

echo_command = None
more_command = None


class ProcessConduitIntegrationTest(unittest.TestCase):

    def __init__(self, arg):
        super().__init__(arg)
        self.p = None

    def tearDown(self):
        if self.p is not None:
            self.p.close()

    @unittest.skipUnless(echo_command, "echo command not defined")
    def test_canCreateProcessConduitAndTerminate(self):
        self.p = ProcessConduit(echo_command)
        assert_that(self.p.open, equal_to(True))
        self.p.close()
        assert_that(self.p.open, equal_to(False))

    @unittest.skipUnless(echo_command, "echo command not defined")
    def test_canCreateProcessConduitAndReadOutputThenTerminate(self):
        p = ProcessConduit(echo_command, "123")
        lines = p.input.readline()
        self.assertEqual(lines, b"123\r\n")

    @unittest.skipUnless(more_command, "more command not defined")
    def test_canCreateProcessConduitAndSendInputOutputThenTerminate(self):
        # will read from stdin and pipe to stdout
        p = ProcessConduit(more_command)
        p.output.write(b"hello\r\n")
        p.output.flush()
        lines = p.input.readline()
        self.assertEqual(lines, b"hello\r\n")

configure_module(sys.modules[__name__])


class ProcessConduitTest(unittest.TestCase):
    def test_opens_process_and_sets_streams(self):
        with patch("subprocess.Popen") as mock:
            mock.stdout = "out"
            mock.stdin = "in"
            mock.return_value = mock
            sut = ProcessConduit("myexe", "arg1", "arg2")
            assert_that(sut.process, is_(mock._mock_return_value))
            # note that the in/out streams are reversed
            assert_that(sut.input, is_(mock.stdout))
            assert_that(sut.output, is_(mock.stdin))
            mock.assert_called_once_with("myexe arg1 arg2", stdout=subprocess.PIPE, stdin=subprocess.PIPE)
            proc = sut.target
            assert_that(proc, is_(mock))

            mock.poll = Mock(return_value=None)
            assert_that(sut.open, is_(True))

            mock.poll = Mock(return_value=True)
            assert_that(sut.open, is_(False))

            mock.poll = Mock(return_value=None)

            mock.wait = Mock()
            sut.wait_for_exit()
            mock.wait.assert_called_once()
            mock.wait.reset_mock()

            mock.terminate = Mock()
            sut.close()
            assert_that(sut.open, is_(False))
            mock.terminate.assert_called_once()
            mock.wait.assert_called_once()

            assert_that(sut.process, is_(None))
            mock.terminate.reset_mock()
            mock.wait.reset_mock()
            sut.close()
            mock.terminate.assert_not_called()
            mock.wait.assert_not_called()

if __name__ == '__main__':
    unittest.main()
