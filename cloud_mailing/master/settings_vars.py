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


MAILING_QUEUE_MAX_SIZE = 'mailing_queue_max_size'
MAILING_QUEUE_MIN_SIZE = 'mailing_queue_min_size'
MAILING_QUEUE_MAX_THREAD = 'max_mailing_thread'
MAILING_QUEUE_MAX_THREAD_SIZE = 'mailing_queue_max_thread_size'
MAILING_RETRY_WAIT = 'mailing_retry_wait'            # no more used
MAILING_DURATION = 'mailing_duration'              # in days
SATELLITE_MAX_RECIPIENTS_TO_SEND = 'satellite_max_recipients_to_send'
FEEDBACK_LOOP_SETTINGS = 'feedback_loop_settings'

default = {
    MAILING_QUEUE_MAX_SIZE: 50000,
    MAILING_QUEUE_MIN_SIZE: 20000,  # TODO should be related to the number of active satellites to avoid locks (> nb_sat * min_queue_len_in_sat)
    MAILING_QUEUE_MAX_THREAD: 50,
    MAILING_QUEUE_MAX_THREAD_SIZE: 100,
    MAILING_RETRY_WAIT: 3600,
    MAILING_DURATION: 10,          # in days
    SATELLITE_MAX_RECIPIENTS_TO_SEND: 1000,
    FEEDBACK_LOOP_SETTINGS: {},
}

# Helpers
from ..common.models import Settings


def get(name):
    return Settings.get_str(name, default[name])


def get_int(name):
    return Settings.get_int(name, default[name])


def get_long(name):
    return Settings.get_long(name, default[name])


def get_bool(name):
    return Settings.get_bool(name, default[name])


def set(name, value):
    return Settings.set(name, value)
