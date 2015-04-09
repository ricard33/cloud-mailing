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


# You can run this .tac file directly with:
#    twistd -ny service.tac

"""
This is an example .tac file which starts a webserver on port 8080 and
serves files from the current working directory.

The important part of this, the part that makes it a .tac file, is
the final root-level section, which sets up the object called 'application'
which twistd will look for
"""
from StringIO import StringIO
import inspect
import logging
from mogo import connect

import twisted
from twisted.application import service, internet
from twisted.web import server, resource, xmlrpc, static

from cloud_mailing.common import __version__ as VERSION
from twisted.internet import ssl
from cloud_mailing.common.ssl_tools import make_SSL_context
from cloud_mailing.satellite import start_satellite_service
from cloud_mailing.common import settings

from cloud_mailing.common.cm_logging import configure_logging
from cloud_mailing.common import colored_log

configure_logging(settings.config, "satellite", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

##Twisted logs
from twisted.python.log import PythonLoggingObserver
observer = PythonLoggingObserver()
observer.start()

log = logging.getLogger("cm")

log.info("****************************************************************")
log.info("Starting CloudMailing SATELLITE version %s" % VERSION )
log.info("Serial: %s" % settings.SERIAL)
log.info("Twisted version %s", twisted.version.short())
log.info("****************************************************************")

# this is the core part of any tac file, the creation of the root-level
# application object
application = service.Application("CloudMailing Satellite")
ssl_context_factory = ssl.ClientContextFactory()
db_conn = connect(settings.SATELLITE_DATABASE)


# attach the service to its parent application
start_satellite_service(application, master_ip=settings.MASTER_IP, master_port=settings.MASTER_PORT,
                        ssl_context_factory=ssl_context_factory)
