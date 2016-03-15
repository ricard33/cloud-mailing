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
import time
from datetime import datetime, timedelta

from twisted.internet import task, defer
from twisted.internet.threads import deferToThread

from cloud_mailing.master.send_recipients_task import SendRecipientsTask
from ..common.db_common import get_db
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
        self.tasks = []

    def start_tasks(self):
        for fn, delay, startNow in ((self.checkState, 5, False),
                                    (self.update_status_for_finished_mailings, 60, False),
                                    (self.check_orphan_recipients, 60, False),
                                    (self.purge_temp_queue_from_finished_and_paused_mailings, 60, False),
                                    (self.retrieve_customized_content, 60, False),
                                    (SendRecipientsTask.getInstance().run, 10, False)
                                    ):
            t = task.LoopingCall(fn)
            t.start(delay, now=startNow)
            self.tasks.append(t)
        self.log.info("Mailing manager started")

    def stop_tasks(self):
        for t in self.tasks:
            t.stop()
        self.tasks = []
        self.log.info("Mailing manager stopped")

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
    def make_recipients_queryset(mailing_id):
        filter = {
            '$and': [
                {'$or': [{'next_try': {'$lte': datetime.utcnow()}},
                         {'next_try': None}]},
                {'$or': [{'in_progress': False}, {'in_progress': None}]},
            ],
            'send_status': {'$in': (RECIPIENT_STATUS.READY,
                                    RECIPIENT_STATUS.WARNING), },
            'mailing.$id': mailing_id,
        }
        return filter

    @defer.inlineCallbacks
    def filling_mailing_queue(self, mailing_filter, rcpt_count, temp_queue_count, mailing_queue_max_size):
        self.log.debug("Starting filling mailing queue...")
        t0 = time.time()
        count = 0
        try:
            db = get_db()

            for mailing in Mailing.find(mailing_filter):
                if mailing['status'] == MAILING_STATUS.READY:
                    yield db.mailing.update({'_id': mailing['_id']}, {'$set': {
                        'status': MAILING_STATUS.RUNNING,
                        'start_time': datetime.utcnow(),
                    }})
                # print "total_recipient: %d  / mailing_queue_max_size: %d / temp_queue_count: %d / rcpt_count: %d"\
                # % (mailing['total_recipient'], mailing_queue_max_size, temp_queue_count, rcpt_count)
                nb_max = max(100, mailing.get('total_pending', 0)
                             * (mailing_queue_max_size - temp_queue_count) / rcpt_count)
                # Quick starter for empty queue
                if temp_queue_count == 0:
                    nb_max = min(1000, nb_max)
                elif temp_queue_count <= 1000:
                    nb_max = min(10000, nb_max)
                # print "nb_max = %d" % nb_max
                rcpt_ids = []
                self.log.debug("Filling mailing queue: selecting max %d recipients from mailing [%d]", nb_max,
                               mailing['_id'])
                filter = MailingManager.make_recipients_queryset(mailing['_id'])
                t1 = time.time()
                selected_recipients = yield db.mailingrecipient.find(filter, sort='next_try', limit=nb_max)
                for rcpt in selected_recipients:
                    yield MailingTempQueue.add_recipient(db, mailing=mailing, recipient=rcpt)
                    rcpt_ids.append(rcpt['_id'])
                    count += 1
                    # if count % 100 == 0:
                    #     print "Added %d..." % count
                self.log.debug("Filling mailing queue: selected %d recipients from mailing [%d] (in %.1f seconds)",
                               len(rcpt_ids), mailing['_id'], time.time() - t1)
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
        class CP:
            def __init__(self, log):
                self.log = log
                self.t0 = time.time()
                self.count = 0


            def check_point(self):
                import inspect
                lineno = inspect.currentframe().f_back.f_lineno
                self.log.debug("checkState() checkpoint %d (line %d): %.1fs" % (self.count, lineno, time.time()-self.t0))
                self.count +=1
                self.t0 = time.time()

        cp = CP(self.log)

        if time.time() < self.nextTime:
            return
        try:
            mailing_queue_max_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_SIZE)
            mailing_queue_min_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MIN_SIZE)

            temp_queue_count = MailingTempQueue.find().count()
            unhandled_temp_queue_count = MailingTempQueue.find({
                '$or': [{'in_progress': False}, {'in_progress': None} ],
                'client': None
            }).count()

            cp.check_point()
            self.log.debug("TempQueue size = %d / unhandled = %d /min queue size = %d / is_filling? %s",
                           temp_queue_count, unhandled_temp_queue_count,
                           mailing_queue_min_size, self.filling_queue_running)

            if temp_queue_count < mailing_queue_min_size and not self.filling_queue_running:
                self.filling_queue_running = True
                mailing_filter = MailingManager.make_mailings_queryset()
                self.log.debug("Filling temp queue with %d active mailings...", Mailing.find(mailing_filter).count())
                results = list(Mailing._get_collection().aggregate([
                    {'$match': mailing_filter},
                    {'$group': {'_id': None, 'sum': {'$sum': '$total_pending'}}}
                ]))  # ['result']
                cp.check_point()
                rcpt_count = results and results[0].get('sum', 0) or 0
                # print "rcpt_count", rcpt_count
                # mailing_ids = [id for id in mailings.values_list('id', flat=True)]
                if rcpt_count == 0:  # no more mailings
                    self.log.debug("Filling temps queue: no eligible recipient. Release filling queue lock.")
                    self.filling_queue_running = False
                    if temp_queue_count == 0:
                        self.nextTime = time.time() + 20
                        return
                else:
                    self.log.debug("Filling temps queue: %d recipients are eligible.", rcpt_count)

                    def _release_lock():
                        self.log.debug("Release filling queue lock")
                        self.filling_queue_running = False

                    cp.check_point()
                    # return deferToThread(self.filling_mailing_queue, mailing_filter, rcpt_count, temp_queue_count,
                    #                      mailing_queue_max_size).addBoth(lambda x: _release_lock())
                    return self.filling_mailing_queue(mailing_filter, rcpt_count, temp_queue_count,
                                         mailing_queue_max_size).addBoth(lambda x: _release_lock())

        except:
            self.log.exception("Unknown exception in checkState()")
        cp.check_point()

    def clear_all_send_mail_in_progress(self):
        t0 = time.time()
        self.log.debug("Resetting IN PROGRESS flag for all mailing recipients...")
        MailingRecipient.update({'$or': [{'send_status': RECIPIENT_STATUS.IN_PROGRESS}, {'in_progress': True}]},
                                {'$set': {'send_status': RECIPIENT_STATUS.READY, 'in_progress': False}},
                                multi=True)
        MailingTempQueue.update({'in_progress': True}, {'$set': {'in_progress': False}}, multi=True)
        self.log.debug("Reset done in %.1fs", time.time() - t0)

    def clear_temp_queue(self):
        self.log.debug("Clearing temp queue from obsolete entries...")
        MailingTempQueue.remove({'mailing__status': MAILING_STATUS.FINISHED})

    @defer.inlineCallbacks
    def update_status_for_finished_mailings(self):
        self.log.debug("update_status_for_finished_mailings")
        t0 = time.time()
        db = get_db()
        unfinished_queues = yield db.mailing.find({'status': {'$in': [MAILING_STATUS.READY, MAILING_STATUS.RUNNING, MAILING_STATUS.PAUSED]}},
                                         fields=['_id', 'start_time', 'scheduled_end', 'scheduled_duration', 'type',
                                                     'dont_close_if_empty', 'mail_from'])
        for mailing in unfinished_queues:
            unfinished_recipients_filter = {
                'mailing.$id': mailing['_id'],
                '$or': [{'send_status': {'$in': [RECIPIENT_STATUS.READY, RECIPIENT_STATUS.WARNING]}},
                        {'in_progress': True}]}
            if mailing.get('scheduled_end') and mailing['scheduled_end'] <= datetime.utcnow() \
                    or mailing.get('scheduled_duration') and mailing.get('start_time') and (
                                mailing['start_time'] + timedelta(
                                minutes=mailing['scheduled_duration'])) <= datetime.utcnow():
                self.log.info("Mailing mailing '%s:%s' started on %s has reach its time limit. Closing it.",
                              mailing['_id'], mailing['mail_from'], mailing.get('start_time') and mailing['start_time'].strftime("%Y-%m-%d") or "???")
                yield db.mailingrecipient.update(unfinished_recipients_filter,
                                        {'$set': {'send_status': RECIPIENT_STATUS.TIMEOUT,
                                                  'in_progress': False,
                                                  'reply_code': None,
                                                  'reply_enhanced_code': None,
                                                  'reply_text': None}
                                         },
                                        multi=True)
                self.log.debug("finished_mailing(%d): recipients updated", mailing['_id'])
                self.close_mailing(mailing['_id'])
                self.log.debug("finished_mailing(%d): mailing closed", mailing['_id'])

            elif mailing['type'] != MAILING_TYPE.OPENED and not mailing['dont_close_if_empty']:
                rcpt = yield db.mailingrecipient.find_one(unfinished_recipients_filter)
                if rcpt is None:
                    self.log.info("Mailing '%s:%s' started on %s has no more recipient. Closing it.",
                                  mailing['_id'], mailing['mail_from'], mailing.get('start_time') and mailing['start_time'].strftime("%Y-%m-%d") or "???")
                    self.close_mailing(mailing['_id'])
        self.log.debug("update_status_for_finished_mailings() in %.1fs", time.time() - t0)

    def purge_temp_queue_from_finished_and_paused_mailings(self):
        self.log.debug("purge_temp_queue_from_finished_and_paused_mailings")
        t0 = time.time()
        running_mailing_ids = [m['_id'] for m in Mailing._get_collection().find(
            {'status': {'$nin': (MAILING_STATUS.PAUSED, MAILING_STATUS.FINISHED)}},
            projection=[]
        )]
        all_ids = zip(*[(r['_id'], r['recipient']['_id']) for r in MailingTempQueue._get_collection().find(
            {'mailing.$id': {'$nin': running_mailing_ids}},
            projection=['_id', 'recipient._id'])])


        if all_ids:
            ids_to_remove, recipient_ids = all_ids
            MailingTempQueue.remove({'_id': {'$in': ids_to_remove}})
            MailingRecipient.update({'_id': {'$in': recipient_ids}, 'in_progress': True},
                                    {'$set': {'in_progress': False, 'send_status': RECIPIENT_STATUS.READY}},
                                    multi=True)

            self.log.info("purge_temp_queue_from_finished_and_paused_mailings() in %.1fs", time.time() - t0)

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

        MailingRecipient.update({'mailing.$id': mailing.id, 'in_progress': True}, {'$set': {'in_progress': False}}, multi=True)

    def close_mailing(self, mailing_id):
        self.log.debug("Close mailing %d", mailing_id)
        mailing = Mailing.grab(mailing_id)
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
        # TODO Check why it seems to be broken with very big DB
        if time.time() > self.next_time_for_check_orphan_recipients:
            self.log.debug("check_orphan_recipients")
            t0 = time.time()

            def _set_next_time(result, delay):
                self.log.debug("check_orphan_recipients() finished in %.1fs", time.time() - t0)
                self.next_time_for_check_orphan_recipients = time.time() + delay

            from .cloud_master import mailing_portal

            if mailing_portal:
                mailing_master = mailing_portal.realm
                return mailing_master.check_recipients_in_clients() \
                    .addCallback(_set_next_time, 600) \
                    .addErrback(_set_next_time, 30)
            else:
                self.log.error("Can't get MailingPortal object!")

    def retrieve_customized_content(self):
        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            return mailing_master.retrieve_customized_content()
        else:
            self.log.error("Can't get MailingPortal object!")


def start_mailing_manager():
    manager = MailingManager.getInstance()
    assert(isinstance(manager, MailingManager))
    manager.start_tasks()

    return manager


