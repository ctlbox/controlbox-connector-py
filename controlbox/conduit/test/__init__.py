import sys

from controlbox.config.config import configure_package

configure_package(sys.modules[__name__])
