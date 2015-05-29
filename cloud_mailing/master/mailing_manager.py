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


import time
import logging
from datetime import datetime, timedelta

from twisted.application import internet
from twisted.internet.threads import deferToThread

from . import settings_vars
from .models import Mailing, MailingTempQueue, MailingRecipient, MAILING_STATUS, RECIPIENT_STATUS, MAILING_TYPE
from ..common.singletonmixin import Singleton


class MailingManager(Singleton):
    """The CM mailing queue.

    Manage mailing relayers, keeping track of the existing connections,
    each connection's responsibility in term of messages. Create
    more relayers if the need arises.

    Someone should press .checkState periodically

    @ivar factory: A callable which returns a ClientFactory suitable for
    making SMTP connections.
    """

    def __init__(self):
        """
        MailingManager constructor.
        """
        Singleton.__init__(self)
        self.queue = None
        self.log = logging.getLogger("mailing")
        self.startTime = time.time()
        self.nextTime = 0
        self.filling_queue_running = False
        self.next_time_for_check_orphan_recipients = time.time() + 60

    def forceToCheck(self):
        self.nextTime = 0

    @staticmethod
    def make_mailings_queryset():
        now = datetime.utcnow()
        filter = {'$and': [
            {'$or': [{'scheduled_start': {'$lte': now}},
                     {'scheduled_start': None}]},
            {'$or': [{'scheduled_end': {'$gt': now}},
                     {'scheduled_end': None}]},
            {'status': {'$in': (MAILING_STATUS.READY, MAILING_STATUS.RUNNING)}},
        ]}
        return filter

    @staticmethod
    def make_recipients_queryset(mailing):
        filter = {
            '$and': [
                {'$or': [{'next_try': {'$lte': datetime.utcnow()}},
                         {'next_try': None}]},
                {'$or': [{'in_progress': False}, {'in_progress': None}]},
            ],
            'send_status': {'$in': (RECIPIENT_STATUS.READY,
                                    RECIPIENT_STATUS.WARNING), },
            'mailing.$id': mailing.id,
        }
        # TODO Missing 'exclude' but it should be useless if 'in_progress' is well filled.
        # queue = MailingRecipient.objects.filter(
        #     Q(smtp_next_time__lte=datetime.utcnow()) | Q(smtp_next_time__isnull=True),
        #     Q(in_progress=False) | Q(in_progress__isnull=True),
        #     send_status__in=(RECIPIENT_STATUS.READY,
        #                      RECIPIENT_STATUS.WARNING),
        #     mailing__in=mailings_qs,
        # ).exclude(
        #     id__in=MailingTempQueue.objects.values_list('recipient__id', flat=True)
        # )
        return filter

    def filling_mailing_queue(self, mailing_filter, rcpt_count, temp_queue_count, mailing_queue_max_size):
        self.log.debug("Starting filling mailing queue...")
        t0 = time.time()
        count = 0
        try:

            for mailing in Mailing.find(mailing_filter):
                    if mailing.status == MAILING_STATUS.READY:
                        mailing.status = MAILING_STATUS.RUNNING
                        mailing.start_time = datetime.utcnow()
                        mailing.save()
                    # print "total_recipient: %d  / mailing_queue_max_size: %d / temp_queue_count: %d / rcpt_count: %d"\
                    # % (mailing.total_recipient, mailing_queue_max_size, temp_queue_count, rcpt_count)
                    nb_max = max(100, (mailing.total_pending or 0)
                                 * (mailing_queue_max_size - temp_queue_count) / rcpt_count)
                    # Quick starter for empty queue
                    if temp_queue_count == 0:
                        nb_max = min(1000, nb_max)
                    elif temp_queue_count <= 1000:
                        nb_max = min(10000, nb_max)
                    # print "nb_max = %d" % nb_max
                    rcpt_ids = []
                    self.log.debug("Filling mailing queue: selecting max %d recipients from mailing [%d]", nb_max,
                                   mailing.id)
                    filter = MailingManager.make_recipients_queryset(mailing)
                    selected_recipients = MailingRecipient.find(filter).sort('next_try').limit(nb_max)
                    for rcpt in selected_recipients:
                        MailingTempQueue.add_recipient(mailing=mailing, recipient=rcpt)
                        rcpt_ids.append(rcpt.id)
                        count += 1
                        # if count % 100 == 0:
                        #     print "Added %d..." % count
                    self.log.debug("Filling mailing queue: selected %d recipients from mailing [%d]", len(rcpt_ids),
                                   mailing.id)
                    if rcpt_ids:
                        n = 100
                        for i in range(0, len(rcpt_ids), n):
                            MailingRecipient.update({'_id': {'$in': rcpt_ids[i:i + n]}}, {'$set': {'in_progress': True}}, multi=True)

                    # Ultimate check before to commit. Maybe mailing has changed its state
                    # if Mailing.search(id=mailing.id, status=MAILING_STATUS.RUNNING).count() == 0:
                    #     transaction.rollback()

            if count:
                self.log.info("Mailing queue successfully filled %d recipients in %.1f seconds.", count,
                              time.time() - t0)
            self.forceToCheck()
        except:
            self.log.exception("Exception using Filling Mailing Queue function.")

    def checkState(self):
        """
        Synchronize with the state of the world, and maybe launch a new
        relay.

        Call me periodically to check I am still up to date.

        @return: None or a Deferred which fires when all of the SMTP clients
        started by this call have disconnected.
        """
        need_to_release = False

        if time.time() < self.nextTime:
            return
        try:
            # TODO Check why it seems to be broken with very big DB
            self.check_orphan_recipients()

            # Delay this call because master port is not ready at startup
            if time.time() - self.startTime > 1 * 60:
                self.update_status_for_finished_mailings()
            self.purge_temp_queue_from_finished_and_paused_mailings()

            mailing_queue_max_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_SIZE)
            mailing_queue_min_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MIN_SIZE)

            temp_queue_count = MailingTempQueue.find().count()
            unhandled_temp_queue_count = MailingTempQueue.find({
                '$or': [{'in_progress': False}, {'in_progress': None} ],
                'client': None
            }).count()

            self.log.debug("TempQueue size = %d / unhandled = %d /min queue size = %d / is_filling? %s",
                           temp_queue_count, unhandled_temp_queue_count,
                           mailing_queue_min_size, self.filling_queue_running)

            if temp_queue_count < mailing_queue_min_size and not self.filling_queue_running:
                self.filling_queue_running = True
                mailing_filter = MailingManager.make_mailings_queryset()
                self.log.debug("Filling temp queue with %d active mailings...", Mailing.find(mailing_filter).count())
                results = Mailing._get_collection().aggregate([
                    {'$match': mailing_filter},
                    {'$group': {'_id': None, 'sum': {'$sum': '$total_pending'}}}
                ])['result']
                rcpt_count = results and results[0].get('sum', 0) or 0
                # print "rcpt_count", rcpt_count
                # mailing_ids = [id for id in mailings.values_list('id', flat=True)]
                if rcpt_count == 0:  # no more mailings
                    self.log.debug("Filling temps queue: no eligible recipient. Release filling queue lock.")
                    self.filling_queue_running = False
                    if temp_queue_count == 0:
                        self.nextTime = time.time() + 60
                        return
                else:
                    self.log.debug("Filling temps queue: %d recipients are eligible.", rcpt_count)

                    def _release_lock():
                        self.log.debug("Release filling queue lock")
                        self.filling_queue_running = False

                    return deferToThread(self.filling_mailing_queue, mailing_filter, rcpt_count, temp_queue_count,
                                         mailing_queue_max_size).addBoth(lambda x: _release_lock())

        except:
            self.log.exception("Unknown exception in checkState()")

    def clear_all_send_mail_in_progress(self):
        t0 = time.time()
        self.log.debug("Resetting IN PROGRESS flag for all mailing recipients...")
        MailingRecipient.update({'$or': [{'send_status': RECIPIENT_STATUS.IN_PROGRESS}, {'in_progress': True}]},
                                {'$set': {'send_status': RECIPIENT_STATUS.READY, 'in_progress': False}},
                                multi=True)
        MailingTempQueue.update({'in_progress': True}, {'in_progress': False}, multi=True)
        self.log.debug("Reset done in %.1fs", time.time() - t0)

    def clear_temp_queue(self):
        self.log.debug("Clearing temp queue from obsolete entries...")
        MailingTempQueue.remove({'mailing__status': MAILING_STATUS.FINISHED})

    def update_status_for_finished_mailings(self):
        self.log.debug("update_status_for_finished_mailings")
        t0 = time.time()
        unfinished_queues = Mailing.find({'status': {'$in': [MAILING_STATUS.READY, MAILING_STATUS.RUNNING, MAILING_STATUS.PAUSED]}})
                                         # fields=('_id', 'start_time', 'scheduled_end', 'scheduled_duration'))
        for mailing in unfinished_queues:
            assert (isinstance(mailing, Mailing))
            unfinished_recipients_filter = {
                'mailing.$id': mailing.id,
                '$or': [{'send_status': {'$in': [RECIPIENT_STATUS.READY, RECIPIENT_STATUS.WARNING]}},
                        {'in_progress': True}]}
            if mailing.scheduled_end and mailing.scheduled_end <= datetime.utcnow() \
                    or mailing.scheduled_duration and mailing.start_time and (
                                mailing.start_time + timedelta(
                                    minutes=mailing.scheduled_duration)) <= datetime.utcnow():
                self.log.info("Mailing mailing '%s' started on %s has reach its time limit. Closing it.",
                              mailing, mailing.start_time and mailing.start_time.strftime("%Y-%m-%d") or "???")
                MailingRecipient.update(unfinished_recipients_filter,
                                        {'send_status': RECIPIENT_STATUS.TIMEOUT,
                                         'in_progress': False,
                                         'reply_code': None,
                                         'reply_enhanced_code': None,
                                         'reply_text': None},
                                        multi=True)
                self.log.debug("finished_mailing(%d): recipients updated", mailing.id)
                self.close_mailing(mailing)
                self.log.debug("finished_mailing(%d): mailing closed", mailing.id)

            elif mailing.type != MAILING_TYPE.OPENED and not mailing.dont_close_if_empty \
                    and MailingRecipient.find_one(unfinished_recipients_filter) is None:
                self.log.info("Mailing '%s' started on %s has no more recipient. Closing it.",
                              mailing, mailing.start_time and mailing.start_time.strftime("%Y-%m-%d") or "???")
                self.close_mailing(mailing)
                # print "update_status_for_finished_mailings: %.1fs" % (time.time() - t0)

    def purge_temp_queue_from_finished_and_paused_mailings(self):
        self.log.debug("purge_temp_queue_from_finished_and_paused_mailings")
        t0 = time.time()
        stopped_mailing_ids = list(Mailing.find(
            {'mailing__status': {'$in': (MAILING_STATUS.PAUSED, MAILING_STATUS.FINISHED)}}))
        if(stopped_mailing_ids):
            remove_result = MailingTempQueue.remove({'mailing.$id': {'$in': stopped_mailing_ids}})
            if remove_result['nRemoved'] > 0:
                MailingRecipient.update({'mailing.$id': {'$in': stopped_mailing_ids}, 'in_progress': True},
                                        {'in_progress': False},
                                        multi=True)
                self.log.info("purge_temp_queue_from_finished_and_paused_mailings: %.1fs", (time.time() - t0))

    def pause_mailing(self, mailing):
        """
        Put the mailing in pause and clear master and satellite queues and memory from any related data
        @param mailing: mailing to pause
        """
        mailing.status = MAILING_STATUS.PAUSED
        mailing.save()
        MailingTempQueue.remove({'mailing.$id': mailing.id})

        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            # For satellites, pausing mailing is the same as closing it.
            mailing_master.close_mailing_on_satellites(mailing)

        MailingRecipient.update({'mailing.$id': mailing.id, 'in_progress': True}, {'in_progress': False}, multi=True)

    def close_mailing(self, mailing):
        self.log.debug("Close mailing %d", mailing.id)
        mailing.status = MAILING_STATUS.FINISHED
        mailing.end_time = datetime.utcnow()
        mailing.update_stats()
        mailing.save()
        MailingTempQueue.remove({'mailing.$id': mailing.id})
        self.log.debug("close_mailing(%d): mailing_temp_queue cleaned", mailing.id)

        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            mailing_master.close_mailing_on_satellites(mailing)

    def check_orphan_recipients(self):
        if time.time() > self.next_time_for_check_orphan_recipients:
            def _set_next_time(result, delay):
                self.next_time_for_check_orphan_recipients = time.time() + delay

            from .cloud_master import mailing_portal

            if mailing_portal:
                mailing_master = mailing_portal.realm
                return mailing_master.check_recipients_in_clients() \
                    .addCallback(_set_next_time, 600) \
                    .addErrback(_set_next_time, 30)
            else:
                self.log.error("Can't get MailingPortal object!")


def _checkState(manager):
    manager.checkState()


def RelayStateHelper(manager, delay):
    return internet.TimerService(delay, _checkState, manager)


def start_mailing_manager():
    manager = MailingManager.getInstance()
    helper = RelayStateHelper(manager, 5)
    manager.log.info("Mailing manager started")
    helper.startService()
    return helper


