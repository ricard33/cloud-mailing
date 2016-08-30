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
import os

import time
from bson import ObjectId
import errno

from twisted.spread import pb, util
from twisted.internet import reactor, defer
from twisted.python import failure
from twisted.cred import credentials
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.spread.util import CallbackPageCollector

from . import settings_vars
from .mail_customizer import MailCustomizer
from .models import MailingRecipient, Mailing
from ..common.config_file import ConfigFile
from ..common import settings
from ..common.models import Settings
from .mailing_sender import MailingSender, getAllPages
from .. import __version__ as VERSION

log = logging.getLogger("cloud")

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
        self.master.callRemote('get_mailing_manager', {
            'version': VERSION,
            'settings': dict([(s['var_name'], s['var_value'])
                              for s in Settings._get_collection().find({}, projection={'_id': False, 'var_name': True, 'var_value': True})])
        }) \
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
        return map(lambda x: str(x['_id']), MailingRecipient._get_collection().find(projection=('_id',)))

    def remote_check_recipients(self, recipient_ids):
        """
        Returns a dictionary mapping for each input id the corresponding recipient object, nor None is not found.
        """
        log.debug('check_recipients(...%d recipients...)', len(recipient_ids))
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

    def remote_get_customized_content(self, collector, mailing_id, recipient_id):
        """
        Ask the satellite to return the customized content for a recipient.

        :param mailing_id: mailing id where the recipient is (used to get the file name without making a db query.
        :param recipient_id: recipient id
        :return: StringPager containing the email content
        """
        log.debug("get_customized_content(%d, %s)", mailing_id, recipient_id)
        file_name = MailCustomizer.make_file_name(mailing_id, recipient_id)
        fullpath = os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, file_name)
        if os.path.exists(fullpath):
            def _remove_file():
                log.debug("Removing customized file '%s'", fullpath)
                os.remove(fullpath)
            util.FilePager(collector, file(fullpath, 'rt'), callback=_remove_file)
        else:
            log.error("Requested customized content not found: %s", fullpath)
            return defer.fail(IOError(errno.ENOENT, "No such file or directory", fullpath))

    def remote_prepare_getting_recipients(self, count):
        """
        Ask satellite for how many recipients he want, and for its paging collector.
        The satellite should return a tuple (wanted_count, collector)
        :param count: proposed recipients count
        :return: a deferred
        """
        log.debug("prepare_getting_recipients(%d)", count)

        temp_queue_count = MailingRecipient.search(finished=False).count()
        mailing_queue_min_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MIN_SIZE)
        mailing_queue_max_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_SIZE)

        if temp_queue_count >= mailing_queue_min_size:
            log.debug("Queue is full. Cancelling recipients request.")
            return 0, None
        count = min(count, mailing_queue_max_size - temp_queue_count)
        log.debug("Requesting %d recipients...", count)

        d = defer.Deferred()
        collector = CallbackPageCollector(d.callback)
        d.addCallbacks(self.mailing_queue.cb_get_recipients, self.mailing_queue.eb_get_recipients, callbackArgs=[time.time()])
        return count, collector


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


