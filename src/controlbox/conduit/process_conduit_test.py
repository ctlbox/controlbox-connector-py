import subprocess
import unittest
from unittest.mock import Mock, patch

from hamcrest import assert_that, is_

from controlbox.conduit.process_conduit import ProcessConduit, ProcessDiscovery


class ProcessConduitTest(unittest.TestCase):
    def test_opens_process_and_sets_streams(self):
        with patch("subprocess.Popen") as mock:
            mock.stdout = "out"
            mock.stdin = "in"
            mock.return_value = mock
            sut = ProcessConduit("myexe", "arg1", "arg2", cwd="abc")
            assert_that(sut.process, is_(mock._mock_return_value))
            # note that the in/out streams are reversed
            assert_that(sut.input, is_(mock.stdout))
            assert_that(sut.output, is_(mock.stdin))
            mock.assert_called_once_with(("myexe", "arg1", "arg2"), cwd="abc",
                                         stdout=subprocess.PIPE, stdin=subprocess.PIPE)
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


class ProcessDiscoveryTest(unittest.TestCase):
    def test_constructor(self):
        file = "a file"
        sut = ProcessDiscovery(file)
        self.assertIs(sut.file, file)
        self.assertEqual(sut.previous, {})

    def test_resource_file_not_exists(self):
        file = "a file/that doesnt/exist"
        sut = ProcessDiscovery(file)
        self.assertEqual({}, sut._fetch_available())

    def test_resource_file_exists(self):
        file = __file__
        sut = ProcessDiscovery(file)
        self.assertEqual({file: file}, sut._fetch_available())


if __name__ == '__main__':  # pragma no cover
    unittest.main()
