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

import os
import sys
from .config_file import ConfigFile

__author__ = 'ricard'


RUNNING_UNITTEST = sys.argv[0].endswith('trial') or 'pytest' in sys.argv[0] or os.environ.get('RUNNING_UNITTEST', False) == "True"

# PROJECT_ROOT = os.path.normpath(os.getcwd())
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
if RUNNING_UNITTEST:
    PROJECT_ROOT = os.path.join(PROJECT_ROOT, 'UT')
    if not os.path.exists(PROJECT_ROOT):
        os.makedirs(PROJECT_ROOT)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config")
CONFIG_FILE = os.path.join(CONFIG_PATH, "cloud-mailing.ini")
LOG_PATH = os.path.join(PROJECT_ROOT, "log")
STATIC_ROOT = os.path.join(PROJECT_ROOT, 'static')

os.makedirs(CONFIG_PATH, exist_ok=True)
os.makedirs(LOG_PATH, exist_ok=True)

config = ConfigFile()
if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE)
else:
    sys.stderr.write("Config file '%s' not found!\n" % CONFIG_FILE)

DEBUG = config.getboolean('DEBUG', 'DEBUG', False)
SSL_CERTIFICATE_PATH = os.path.join(PROJECT_ROOT, 'ssl')
SSL_CERTIFICATE_NAME = 'cm'

MASTER_DATABASE = config.get('MASTER_DATABASE', 'NAME', "cm_master")
MASTER_DATABASE_URI = config.get('MASTER_DATABASE', 'URI', "mongodb://localhost:27017")
SATELLITE_DATABASE = config.get('SATELLITE_DATABASE', 'NAME', "cm_satellite")
SATELLITE_DATABASE_URI = config.get('SATELLITE_DATABASE', 'URI', "mongodb://localhost:27017")
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
CUSTOMIZED_CONTENT_FOLDER = config.get('MAILING', 'CUSTOMIZED_CONTENT_FOLDER', os.path.join(PROJECT_ROOT, 'cust_ml'))

# Create missing folders
for dir_name in (CUSTOMIZED_CONTENT_FOLDER, MAIL_TEMP):
    try:
        os.makedirs(dir_name)
    except:
        pass

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

# API settings
PAGE_SIZE = 100

# SMTPD

SMTPD_AUTH_URL = config.get('SMTPD', 'user_authentication_url', 'https://localhost/api/auth/')
SMTPD_AUTH_USERNAME_FIELD = config.get('SMTPD', 'user_authentication_username_field', 'username')
SMTPD_AUTH_PASSWORD_FIELD = config.get('SMTPD', 'user_authentication_password_field', 'password')
SMTPD_VALIDATE_FROM_URL = config.get('SMTPD', 'validate_from_url', 'https://localhost/api/validate_from/')
SMTPD_VALIDATE_FROM_FIELD = config.get('SMTPD', 'validate_from_field', 'mail_from')
SMTPD_VALIDATE_TO_URL = config.get('SMTPD', 'validate_to_url', 'https://localhost/api/validate_to/')
SMTPD_VALIDATE_TO_FIELD = config.get('SMTPD', 'validate_to_field', 'rcpt_to')
SMTPD_MESSAGE_URL = config.get('SMTPD', 'message_url', 'https://localhost/api/send_mailing/')
SMTPD_RECIPIENTS_FIELD = config.get('SMTPD', 'recipients_field', 'recipients')
SMTPD_MESSAGE_FIELD = config.get('SMTPD', 'message_field', 'message')
