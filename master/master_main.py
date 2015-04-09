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

import logging
from mogo import connect
import twisted
from twisted.application import service, internet
from twisted.application.service import IService
from twisted.internet import reactor
from twisted.python.log import PythonLoggingObserver
from twisted.web import server

from .. import __version__ as VERSION
from ..common.ssl_tools import make_SSL_context
from ..common import settings
from ..common.cm_logging import configure_logging
from ..common import colored_log
from .xmlrpc_api import make_xmlrpc_server

service_master = None
service_manager = None

def get_api_service(application=None, ssl_context_factory=None):
    """
    Return a service suitable for creating an application object.

    This service is a simple web server that serves files on port 8080 from
    underneath the current working directory.
    """
    if not ssl_context_factory:
        ssl_context_factory = make_SSL_context()

    webServer = server.Site( make_xmlrpc_server() )
    if application:
        apiService = internet.SSLServer(33610, webServer, ssl_context_factory)
        apiService.setServiceParent(application)
    else:
        apiService = reactor.listenSSL(33610, webServer, ssl_context_factory)

    logging.info("Supervisor XMLRPC SSL server started on port %d", 33610)
    return apiService


def start_master_service(application=None, master_port=33620, ssl_context_factory=None):
    global service_master, service_manager
    from mailing_manager import start_mailing_manager
    service_manager = start_mailing_manager()
    if application:
        service_manager.setServiceParent(application)

    from cloud_master import get_cloud_master_factory
    factory = get_cloud_master_factory()

    if application:
        if ssl_context_factory:
            service_master = internet.SSLServer(master_port, factory, ssl_context_factory)
        else:
            service_master = internet.TCPServer(master_port, factory)
        service_master.setServiceParent(application)
    else:
        if ssl_context_factory:
            service_master = reactor.listenSSL(master_port, factory, ssl_context_factory)
        else:
            service_master = reactor.listenTCP(master_port, factory)

    logging.info("CLOUD MASTER started on port %d", master_port)


def stop_master_service():
    global service_master, service_manager
    if service_master:
        if isinstance(service_master, IService):
            # print "SERVICE"
            service_master.stopService()
        else:
            # print "REACTOR"
            service_master.stopListening()
    if service_manager:
        service_manager.stopService()
    from cloud_master import stop_all_threadpools
    stop_all_threadpools()


def main(application=None):
    """
    Startup sequence for CM Master

    :param application: optional Application instance (if used inside twistd)
    :type application: twisted.application.service.Application
    """
    configure_logging(settings.config, "master", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

    ##Twisted logs
    observer = PythonLoggingObserver()
    observer.start()

    log = logging.getLogger("cm")

    log.info("****************************************************************")
    log.info("Starting CloudMailing version %s" % VERSION )
    log.info("Serial: %s" % settings.SERIAL)
    log.info("Twisted version %s", twisted.version.short())
    log.info("****************************************************************")

    ssl_context_factory = make_SSL_context()
    db_conn = connect(settings.MASTER_DATABASE)

    # attach the service to its parent application
    apiService = get_api_service(application, ssl_context_factory=ssl_context_factory)
    start_master_service(application, ssl_context_factory=ssl_context_factory)
