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

__author__ = 'ricard'


def configure_logging(config, log_name, LOG_CONFIG_PATH, LOG_PATH, DEFAULT_LOG_FORMAT, RUNNING_UNITTEST):
    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH)

    import logging, logging.config, logging.handlers

    if RUNNING_UNITTEST and not logging.Logger.manager.loggerDict:
        # HACK to avoid logs due to DEBUG level forced by pyreadline's logger module
        try:
            import pyreadline
        #    except ImportError, ex:
        except Exception, ex:
            # print >> sys.stderr, "IMPORT ERROR with pyreadline:", ex.message
            pass
        # logger = logging.getLogger()
        logging.basicConfig(level=logging.CRITICAL, format=DEFAULT_LOG_FORMAT)
        # logging.basicConfig(level=logging.DEBUG, format=DEFAULT_LOG_FORMAT)
        # logger.setLevel(logging.CRITICAL)
        # logger.setLevel(logging.DEBUG)
        return

    if not RUNNING_UNITTEST:
        log_ok = False
        logconfig_fullpath = os.path.join(LOG_CONFIG_PATH, 'logging-%s.py' % log_name)
        if not os.path.exists(logconfig_fullpath):
            logconfig_fullpath = os.path.splitext(logconfig_fullpath)[0] + '.ini'
        if not os.path.exists(logconfig_fullpath):
            logconfig_fullpath = os.path.splitext(logconfig_fullpath)[0] + '.default.py'
        if os.path.exists(logconfig_fullpath):
            # print "Loading log config from %s" % logconfig_fullpath
            try:
                if logconfig_fullpath.endswith(".py"):
                    import imp
                    log_config = imp.load_source('log_config', logconfig_fullpath)
                    logging.config.dictConfig(log_config.LOGGING)
                else:
                    logging.config.fileConfig(logconfig_fullpath)

                log_ok = True
            except Exception:
                import traceback

                traceback.print_exc()

        if not log_ok:
            print "Loading log config not found or badly formated, loading default config."

            log_level = logging.INFO
            formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
            logging.basicConfig(level=log_level, format=DEFAULT_LOG_FORMAT)
            logFile = logging.handlers.RotatingFileHandler(os.path.join(LOG_PATH, os.path.basename(log_name) + '.log'),
                                                           maxBytes=1 * 1024 * 1024, backupCount=10)
            logFile.setLevel(log_level)
            logFile.setFormatter(formatter)
            logging.getLogger().addHandler(logFile)
            logging.getLogger().propagate = False

            logger = logging.getLogger('mailing.out')
            logger.propagate = False
            logFile = logging.handlers.TimedRotatingFileHandler(os.path.join(LOG_PATH, 'mailing.out.log'), when='d',
                                                                interval=1, backupCount=20)
            logFile.setLevel(log_level)
            logFile.setFormatter(formatter)
            logger.addHandler(logFile)
