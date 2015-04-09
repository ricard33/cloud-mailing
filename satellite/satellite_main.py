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
from twisted.internet import reactor, ssl
from twisted.python.log import PythonLoggingObserver

from .. import __version__ as VERSION
from ..common import settings
from ..common.cm_logging import configure_logging
from ..common import colored_log

service_satellite = None

log = logging.getLogger("cloud")

def start_satellite_service(application=None, master_ip='localhost', master_port=33620, ssl_context_factory=None):
    global service_satellite

    ##Twisted logs
    from twisted.python.log import PythonLoggingObserver
    observer = PythonLoggingObserver()
    observer.start()

    ##Services

    from cloud_client import get_cloud_client_factory
    factory = get_cloud_client_factory()

    log.info('Trying to connect to Master on %s:%d' % (master_ip, master_port))
    if application:
        if ssl_context_factory:
            service_satellite = internet.SSLClient(master_ip, master_port, factory, ssl_context_factory)
        else:
            service_satellite = internet.TCPClient(master_ip, master_port, factory)
        service_satellite.setServiceParent(application)
    else:
        if ssl_context_factory:
            service_satellite = reactor.connectSSL(master_ip, master_port, factory, ssl_context_factory)
        else:
            service_satellite = reactor.connectTCP(master_ip, master_port, factory)

    # logging.info("CLOUD MASTER started on port %d", master_port)


def stop_satellite_service():
    global service_satellite
    if service_satellite:
        if isinstance(service_satellite, IService):
            # print "SERVICE"
            service_satellite.stopService()
        # else:
        #     # print "REACTOR"
        #     service_satellite.disconnect()  # don't known the function name


def main(application=None):
    """
    Startup sequence for CM Satellite

    :param application: optional Application instance (if used inside twistd)
    :type application: twisted.application.service.Application
    """
    configure_logging(settings.config, "satellite", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

    ##Twisted logs
    observer = PythonLoggingObserver()
    observer.start()

    log = logging.getLogger("cm")

    log.info("****************************************************************")
    log.info("Starting CloudMailing SATELLITE version %s" % VERSION )
    log.info("Serial: %s" % settings.SERIAL)
    log.info("Twisted version %s", twisted.version.short())
    log.info("****************************************************************")

    ssl_context_factory = ssl.ClientContextFactory()
    db_conn = connect(settings.SATELLITE_DATABASE)

    # attach the service to its parent application
    start_satellite_service(application=application, master_ip=settings.MASTER_IP, master_port=settings.MASTER_PORT,
                            ssl_context_factory=ssl_context_factory)
