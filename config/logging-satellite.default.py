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

__author__ = 'ricard'
import sys

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(name)-12s: %(asctime)s %(levelname)-8s [%(threadName)s] %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    #'filters': {
    #    'special': {
    #        '()': 'project.logging.SpecialFilter',
    #        'foo': 'bar',
    #    },
    #},
    'handlers': {
        'console': {
            'level': 'NOTSET',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            # 'stream': sys.stdout,
        },
        'file': {
            'level': 'NOTSET',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            'filename': 'log/satellite.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
        },
        'outgoing': {
            'level': 'NOTSET',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'formatter': 'verbose',
            'filename': 'log/mailing.out.log',
            'when': 'd',
            'interval': 1,
            'backupCount': 20,
        },
        # 'mail_admins': {
        #     'level': 'ERROR',
        #     'class': 'logging.handlers.SMTPHandler',
        #     'mailhost': 'mail.example.org',
        #     'fromaddr': 'cloud_mailing@example.org',
        #     'toaddrs': ['alerts@example.org',],
        #     'subject': "ALERT form Cloud Mailing",
        #     'credentials': ['username', 'password'],
        #     'secure': False,
        #     #'filters': ['special']
        # }
    },
    'root': {
        'handlers': ['console', 'file', ],
        'level': 'INFO',
    },
    'loggers': {
        'twisted': {
            'level': 'WARNING',
        },
        'daemons': {
            'level': 'INFO',
        },
        'relay': {
            'level': 'INFO',
        },
        'mailing': {
            'level': 'INFO',
        },
        'ml_queue': {
            'level': 'DEBUG',
        },
        'sendmail': {
            'level': 'INFO',
        },
        'mailing.out': {
            'level': 'INFO',
            'handlers': ['outgoing']
        },
    },

}
