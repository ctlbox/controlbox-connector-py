import os
import subprocess

from controlbox.conduit.base import DefaultConduit
from controlbox.conduit.discovery import PolledResourceDiscovery


class ProcessConduit(DefaultConduit):
    """ Provides a conduit to a locally hosted process. """

    def __init__(self, *args, cwd=None):
        """
        args: the process image name and any additional arguments required by the process.
        raises OSError and ValueError
        """
        super().__init__()
        self.process = None
        self.cwd = cwd
        self._load(*args)

    @property
    def target(self):
        return self.process

    def _load(self, *args):
        p = subprocess.Popen(args, cwd=self.cwd, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        self.process = p
        self.set_streams(p.stdout, p.stdin)

    @property
    def open(self):
        """
        The conduit is considered open if the underlying process is still set and alive.
        """
        return self.process is not None and \
            self.process.poll() is None

    def wait_for_exit(self):
        self.process.wait()

    def close(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait()
            self.process = None


# class DirectoryDiscovery(PolledResourceDiscovery):
#     """ Monitors a file that can be executed. """
#
#     def __init__(self, file, pattern):
#         super().__init__()
#         self.file = file
#         self.pattern = pattern
#
#     def _is_allowed(self, key, device):
#         return self.pattern.match(key)


class ProcessDiscovery(PolledResourceDiscovery):
    """ Monitors a file that can be executed. """

    def __init__(self, file):
        super().__init__()
        self.file = file

    def _fetch_available(self):
        return {} if not os.path.isfile(self.file) else {self.file: self.file}
