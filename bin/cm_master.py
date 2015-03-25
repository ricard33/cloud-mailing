#!/usr/bin/env python
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

import sys, os

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))

import logging
from mogo import connect
import twisted
from twisted.internet import reactor

from common import __version__ as VERSION
from common.ssl_tools import make_SSL_context
from master import get_api_service, start_master_service
from common import settings

from common.cm_logging import configure_logging
from common import colored_log
configure_logging(settings.config, "master", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

##Twisted logs
from twisted.python.log import PythonLoggingObserver
observer = PythonLoggingObserver()
observer.start()

log = logging.getLogger("cm")

log.info("****************************************************************")
log.info("Starting CloudMailing version %s" % VERSION )
log.info("Serial: %s" % settings.SERIAL)
log.info("Twisted version %s", twisted.version.short())
log.info("****************************************************************")


# this is the core part of any tac file, the creation of the root-level
# application object
ssl_context_factory = make_SSL_context()
db_conn = connect(settings.MASTER_DATABASE)


# attach the service to its parent application
apiService = get_api_service(ssl_context_factory=ssl_context_factory)
start_master_service(None, ssl_context_factory=ssl_context_factory)
reactor.run()