"""
Provides project-level commands. Commands are run via `python setup.py <command> [args]`

Commands available:

- apidoc: regenerate reST docs for inline pydoc comments
- autobuild: watch for changes to the reST files and rebuild the documentation, refreshing
   the browser.
"""

from setuptools import setup, Command

import os


class RunInRootCommand(Command):
    user_options = []

    def initialize_options(self):
        self.cwd = None

    def finalize_options(self):
        self.cwd = os.getcwd()

    def run(self):
        assert os.getcwd() == self.cwd, 'Must be in package root: %s' % self.cwd
        self.runcmd()

    def runcmd(self):
        pass


class ApiDocCommand(RunInRootCommand):
    description = "regenerates the API docs"

    def runcmd(self):
        os.system('"sphinx-apidoc" -f -e -o docs/apidoc .')


class AutoBuildCommand(RunInRootCommand):
    description = "watches the docs for changes and rebuilds them, automatically refreshing the browser page"

    def runcmd(self):
        os.system("sphinx-autobuild docs docs/_build/html -B")


setup(
    name='controlbox-connector-py',
    version='0.0.1',
    description='Application-neutral support for controlbox instances in Python.',
    url='',
    author='',
    author_email='',
    license='LGPL',
    package_dir={'': 'src'},
    packages=['controlbox', 'controlbox.conduit', 'controlbox.config', 'controlbox.connector',
                'controlbox.protocol', 'controlbox.support'],
    zip_safe=False,
    cmdclass={
        'apidoc': ApiDocCommand,
        'autobuild': AutoBuildCommand
    }
)
