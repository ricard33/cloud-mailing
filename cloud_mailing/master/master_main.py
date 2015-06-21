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
import argparse
import os
import random
import pymongo
from mogo import connect
import sys
import time
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
from ..common.config_file import ConfigFile
from .xmlrpc_api import make_xmlrpc_server, CloudMailingRpc

service_master = None
service_manager = None

def get_api_service(application=None, interface='', port=33610, ssl_context_factory=None):
    """
    Return a service suitable for creating an application object.

    This service is a simple web server that serves files on port 8080 from
    underneath the current working directory.
    """
    # if not ssl_context_factory:
    #     ssl_context_factory = make_SSL_context()

    # check if an API KEY exists?
    config = ConfigFile()
    config.read(settings.CONFIG_FILE)

    key = config.get('CM_MASTER', 'API_KEY', '')
    if not key:
        logging.warn("API KEY not found. Generating a new one...")
        config.set('CM_MASTER', 'API_KEY', "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]))
        with file(settings.CONFIG_FILE, 'wt') as f:
            config.write(f)

    webServer = server.Site( make_xmlrpc_server() )
    # webServer = server.Site( CloudMailingRpc(useDateTime=True) )
    if application:
        if ssl_context_factory:
            apiService = internet.SSLServer(port, webServer, ssl_context_factory, interface=interface)
        else:
            apiService = internet.TCPServer(port, webServer, interface=interface)
        apiService.setServiceParent(application)
    else:
        if ssl_context_factory:
            apiService = reactor.listenSSL(port, webServer, ssl_context_factory, interface=interface)
        else:
            apiService = reactor.listenTCP(port, webServer, interface=interface)

    logging.info("Supervisor XMLRPC%s server started on port %d", ssl_context_factory and " SSL" or "", port)
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
    parser = argparse.ArgumentParser(description='Start the Master process for CloudMailing.')
    parser.add_argument('-p', '--port', type=int, default=33620, help='port number for Master MailingManager (default: 33620)')
    parser.add_argument('--api-interface', default='', help='network interface (IP address) on which API should listen (default: <empty> = all)')
    parser.add_argument('--api-port', type=int, default=33610, help='port number for API (default: 33610)')
    parser.add_argument('--api-dont-use-ssl', action='store_true', default=False, help='ask API to not use secure port (SSL)')

    args = parser.parse_args()

    configure_logging("master", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

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
    db_conn = None
    while not db_conn:
        try:
            db_conn = connect(settings.MASTER_DATABASE)
            log.info("Connected to database '%s'", settings.MASTER_DATABASE)
        except pymongo.errors.ConnectionFailure:
            log.error("Failed to connect to database server!")
            # special case for MailFountain hardward only
            if os.path.exists("/data/mongodb/mongod.lock"):
                os.remove("/data/mongodb/mongod.lock")
                os.system('su -m mongodb -c "mongod --config /usr/local/etc/mongodb.conf --dbpath /data/mongodb/ --repair"')
                os.system("service mongod start")
            else:
                log.info("   Trying again in 5 seconds...")
                time.sleep(5)

    # attach the service to its parent application
    apiService = get_api_service(application, port=args.api_port,
                                 interface=args.api_interface,
                                 ssl_context_factory=not args.api_dont_use_ssl and ssl_context_factory or None)
    start_master_service(application, master_port=args.port, ssl_context_factory=ssl_context_factory)
