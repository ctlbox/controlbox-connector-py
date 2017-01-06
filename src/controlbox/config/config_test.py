import os
from unittest.mock import Mock

import sys
import unittest

from configobj import ConfigObjError, ConfigObj
from hamcrest import assert_that, is_, equal_to, has_property, is_not, calling, raises
from nose.plugins.attrib import attr

from controlbox.config.config import configure_module, config_filename, config_flavor, load_config_file_base, \
    load_config, reconstruct_name, fq_module_name, map_os_name, fetch_conf_path, apply_conf_path

config_name = 'config_test'
value1 = None
value2 = None
value3 = None
value4 = None

this_module = sys.modules[__name__]


@attr(fixture='config')
class ConfigTestCase(unittest.TestCase):

    def test_config_file_not_found(self):
        assert_that(calling(load_config_file_base).with_args('blah'), raises(IOError))

    def test_config_file_invalid_schema(self):
        path = os.path.dirname(__file__)
        assert_that(calling(load_config).with_args('config_test_invalid_schema', path),
                    raises(ConfigObjError, "the config file config_test_invalid_schema failed validation"))

    def test_config_file_invalid_syntax(self):
        path = os.path.dirname(__file__)
        assert_that(calling(load_config_file_base).with_args(os.path.join(path, 'config_test_invalid_syntax.cfg')),
                    raises(ConfigObjError, "Section too nested at line 1. at .*config_test_invalid_syntax.cfg"))

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

    def test_reconstruct_name(self):
        assert_that(reconstruct_name('C:/drive/dir/package1/package2/module.py', 2), is_('package1.package2.module'))
        assert_that(reconstruct_name('C:\\drive\\dir\\module.py', 0), is_('module'))

    def test_fq_module_name_with_name(self):
        module = Mock()
        module.__name__ = 'one.two.three'
        module.__package__ = 'one.two'
        assert_that(fq_module_name(module), is_('one.two.three'))

    def test_fq_module_name_as_main(self):
        module = Mock()
        module.__name__ = '__main__'
        module.__package__ = 'one.two'
        module.__file__ = '/some/place/one/two/three.py'
        assert_that(fq_module_name(module), is_('one.two.three'))

    def test_fq_module_name_no_package(self):
        module = Mock()
        module.__package__ = None
        assert_that(calling(fq_module_name).with_args(module), raises(ConfigObjError, '.*no package'))

    def test_map_os_name(self):
        assert_that(map_os_name('Windows'), is_('windows'))
        assert_that(map_os_name('Darwin'), is_('osx'))
        assert_that(map_os_name('darwin'), is_('osx'))

    def test_non_existent_config_path(self):
        sut = ConfigObj()
        assert_that(fetch_conf_path(sut, 'abcd'), is_(None))

    def test_non_existent_apply_config_path(self):
        sut = ConfigObj()
        target = Mock()
        apply_conf_path(sut, 'abcd', target)
        # not sure what to assert here - that apply() was not called? This would be much easier to test
        # if the config API were a class.

    def test_configure_module(self):
        configure_module(this_module, 'config_test_alt')
        assert_that(value3, is_('alt'))


if __name__ == '__main__':  # pragma no cover
    unittest.main()
