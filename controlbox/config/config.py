import os
import sys
import platform
from validate import Validator

from configobj import ConfigObj, Section, ConfigObjError, flatten_errors

# The default extension for configuration files
config_extension = '.cfg'


def config_flavor(name, flavor=None):
    configname = name if not flavor else name + '.' + flavor
    return configname


def config_filename(name, package=None):
    """
    Determines the location of a config file relative to this module.
    """
    filename = sys.modules[__name__].__file__
    dirname = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(filename)), '../..'))
    if package:
        dirname = os.path.join(dirname, package.replace('.', '/'))
    config_file = os.path.join(dirname, name + config_extension)
    return config_file


def load_config_file_base(file, must_exist=True):
    """
    Loads a configuration file
    :param file:        The configuration file to load
    :param must_exist:  when True, the file must exist or an exception is thrown.
    :return: The ConfigObj instance for the file.
    """
    return ConfigObj(file, interpolation='Template') if must_exist or os.path.exists(file) else ConfigObj()


def config_flavor_file(name, package=None, subpart=None)->ConfigObj:
    """
    Loads a specialization of a config file. The configuration file is expected to be named
    after the base, followed by a period and then the specialization, if the specialization is given,
    otherwise just the base name.
    :param name:    The name of the base configuration
    :param subpart: The name of the specialization.
    :return: The ConfigObj for the configuration file.
    """
    configname = config_flavor(name, subpart)
    file = config_filename(configname, package)
    config = load_config_file_base(file)
    return config


def load_config(name, package=None):
    """
        Loads all the configuration files that relate to the given name.
        Configurations are loaded in this order:
        - the base configuration
        - the default specialization
        - the platform specialization
        - the user override
        The configurations are flattened into a single configuration, and then validated
        against a configuration specialization "schema".
    :param name: the base name of the configuration to load.
    :return:
    """
    local_config = config_flavor_file(name, package)
    default_config = config_flavor_file(name, package, 'default')
    platform_config = config_flavor_file(name, package, platform.system().lower())
    # todo - how to set the name for this
    user_config = load_config_file_base(os.path.expanduser(
        '~/' + name + config_extension), must_exist=False)
    config = ConfigObj()
    config.merge(default_config)
    config.merge(platform_config)
    config.merge(user_config)
    config.merge(local_config)

    config.configspec = config_flavor_file(name, package, 'schema')
    validator = Validator()
    result = config.validate(validator)
    if not result:
        for section_list, key, res in flatten_errors(config, result):
            print('result %s' % res)
            if key is not None:
                print('The "%s" key in the section "%s" failed validation' %
                      (key, ', '.join(section_list)))
            else:
                print('The following section was missing:%s ' %
                      ', '.join(section_list))
        raise ConfigObjError("the config failed validation %s" % result)
    return config


def apply(target, config_path, config_name, package=None):
    """
    Applies defined values from a path to a given target object.
    :param target: The object to receive the values defined
    :param cont_path: The path that is the prefix to the values defined. The path is split on '.'.
    :param config_name: The configuration file to load.
    :param package: the package that contains the configuration file
    :return:
    """
    conf = load_config(config_name, package)
    name_parts = config_path.split('.')
    apply_conf_path(conf, name_parts, target)


def fetch_conf_path(conf: Section, path):
    """
    Retrieves the named configuration section
    :param conf:        The root configuration the na
    :param name_path:   An iterable that lists the names of the config to respove
    :return: The configuraion object identified by teh path
    """
    for p in path:    # lookup specific section
        conf = conf.get(p, None)
        if conf is None:
            return
    return conf


def apply_conf_path(conf: Section, name_parts, target):
    """
    Applies a configuration path to a given target object
    :param conf:        The root configuration object
    :param name_parts:  The path of the configuration to apply
    :param target:      The target object that receives the configured values
    :return:
    """
    conf = fetch_conf_path(conf, name_parts)
    if conf:
        apply_conf(conf, target)


def apply_conf(conf: Section, target):
    """
    Applies the attributes contained in a configuration object to a target object.
    It does this by iterating over the items in the configuration and setting any attributes with the same name.
    :param conf:
    :param target:
    :return:
    """
    for k, v in conf.items():
        if hasattr(target, k):
            setattr(target, k, v)


def reconstruct_name(path, package_depth):
    """
    Retrieves a package from a path.
    :param path The filename of a module file
    :param package_depth The number of levels deep from the root.

    >>> reconstruct_name('C:/drive/dir/package1/package2/module.py', 2)
    'package1.package2.module'
    >>> reconstruct_name('C:\\drive\\dir\\module.py', 0)
    'module'
    """
    path = path.replace('\\', '/')
    parts = path.split('/')
    parts[-1] = os.path.splitext(parts[-1])[0]
    return '.'.join(parts[-package_depth - 1:])


def build_module_name(module, package_depth):
    """
    Retrieves the fully qualified name of the module.
    :param module:
    :param package_depth:
    :return:
    """
    return module.__name__ if module.__name__ is not '__main__' else reconstruct_name(module.__file__, package_depth)


def configure_module(module, package_depth=None, config_name=None):
    """
    The package is needed when a module is loaded as main. Then the name isn't the fully qualified name, but
    just '__main__'. To reconstruct the original module name, we use the package, and combine with the filename
    """
    package = module.__package__
    name = build_module_name(module, package_depth)
    if not config_name:
        config_name = name.split('.')[-1]
    apply(module, name, config_name, package)


def configure_package(module):
    configure_module(module, module.__package__)
