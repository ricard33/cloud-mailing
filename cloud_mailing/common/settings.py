# Copyright 2015 Cedric RICARD
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

import os
import sys
from .config_file import ConfigFile

__author__ = 'ricard'


RUNNING_UNITTEST = sys.argv[0].endswith('trial') or os.environ.get('RUNNING_UNITTEST', False) == "True"

PROJECT_ROOT = os.path.normpath(os.getcwd())
if RUNNING_UNITTEST:
    PROJECT_ROOT = os.path.join(PROJECT_ROOT, 'UT')
    if not os.path.exists(PROJECT_ROOT):
        os.makedirs(PROJECT_ROOT)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config")
CONFIG_FILE = os.path.join(CONFIG_PATH, "cloud-mailing.ini")
LOG_PATH = os.path.join(PROJECT_ROOT, "log")

config = ConfigFile()
if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)
else:
    sys.stderr.write("Config file '%s' not found!\n" % CONFIG_FILE)

DEBUG = config.getboolean('DEBUG', 'DEBUG', False)
SSL_CERTIFICATE_PATH = os.path.join(PROJECT_ROOT, 'ssl')
SSL_CERTIFICATE_NAME = 'cm'

MASTER_DATABASE = config.get('MASTER_DATABASE', 'NAME', "cm_master")
SATELLITE_DATABASE = config.get('SATELLITE_DATABASE', 'NAME', "cm_satellite")
TEST_DATABASE = "cm_test"

SERIAL = config.get('ID', 'SERIAL', '<NO_SERIAL_NUMBER>')


## Master

MASTER_IP = config.get('MAILING', 'master_ip', 'localhost')
MASTER_PORT = config.getint('MAILING', 'master_port', 33620)

## Satellite specific

TEST_TARGET_IP = config.get('MAILING', 'test_target_ip', "")  # used for mailing tests. IP of an internal and fake SMTP server.
TEST_TARGET_PORT = config.getint('MAILING', 'test_target_port', 33625)  # used for mailing tests. Port number of an internal and fake SMTP server.
TEST_FAKE_DNS = config.getboolean('MAILING', 'test_faked_dns', False)  # used for mailing tests. DNS always returns local ip.
USE_LOCAL_DNS_CACHE = config.getboolean('MAILING', 'use_local_dns_cache', False)  # mainly used for mailing tests. DNS always returns determined ips for some domains.
LOCAL_DNS_CACHE_FILE = config.get('MAILING', 'local_dns_cache_filename', os.path.join(PROJECT_ROOT, 'local_dns_cache.ini'))  # mainly used for mailing tests. DNS always returns determined ips for some domains.
MAIL_TEMP = config.get('MAILING', 'MAIL_TEMP', os.path.join(PROJECT_ROOT, 'temp'))

## End satellite specific

# Logging configuration
if 'master_app' in sys.argv:
    log_name = 'master'
elif 'satellite_app' in sys.argv:
    log_name = 'satellite'
else:
    log_name = 'cloud_mailing'

DEFAULT_LOG_FORMAT='%(name)-12s: %(asctime)s %(levelname)-8s [%(threadName)s] %(message)s'

import warnings
warnings.simplefilter('ignore', UserWarning)