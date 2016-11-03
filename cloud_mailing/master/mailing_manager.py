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
import os
import time
from datetime import datetime, timedelta

from twisted.internet import task, defer

from ..common import settings
from . import settings_vars
from .send_recipients_task import SendRecipientsTask
from .models import Mailing, MailingRecipient, MAILING_STATUS, RECIPIENT_STATUS, MAILING_TYPE
from ..common.db_common import get_db
from ..common.singletonmixin import Singleton


class MailingManager(Singleton):
    """The CM mailing queue.

    Manage mailing relayers, keeping track of the existing connections,
    each connection's responsibility in term of messages. Create
    more relayers if the need arises.

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
        self.filling_queue_running = False
        self.next_time_for_check_orphan_recipients = time.time() + 60
        self.tasks = []

    def start_tasks(self):
        for fn, delay, startNow in ((self.update_status_for_finished_mailings, 60, False),
                                    (self.check_orphan_recipients, 10, False),
                                    (self.retrieve_customized_content, 60, False),
                                    (self.purge_customized_content, 3600, False),
                                    (SendRecipientsTask.getInstance().run, 10, False)
                                    ):
            t = task.LoopingCall(self.task_wrapper(fn))
            t.start(delay, now=startNow).addErrback(self.eb_tasks, fn.__name__)
            self.tasks.append(t)
        self.log.info("Mailing manager started")

    def stop_tasks(self):
        for t in self.tasks:
            t.stop()
        self.tasks = []
        self.log.info("Mailing manager stopped")

    def task_wrapper(self, task_fn):
        logger = logging.getLogger('tasks')
        @defer.inlineCallbacks
        def _task():
            try:
                logger.debug("Running task '%s'", task_fn.__name__)
                yield defer.maybeDeferred(task_fn)
            except Exception as ex:
                logger.exception("Exception in task '%s'", task_fn.__name__)
        _task.__name__ = task_fn.__name__
        return _task

    def eb_tasks(self, failure, name):
        logging.getLogger('tasks').error("Failure in task '%s': %s", name, failure)

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

    def pause_mailing(self, mailing):
        """
        Put the mailing in pause and clear master and satellite queues and memory from any related data
        @param mailing: mailing to pause
        """
        mailing.status = MAILING_STATUS.PAUSED
        mailing.save()

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
        self.log.debug("close_mailing(%d): mailing_temp_queue cleaned", mailing.id)

        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            mailing_master.close_mailing_on_satellites(mailing)

    def check_orphan_recipients(self):
        if time.time() > self.next_time_for_check_orphan_recipients:
            self.log.debug("check_orphan_recipients")
            t0 = time.time()

            def _set_next_time(result, delay):
                count = result and sum(map(lambda x: len(x[1]), result)) or 0
                self.log.debug("check_orphan_recipients() finished for %d orphans in %.1fs", count, time.time() - t0)
                if count:
                    delay = 10
                self.next_time_for_check_orphan_recipients = time.time() + delay

            from .cloud_master import mailing_portal

            if mailing_portal:
                mailing_master = mailing_portal.realm
                return mailing_master.check_recipients_in_clients() \
                    .addCallback(_set_next_time, 120) \
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

    def purge_customized_content(self):
        retention_days = settings_vars.get_int(settings_vars.CUSTOMIZED_CONTENT_RETENTION_DAYS)
        retention_seconds = retention_days * 86400

        log = self.log.getChild("purge")
        log.debug("purge_customized_content: starting scanning customized contents (retention days = %d)", retention_days)

        count = 0
        now = time.time()

        import glob
        for entry in glob.glob(os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, "cust_ml_*.rfc822*")):
            # noinspection PyBroadException
            try:
                modification_time = os.stat(entry).st_mtime
                log.log(1, "Find file '%s': %.1f days old", entry, (now - modification_time) / 86400)
                if now - modification_time > retention_seconds:
                    log.debug("Remove file '%s'", entry)
                    os.remove(entry)
                    count += 1
                # pylint: disable-msg=W0703
            except Exception:
                log.exception("Can't remove customized file '%s'", entry)

        if count:
            log.info("purge_customized_content: removed %d files in %.1f seconds", count, time.time() - now)


def start_mailing_manager():
    manager = MailingManager.getInstance()
    assert(isinstance(manager, MailingManager))
    manager.start_tasks()

    return manager


