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

# this file contains all settings names
# they are used into 'settings' table


EHLO_STRING = 'EHLO_STRING'
X_MAILER = 'CloudMailing'

MAILING_QUEUE_MAX_SIZE = 'mailing_queue_max_size'
MAILING_QUEUE_MIN_SIZE = 'mailing_queue_min_size'
MAILING_QUEUE_MAX_THREAD = 'max_mailing_thread'
MAILING_QUEUE_MAX_THREAD_SIZE = 'mailing_queue_max_thread_size'
MAILING_MAX_REPORTS = 'mailing_max_reports'
MAILING_MAX_NEW_RECIPIENTS = 'mailing_max_new_recipients'
# DEFAULT_CNX_PER_MX = 'default_connection_per_mx'
# DEFAULT_MAX_MX = 'default_max_mx'
DEFAULT_MAX_QUEUE_PER_DOMAIN = 'default_max_queue_per_domain'
ZOMBIE_QUEUE_AGE_IN_SECONDS = 'zombie_queue_age_in_seconds'
MAILING_QUEUE_ENDING_DELAY = 'mailing_queue_ending_delay'

default = {
    EHLO_STRING: 'mail.cloudmailing.net',

    MAILING_QUEUE_MAX_SIZE: 10000,
    MAILING_QUEUE_MIN_SIZE: 5000,
    MAILING_QUEUE_MAX_THREAD: 50,
    MAILING_QUEUE_MAX_THREAD_SIZE: 100,
    MAILING_MAX_REPORTS: 1000,
    MAILING_MAX_NEW_RECIPIENTS: 100,
    # DEFAULT_CNX_PER_MX: 1
    # DEFAULT_MAX_MX: 2
    DEFAULT_MAX_QUEUE_PER_DOMAIN: 1,  #2
    ZOMBIE_QUEUE_AGE_IN_SECONDS: 300,
    MAILING_QUEUE_ENDING_DELAY: 0,
}

# Helpers
from ..common.models import Settings


def get(name):
    return Settings.get_str(name, default[name])


def get_int(name):
    return Settings.get_int(name, default[name])


def get_long(name):
    return Settings.get_long(name, default[name])


def get_float(name):
    return Settings.get_float(name, default[name])


def get_bool(name):
    return Settings.get_bool(name, default[name])


def set(name, value):
    return Settings.set(name, value)
