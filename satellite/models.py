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

from mogo import Model, Field, EnumField, ReferenceField

from datetime import datetime, timedelta
import time
from common.models import Sequence


class RECIPIENT_STATUS:
    READY              = 'READY'
    FINISHED           = 'FINISHED'
    TIMEOUT            = 'TIMEOUT'
    GENERAL_ERROR      = 'GENERAL_ERROR'
    ERROR              = 'ERROR'
    WARNING            = 'WARNING'
    IN_PROGRESS        = 'IN PROGRESS'

recipient_status = (RECIPIENT_STATUS.READY,
                    RECIPIENT_STATUS.IN_PROGRESS,
                    RECIPIENT_STATUS.WARNING,
                    RECIPIENT_STATUS.FINISHED,
                    RECIPIENT_STATUS.ERROR,
                    RECIPIENT_STATUS.TIMEOUT,
                    RECIPIENT_STATUS.GENERAL_ERROR,
                    )


class Mailing(Model):
    """Used to store headers and body."""
    # id              = models.IntegerField(primary_key=True)  # Should be the same as mailing_id in Master
    testing         = Field(bool, default=False)    # If True, emails are sent to a testing SMTP server instead of the real one.
    # advanced_template = models.BooleanField(default=False, help_text="If True, emails will be customized with Jinja2 templating engine")
    read_tracking   = Field(bool, default=True)     # If True, read tracking image are added to html bodies
    click_tracking  = Field(bool, default=False)    # If True, links found into html bodies are converted to allow clicks tracking
    body_downloaded = Field(bool, default=False)
    header          = Field()
    body            = Field()
    tracking_url    = Field()       # Base url for all tracking links
    deleted         = Field(bool, default=False)    # Mailing deletion requested. Will occur once all its recipients will be removed.

    created         = Field(datetime, default=datetime.utcnow)
    modified        = Field(datetime, default=datetime.utcnow)

    _id_type = int

    def __unicode__(self):
        return u"Queue[%d]" % self.id

    def save(self, *args, **kwargs):
        if not self._id:
            raise ValueError("Mailing model: An id have to be provided")
            # super(Model, self).__setitem__(self._id_field, Sequence.get_next('mailing_id'))
        self.modified = datetime.utcnow()
        return super(Mailing, self).save(*args, **kwargs)


class MailingRecipient(Model):
    # id              = AutoField(primary_key=True)
    # recipient_id     = models.IntegerField(db_index=True)   # ID on master
    mailing         = ReferenceField(Mailing, required=True)
    tracking_id     = Field()
    contact_data    = Field()  # Python dictionary containing all recipient fields
    email           = Field(required=True)
    mail_from       = Field(required=False)
    sender_name     = Field()
    domain_name     = Field(required=True)   # Recipient's domain name
    first_try       = Field(datetime)
    next_try        = Field(datetime) # TODO maybe a int from EPOCH would be faster
    try_count       = Field(int)
    send_status     = EnumField(recipient_status, default=RECIPIENT_STATUS.READY)
    reply_code      = Field(int)
    reply_enhanced_code = Field()
    reply_text      = Field()
    smtp_log        = Field()
    in_progress     = Field(bool, default=False)  # added in temp queue
    created         = Field(datetime, default=datetime.utcnow)
    modified        = Field(datetime, default=datetime.utcnow)
    finished        = Field(bool, default=False)  # True if this recipient have been handled (successfully or not) and should be returned back to the master.

    def __unicode__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.modified = datetime.utcnow()
        return super(MailingRecipient, self).save(*args, **kwargs)

    def set_send_mail_in_progress(self):
        self.send_status = RECIPIENT_STATUS.IN_PROGRESS
        if self.try_count is None:
            self.try_count = 0
        self.try_count += 1
        self.in_progress = True
        if not self.first_try:
            self.first_try = datetime.utcnow()
        self.next_try = datetime.utcnow()
        self.save()

    def update_send_status(self, send_status, smtp_code=None, smtp_e_code=None, smtp_message=None, in_progress=False,
                           smtp_log=None):
        """
        Updates the contact status.
        """
        self.send_status = send_status
        if send_status == RECIPIENT_STATUS.FINISHED:
            self.next_try = datetime.utcnow()
        self.reply_code = smtp_code and smtp_code or None
        self.reply_enhanced_code = smtp_e_code and smtp_e_code or None
        self.reply_text = smtp_message and unicode(smtp_message, errors='replace') or None
        self.smtp_log = smtp_log and unicode(smtp_log, errors='replace') or None
        self.in_progress = in_progress
        self.save()
        #if send_status in (RECIPIENT_STATUS.ERROR, RECIPIENT_STATUS.GENERAL_ERROR):
            #self.contact.status = CONTACT_STATUS.ERROR
            #self.contact.save()
        #elif send_status == RECIPIENT_STATUS.FINISHED:
            #self.contact.status = CONTACT_STATUS.VALID
            #self.contact.save()

    def set_send_mail_next_time(self):
        """
        This implement the mailing specific strategy for retries and mark this entry as removable from queue.
        """
        self.in_progress = False
        if self.try_count < 3:
            self.next_try = datetime.utcnow() + timedelta(minutes=10)
        elif self.try_count < 10:
            self.next_try = datetime.utcnow() + timedelta(minutes=60)
        else:
            self.next_try = datetime.utcnow() + timedelta(hours=6)
        self.finished = True
        self.save()

    def mark_as_finished(self):
        self.finished = True
        self.save()


