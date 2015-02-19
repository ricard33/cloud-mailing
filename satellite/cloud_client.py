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

#
# CloudMailing client
#

import hmac
import logging
from bson import ObjectId

from twisted.spread import pb
from twisted.internet import reactor
from twisted.cred import credentials
from twisted.internet.protocol import ReconnectingClientFactory
from satellite.mail_customizer import MailCustomizer
from satellite.models import MailingRecipient, Mailing
from common.config_file import ConfigFile

log = logging.getLogger("cloud")

from common import settings
from mailing_sender import MailingSender

#pylint: disable-msg=W0404

class CloudClient(pb.Referenceable):
    def __init__(self):
        self.master = None
        self.is_connected = False
        self.mailing_queue = None
        self.ut_mode = False
        
    def remote_is_ready(self):
        return True
    
    def disconnected(self, remoteRef):
        log.warn("Master disconnected!! %s", remoteRef)
        self.is_connected = False
        
    def connected(self, master):
        self.master = master
        self.is_connected = True
        self.master.notifyOnDisconnect(self.disconnected)
        if not self.mailing_queue:
            self.mailing_queue = MailingSender(self, timer_delay = self.ut_mode and 1 or 5,
                                              delay_if_empty = self.ut_mode and 1 or 10)
        self.master.callRemote('get_mailing_manager') \
            .addCallback(self.mailing_queue.cb_get_mailing_manager)

    def remote_activate_unittest_mode(self, activated):
        log.debug("UnitTest Mode set to %s", activated)
        self.ut_mode = activated
        if self.mailing_queue:
            if activated:
                self.mailing_queue.delay_if_empty = 1
                self.mailing_queue.nextTime = 0
            else:
                self.mailing_queue.delay_if_empty = 10
    
    def remote_close_mailing(self, mailing_id):
        """Ask queue to remove all recipients from this mailing id."""
        self.mailing_queue.close_mailing(mailing_id)

    def remote_mailing_changed(self, mailing_id):
        """Informs satellite that mailing content has changed."""
        Mailing.update({'_id': mailing_id}, {'$set': {'body_downloaded': False}})
        import os, glob
        for entry in glob.glob(os.path.join(settings.MAIL_TEMP, MailCustomizer.make_patten_for_queue(mailing_id))):
            try:
                os.remove(entry)
            except Exception:
                log.exception("Can't remove customized file '%s'", entry)

    def remote_get_recipients_list(self):
        """
        Returns the list of currently handled recipient ids.
        """
        return map(lambda x: str(x['_id']), MailingRecipient._get_collection().find(fields=('_id',)))

    def remote_check_recipients(self, recipient_ids):
        """
        Returns a dictionary mapping for each input id the corresponding recipient object, nor None is not found.
        """
        recipients_dict = {}
        for _id in recipient_ids:
            recipients_dict[_id] = None
        for recipient in MailingRecipient._get_collection().find({'_id': {'$in': map(lambda x: ObjectId(x), recipient_ids)}}):
            for field in ('contact_data', 'unsubscribe_id'):
                recipient.pop(field, None)
            recipient['_id'] = str(recipient['_id'])
            recipient['mailing'] = recipient['mailing'].id
            recipients_dict[recipient['_id']] = recipient
        return recipients_dict

    def remote_force_check_for_new_recipients(self):
        """
        Signals to a Satellite that Master has emails that have to be handled immediately.
        So Satellites should ask for new recipients after they have received this call.
        This is useful for test emails.
        """
        self.mailing_queue.check_for_new_recipients()

    def remote_get_all_configuration(self):
        """
        Asks the satellite for its configuration.

        @return: a dictionary representing the current configuration.
        """
        return {
            'CM_MAILING_QUEUE_TEST_TARGET_IP': settings.TEST_TARGET_IP,
            'CM_MAILING_QUEUE_TEST_TARGET_PORT': settings.TEST_TARGET_PORT,
            'CM_MAILING_QUEUE_TEST_FAKE_DNS': settings.TEST_FAKE_DNS,
            'CM_MAILING_QUEUE_USE_LOCAL_DNS_CACHE': settings.USE_LOCAL_DNS_CACHE,
            'CM_MAILING_QUEUE_LOCAL_DNS_CACHE_FILE': settings.LOCAL_DNS_CACHE_FILE,
        }


class CloudClientFactory(pb.PBClientFactory, ReconnectingClientFactory):

    cloud_client = None
    
    def __init__(self, cloud_client):
        pb.PBClientFactory.__init__(self)
        self.ipaddress = None
        self.cloud_client = cloud_client
        self.maxDelay = 60  # Max delay for ReconnectingClientFactory

    def clientConnectionMade(self, broker):
        log.info('Started to connect.')
        self.resetDelay()
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)
        pb.PBClientFactory.clientConnectionMade(self, broker)
        def1 = self.login(credentials.UsernamePassword(settings.SERIAL, hmac.HMAC(config.get("MAILING", 'shared_key', '!')).hexdigest()),
                          client=self.cloud_client)
        def1.addCallback(self.cloud_client.connected)
        

    def buildProtocol(self, addr):
        log.info('CloudClientFactory connected to %s' % addr)
        return pb.PBClientFactory.buildProtocol(self, addr)

    #noinspection PyMethodOverriding
    def clientConnectionLost(self, connector, reason):
        log.warn('Lost connection.  Reason: %s', reason.getErrorMessage())
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.warn('Connection failed. Reason: %s', reason.getErrorMessage())
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


def get_cloud_client_factory():
    client = CloudClient()
    factory = CloudClientFactory(client)
    return factory


