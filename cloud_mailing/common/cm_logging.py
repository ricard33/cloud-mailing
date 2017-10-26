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
import logging, logging.config, logging.handlers
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler, FileSystemEventHandler

__author__ = 'ricard'
_watchdog_configured = False

def configure_logging(log_name, LOG_CONFIG_PATH, LOG_PATH, DEFAULT_LOG_FORMAT, RUNNING_UNITTEST):
    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH)


    if RUNNING_UNITTEST and not logging.Logger.manager.loggerDict:
        # HACK to avoid logs due to DEBUG level forced by pyreadline's logger module
        try:
            import pyreadline
        #    except ImportError, ex:
        except Exception as ex:
            # print >> sys.stderr, "IMPORT ERROR with pyreadline:", ex.message
            pass
        # logger = logging.getLogger()
        logging.basicConfig(level=logging.CRITICAL, format=DEFAULT_LOG_FORMAT)
        # logging.basicConfig(level=logging.DEBUG, format=DEFAULT_LOG_FORMAT)
        # logger.setLevel(logging.CRITICAL)
        # logger.setLevel(logging.DEBUG)
        return

    if not RUNNING_UNITTEST:
        handler = LoggingConfigEventHandler(log_name, LOG_CONFIG_PATH, LOG_PATH, DEFAULT_LOG_FORMAT)
        handler.do_reconfigure_logging()

        if os.path.exists(LOG_CONFIG_PATH):
            observer = Observer()
            # observer.schedule(LoggingEventHandler(), LOG_CONFIG_PATH, recursive=False)
            observer.schedule(handler, LOG_CONFIG_PATH, recursive=False)
            print("log watcher to '%s'" % LOG_CONFIG_PATH)
            observer.daemon = True  # should not block the program ending
            observer.start()


class LoggingConfigEventHandler(FileSystemEventHandler):
    """Check for logging config changes."""
    def __init__(self, log_name, LOG_CONFIG_PATH, LOG_PATH, DEFAULT_LOG_FORMAT):
        self.log_name = log_name
        self.config_path = LOG_CONFIG_PATH
        self.log_path = LOG_PATH
        self.default_log_format = DEFAULT_LOG_FORMAT
        self.base_filename = 'logging-%s' % self.log_name

    def on_any_event(self, event):
        print(("Event %s" % repr(event)))
        logging.debug("Event %s", event)
        if not event.is_directory:
            filename = os.path.basename(event.src_path)
            if filename.startswith(self.base_filename):
                logging.info("Logging config change detected. Reloading configuration...")
                self.do_reconfigure_logging()

    def do_reconfigure_logging(self):
        log_ok = False
        logconfig_fullpath = os.path.join(self.config_path, 'logging-%s.py' % self.log_name)
        if not os.path.exists(logconfig_fullpath):
            logconfig_fullpath = os.path.splitext(logconfig_fullpath)[0] + '.ini'
        if not os.path.exists(logconfig_fullpath):
            logconfig_fullpath = os.path.splitext(logconfig_fullpath)[0] + '.default.py'
        if os.path.exists(logconfig_fullpath):
            logging.info("Loading log config from %s", logconfig_fullpath)
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
            print("Loading log config not found or badly formated, loading default config.")

            log_level = logging.INFO
            formatter = logging.Formatter(self.default_log_format)
            logging.basicConfig(level=log_level, format=self.default_log_format)
            logFile = logging.handlers.RotatingFileHandler(os.path.join(self.log_path, os.path.basename(self.log_name) + '.log'),
                                                           maxBytes=1 * 1024 * 1024, backupCount=10)
            logFile.setLevel(log_level)
            logFile.setFormatter(formatter)
            logging.getLogger().addHandler(logFile)
            logging.getLogger().propagate = False

            logger = logging.getLogger('mailing.out')
            logger.propagate = False
            logFile = logging.handlers.TimedRotatingFileHandler(os.path.join(self.log_path, 'mailing.out.log'), when='d',
                                                                interval=1, backupCount=20)
            logFile.setLevel(log_level)
            logFile.setFormatter(formatter)
            logger.addHandler(logFile)

            logging.getLogger('twisted').setLevel(logging.WARN)