class HourlyStats(Model):
    date        = Field(datetime)
    epoch_hour  = Field(int)
    sent        = Field(int, default=0)
    failed      = Field(int, default=0)
    tries       = Field(int, default=0)  # Total tentatives count, including sent, failed and temporary failed.
    up_to_date  = Field(bool, default=False)  # If false, this entry needs to be sent to the CloudMaster.
    
    @staticmethod
    def __generic_update(operations):
        r = HourlyStats.update({'epoch_hour': int(time.time() / 3600)},
                               dict(operations, **{'$set': {'up_to_date': False}}),
                               upsert=True,
                               w=1)
        if r is None or not r['updatedExisting']:
            # entry = HourlyStats.search_or_create(epoch_hour=int(time.time() / 3600))
            entry = HourlyStats.grab(r['upserted'])
            entry.update(date=datetime.utcnow().replace(minute=0, second=0, microsecond=0))

    @staticmethod
    def add_sent():
        HourlyStats.__generic_update({'$inc': {'sent': 1, 'tries': 1}})

    @staticmethod
    def add_failed():
        HourlyStats.__generic_update({'$inc': {'failed': 1, 'tries': 1}})

    @staticmethod
    def add_try():
        HourlyStats.__generic_update({'$inc': {'tries': 1}})



class DomainStats(Model):
    """
    Tracks DNS resolution statistics as well as handled recipients count per domains.
    Also tracks any DNS error on domains resolution. It allows to take decision for domain's recipients if error
    is fatal (no-retry) or not (retry).
    For DNS error, there are two levels:
        - recoverable errors: these errors can be due to temporary network problems. So they should never be fatal for
         concerned recipients.
        - fatal errors: these errors are clearly identified as fatal, i.e. we CAN'T address these recipients in any way
         (for example, the DNS really answer us that the domain doesn't exist). In this case, we will try again later
         (in case in unexpected error with the DNS) but only few times (5 by default).
    """
    domain_name     = Field(required=True)  # Recipient's domain name

    # at recipient level (+1 for each recipient)
    sent        = Field(default=0)
    failed      = Field(default=0)
    tries       = Field(default=0)  # help_text="Total tentatives count, including sent, failed and temporary failed.")

    # at DNS level (+1 for each DNS query)
    dns_tries           = Field(default=0)  # help_text="Total tentatives count, including fatal and temporary failed.")
    dns_temp_errors     = Field(default=0)  # help_text="Errors due to temporal circumstances. Its can be solved later.")
    dns_fatal_errors    = Field(default=0)
    dns_last_error      = Field()           # help_text="Full class name of the exception.")

    dns_cumulative_temp_errors  = Field(default=0)  # help_text="This counter is never reset")
    dns_cumulative_fatal_errors = Field(default=0)  # help_text="This counter is never reset")

    created         = Field(datetime, default=datetime.utcnow)
    modified        = Field(datetime, default=datetime.utcnow)

    def save(self, *args, **kwargs):
        self.modified = datetime.utcnow()
        return super(DomainStats, self).save(*args, **kwargs)

    @staticmethod
    def get_exception_fullname(ex):
        return "%s.%s" % (ex.__class__.__module__, ex.__class__.__name__)

    def check_error(self, ex):
        return DomainStats.get_exception_fullname(ex) == self.dns_last_error

    @staticmethod
    def __generic_update(domain, operations):
        r = DomainStats.update({'domain_name': domain},
                               operations,
                               upsert=True)
        # if r is None or not r['updatedExisting']:
        #     entry = DomainStats.search_or_create(domain_name=domain)
        #     kwargs = {}
        #     for key, value in operations['$inc'].items():
        #         kwargs[key] = value
        #     entry.update(date=datetime.utcnow().replace(minute=0, second=0, microsecond=0), **kwargs)

    @staticmethod
    def add_sent(domain):
        DomainStats.__generic_update(domain, {'$inc': {'sent': 1, 'tries': 1}})

    @staticmethod
    def add_failed(domain):
        DomainStats.__generic_update(domain, {'$inc': {'failed': 1, 'tries': 1}})

    @staticmethod
    def add_try(domain):
        DomainStats.__generic_update(domain, {'$inc': {'tries': 1}})

    @staticmethod
    def add_dns_success(domain):
        DomainStats.__generic_update(domain, {'$inc': {'dns_tries': 1},
                                              '$set': {'dns_temp_errors': 0,
                                                       'dns_fatal_errors': 0,
                                                       'dns_last_error': None}})

    @staticmethod
    def add_dns_temp_error(domain, ex):
        DomainStats.__generic_update(domain, {'$inc': {'tries': 1,
                                                       'dns_tries': 1,
                                                       'dns_temp_errors': 1,
                                                       'dns_cumulative_temp_errors': 1},
                                              '$set': {'dns_last_error': DomainStats.get_exception_fullname(ex)}})


    @staticmethod
    def add_dns_fatal_error(domain, ex):
        DomainStats.__generic_update(domain, {'$inc': {'tries': 1,
                                                       'failed': 1,
                                                       'dns_tries': 1,
                                                       'dns_fatal_errors': 1,
                                                       'dns_cumulative_fatal_errors': 1},
                                              '$set': {'dns_last_error': DomainStats.get_exception_fullname(ex)}})


class DomainConfiguration(Model):
    domain_name = Field(required=True)
#   - 'active_relayers': list of active relayers for this domain
    mx_servers = Field()  # list of MX's IPs addresses
    mx_last_updated = Field(datetime)   # datetime of the last update of MX list
    max_relayers = Field(int)   # the maximum simultaneous relayers for this domain (taken from DB
                                # or None to use the default rule = half of the MX servers)
    cnx_per_mx = Field(int)     # the maximum simultaneous connections per MX server
    max_mx = Field(int)         # the maximum simultaneous connected MX servers


class ActiveQueue(Model):
    domain_name = Field(required=True)
    recipients = Field()
    created = Field(datetime, default=datetime.utcnow)
