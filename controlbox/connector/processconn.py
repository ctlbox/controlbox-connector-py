import logging
import os

from controlbox.conduit.base import Conduit
from controlbox.conduit.process_conduit import ProcessConduit
from controlbox.connector.base import AbstractConnector, ConnectorError

logger = logging.getLogger(__name__)


class ProcessConnector(AbstractConnector):
    """ Instantiates a process and connects to it via standard in/out. """

    def __init__(self, image, args=None, cwd=None):
        super().__init__()
        self.image = image
        self.args = args
        self.cwd = cwd

    @property
    def endpoint(self):
        return self.image

    def _disconnect(self):
        pass

    def _connect(self) -> Conduit:
        try:
            args = self.args if self.args is not None else []
            p = ProcessConduit(self.image, *args, cwd=self.cwd)
            return p
        except (OSError, ValueError) as e:
            logger.error(e)
            raise ConnectorError from e

    def _try_available(self):
        return self._is_executable(self.image)

    @staticmethod
    def _is_executable(file):
        """
        Determines if the given file is executable.
        :param file: the filename to check.
        :return: True if the file is executable.
        """
        return os.path.isfile(file) and os.access(file, os.X_OK)


