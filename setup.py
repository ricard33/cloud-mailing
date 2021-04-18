# Copyright 2015-2019 Cedric RICARD
#
# This file is part of CloudMailing.
#
# CloudMailing is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CloudMailing is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with CloudMailing.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import io
import codecs
import os
import sys

here = os.path.normpath(os.path.dirname(__file__))


def read_version_from_properties_file():
    import os
    filename = os.path.join(here, 'cloud_mailing', 'version.properties')
    if os.path.exists(filename):
        with open(filename, 'rt') as f:
            for line in f:
                try:
                    name, value = line.split('=')
                    if name == 'VERSION':
                        return value.strip()
                except:
                    pass
    return "0.3.0"


def read(*filenames, **kwargs):
    encoding = kwargs.get('encoding', 'utf-8')
    sep = kwargs.get('sep', '\n')
    buf = []
    for filename in filenames:
        with io.open(os.path.join(here, filename), encoding=encoding) as f:
            buf.append(f.read())
    return sep.join(buf)


long_description = read('README.md', 'CHANGES.md')


class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errcode = pytest.main(self.test_args)
        sys.exit(errcode)


setup(
    name='cloud_mailing',
    version=read_version_from_properties_file(),
    url='http://github.com/ricard33/cloud_mailing/',
    license='GNU Affero General Public License',
    author='Cedric RICARD',
    tests_require=['pytest'],
    install_requires=['twisted',
                      'pymongo',
                      'mogo',
                      'Jinja2',
                      'watchdog',
                      ],
    cmdclass={'test': PyTest},
    author_email='ricard@free.fr',
    description='An e-mailing engine designed for simplicity and performance',
    long_description=long_description,
    packages=['cloud_mailing'],
    include_package_data=True,
    platforms='any',
    # test_suite='sandman.test.test_sandman',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Environment :: No Input/Output (Daemon)',
        'Framework :: Twisted',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Communications :: Email :: Mailing List Servers',
        ],
    extras_require={
        'testing': ['pytest'],
    },
    scripts=['bin/cm_master.py', 'bin/cm_satellite.py']
)
