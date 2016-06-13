import os
import sys
import unittest

from hamcrest import assert_that, is_, equal_to, has_property, is_not
from nose.plugins.attrib import attr

from controlbox.config.config import configure_module, config_filename, config_flavor

config_name = 'config_test'
value1 = None
value2 = None
value3 = None
value4 = None

this_module = sys.modules[__name__]


@attr(fixture='config')
class ConfigTestCase(unittest.TestCase):

    def test_can_retrieve_config_file(self):
        name = config_flavor(config_name, "default")
        file = config_filename(name, os.path.dirname(this_module.__file__))
        assert_that(os.path.exists(file), is_(True),
                    "expected config path %s to exist" % file)

    def test_can_apply_module(self):
        configure_module(this_module)
        assert_that(value1, is_(equal_to('def')))
        assert_that(value2, is_(equal_to(['1', '2', '3'])))
        assert_that(value3, is_(4))
        assert_that(value4, is_(50))
        assert_that(this_module, is_not(has_property("missing_value")))


if __name__ == '__main__':
    unittest.main()
