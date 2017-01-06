import os
import platform

from configobj import ConfigObj, ConfigObjError, Section
from validate import Validator

# The default extension for configuration files
config_extension = '.cfg'


def config_flavor(name, flavor=None):
    configname = name if not flavor else name + '.' + flavor
    return configname


def config_filename(name, directory=None):
    """
    Determines the location of a config file relative to this module.
    """
    config_file = os.path.join(directory, name + config_extension)
    return config_file


def load_config_file_base(file, must_exist=True):
    """
    Loads a configuration file
    :param file:        The configuration file to load
    :param must_exist:  when True, the file must exist or an exception is thrown.
    :return: The ConfigObj instance for the file.
    """
    try:
        return ConfigObj(file, interpolation='Template', file_error=must_exist) \
            if must_exist or os.path.exists(file) else ConfigObj()
    except ConfigObjError as e:
        raise type(e)(str(e) + ' at ' + file)


def config_flavor_file(name, directory, subpart=None)->ConfigObj:
    """
    Loads a specialization of a config file. The configuration file is expected to be named
    after the base, followed by a period and then the specialization, if the specialization is given,
    otherwise just the base name.
    :param name:    The name of the base configuration
    :param subpart: The name of the specialization.
    :return: The ConfigObj for the configuration file.
    """
    configname = config_flavor(name, subpart)
    file = config_filename(configname, directory)
    config = load_config_file_base(file, False)
    return config


def map_os_name(name):
    """
    >>> map_os_name('Windows')
    'windows'
    >>> map_os_name("Darwin")
    'osx'
    """
    name = name.lower()
    if name == 'darwin':
        name = 'osx'
    return name


def os_name():
    return map_os_name(platform.system())


def load_config(name, directory):
    """
        Loads all the configuration files that relate to the given name.
        Configurations are loaded in this order:
        - the base configuration
        - the default specialization
        - the platform specialization
        - the user override
        The configurations are flattened into a single configuration, and then validated
        against a configuration specialization "schema".
    :directory: the location of the configuration file
    :return:
    """
    local_config = config_flavor_file(name, directory)
    default_config = config_flavor_file(name, directory, 'default')
    platform_config = config_flavor_file(name, directory, os_name())
    # todo - how to set the name for this
    user_config = load_config_file_base(os.path.expanduser(
        '~/' + name + config_extension), must_exist=False)
    config = ConfigObj()
    config.merge(default_config)
    config.merge(platform_config)
    config.merge(user_config)
    config.merge(local_config)

    config.configspec = config_flavor_file(name, directory, 'schema')
    validator = Validator()
    result = config.validate(validator)
    if not result:
        # for section_list, key, res in flatten_errors(config, result):
            # print('result %s' % res)
            # if key is not None:
            #     print('The "%s" key in the section "%s" failed validation' %
            #           (key, ', '.join(section_list)))
            # else:
            #     print('The following section was missing:%s ' %
            #           ', '.join(section_list))
        raise ConfigObjError("the config file %s failed validation %s" % (name, result))
    return config


def apply(target, config_path, config_name, directory):
    """
    Applies defined values from a path to a given target object.
    :param target: The object to receive the values defined
    :param cont_path: The path that is the prefix to the values defined. The path is split on '.'.
    :param config_name: The configuration file to load.
    :param the directory containing the config file
    :return:
    """
    conf = load_config(config_name, directory)
    name_parts = config_path.split('.')
    apply_conf_path(conf, name_parts, target)


def fetch_conf_path(conf: Section, path):
    """
    Retrieves the named configuration section
    :param conf:        The root configuration the na
    :param name_path:   An iterable that lists the names of the config to resolve
    :return: The configuration object identified by teh path
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


# def find_package_root(dir, package=None):
#     def prepend_package_part(pkg, part):
#         return part if not pkg else part + '.' + pkg
#
#     package_file = os.path.join(dir, '__init__.py')
#     parent = os.path.abspath(os.path.join(dir, '..'))
#     return find_package_root(parent, prepend_package_part(package, os.path.basename(dir))) \
#         if os.path.exists(package_file) else (dir, package)
#
#
# def determine_module_package(module):
#     file = module.__file__
#     # walk the tree until there are no __init__.py files
#     root, package = find_package_root(os.path.dirname(file))
#     return package


def fq_module_name(module):
    """
    Retrieves the fully qualified name of the module.
    :param module:
    :param package_depth:
    :return:
    """
    if not module.__package__:
        raise ConfigObjError('module has no package defined')
    return module.__name__ if module.__name__ != '__main__' else \
        reconstruct_name(module.__file__, len(module.__package__.split('.')))


def configure_module(module, config_name=None):
    """
    Applies the configuration to the given module.
    The configuration is loaded from files named after the module.

    Obsolete - possibly a python 2 holdover - the package is needed when a module is loaded as main.
    Then the name isn't the fully qualified name, but
    just '__main__'. To reconstruct the original module name, we use the package, and combine with the filename
    """
    fqname = fq_module_name(module)
    if not config_name:
        config_name = fqname.split('.')[-1]
    # apply the settings to this module, the nested location of settings
    # reflects the module's location (x.y.z.source_file)
    # the config_name follows the module source file name, located in the
    # same directory as the source file
    apply(module, fqname, config_name, os.path.dirname(module.__file__))
