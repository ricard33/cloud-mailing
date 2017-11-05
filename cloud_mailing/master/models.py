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

import email
import email.parser
import email.policy
import time
from datetime import datetime, timedelta

from bson import DBRef, ObjectId
from mogo import Model, Field, EnumField, ReferenceField
from twisted.internet import defer

from ..common.encoding import force_str, force_bytes
from ..common.email_tools import header_to_unicode
from ..common.models import Sequence

DATABASE = "cm_master"

_ = lambda x: x


class _Model(dict):
    """
    A simple model that wraps mongodb document
    """
    __getattr__ = dict.get
    __delattr__ = dict.__delitem__
    __setattr__ = dict.__setitem__

    @classmethod
    def grab(_class, id):
        document = _class({
            "_id": id
        })
        document.reload()
        return document

    def save(self):
        if not self._id:
            self.collection.insert(self)
        else:
            self.collection.update(
                { "_id": ObjectId(self._id) }, self)

    def reload(self):
        if self._id:
            self.update(self.collection\
                    .find_one({"_id": ObjectId(self._id)}))

    def remove(self):
        if self._id:
            self.collection.remove({"_id": ObjectId(self._id)})
            self.clear()



class User(Model):
    # id              = AutoField(primary_key=True)
    username        = Field(required=True)
    password        = Field(required=True)
    is_superuser    = Field(bool, default=False)
    groups          = Field()       # group names list


class CloudClient(Model):
    # id              = AutoField(primary_key=True)
    serial          = Field(required=True)   # Serial of the client
    enabled         = Field(bool, default=True, required=True)  # Allows to activate or deactivate a client
    paired          = Field(bool, default=False, required=True)  # True when the client is currently connected
    date_paired     = Field(datetime)       # Date of the last successful pairing
    shared_key      = Field()
    domain_affinity = Field()
    group           = Field()  # group name, empty for default
    version         = Field()
    settings        = Field()

    _id_type = int

    # class Meta:
    #     database = DATABASE
    #     collection = "cloud_client"
    #
    #     indices = (
    #         Index("serial"),
    #     )

    def save(self, *args, **kwargs):
        if not self._id:
            super(Model, self).__setitem__(self._id_field,Sequence.get_next('cloud_client_id'))
        return super(CloudClient, self).save(*args, **kwargs)


class MAILING_TYPE:
    REGULAR     = 'REGULAR'
    OPENED      = 'OPENED'
    RECURRING   = 'RECURRING'
    ABSPLIT     = 'ABSPLIT'

mailing_types = (
    MAILING_TYPE.REGULAR,
    MAILING_TYPE.OPENED,
)

class MAILING_STATUS:
    FILLING_RECIPIENTS = 'FILLING_RECIPIENTS'
    READY              = 'READY'
    RUNNING            = 'RUNNING'
    PAUSED             = 'PAUSED'
    FINISHED           = 'FINISHED'

relay_status = (MAILING_STATUS.FILLING_RECIPIENTS,
                MAILING_STATUS.READY,
                MAILING_STATUS.RUNNING,
                MAILING_STATUS.PAUSED,
                MAILING_STATUS.FINISHED)


class RECIPIENT_STATUS:
    READY              = 'READY'
    FINISHED           = 'FINISHED'
    TIMEOUT            = 'TIMEOUT'
    GENERAL_ERROR      = 'GENERAL_ERROR'
    ERROR              = 'ERROR'
    WARNING            = 'WARNING'
    IN_PROGRESS        = 'IN PROGRESS'

recipient_status = (RECIPIENT_STATUS.READY,
                    RECIPIENT_STATUS.IN_PROGRESS,  # TODO remove this status (unused on master)
                    RECIPIENT_STATUS.WARNING,
                    RECIPIENT_STATUS.FINISHED,
                    RECIPIENT_STATUS.ERROR,
                    RECIPIENT_STATUS.TIMEOUT,
                    RECIPIENT_STATUS.GENERAL_ERROR,
                    )


class Mailing(Model):
    # id              = AutoField(primary_key=True)
    type            = EnumField(mailing_types, default=MAILING_TYPE.REGULAR, required=True)
    owner_guid      = Field()       # Free GUID used to identify mailings created by API user.
    satellite_group = Field()       # group name, empty for default
    # TODO Should we keep this?
    domain_name     = Field()       # Related domain name = identity of sender.
    mail_from       = Field(required=True)
    sender_name       = Field()
    subject         = Field()
    header          = Field()
    body            = Field()
    testing         = Field(bool, default=False)  #If True, emails are sent to a testing SMTP server instead of the real one.
    backup_customized_emails = Field(bool, default=False)  # If True, customized emails will be included in recipients reports.
    read_tracking   = Field(bool, default=True)  # If True, read tracking image are added to html bodies
    click_tracking  = Field(bool, default=False)  # If True, links found into html bodies are converted to allow clicks tracking
    tracking_url    = Field()  # Base url for all tracking links
    url_encoding    = Field()
    dkim            = Field()  # dkim settings (dictionary). Fields are enabled (Default=True), selector, domain, privkey
    feedback_loop   = Field()  # Settings needed to implement the Google Feedback Loop requirements (dictionary)
                               # Fields are `campain_id`, `customer_id`, `mail_type_id`, `sender_id`
                               # and `dkim` which contains dkim settings for fbl domain. All are optionals. If not provided,
                               # defaults are (in order): 'mailing.id', 'mailing.domain_name', 'mailing.type'.
                               # 'sender_id' and 'dkim' are taken from global settings.
    submit_time     = Field(datetime, default=datetime.utcnow)
    scheduled_start = Field()
    scheduled_duration = Field(int)  # Mailing duration in minutes
    scheduled_end   = Field()  # Can be set to specify an imperative ending date. Else, mailing will end when its recipients queue is empty.
    start_time      = Field()  # Real start date of this mailing, filled when first recipient is handled.
    end_time        = Field()  # Real end date of this mailing, filled when the mailing is closed, what ever the reason is.
    status          = EnumField(relay_status, default=MAILING_STATUS.FILLING_RECIPIENTS)
    dont_close_if_empty = Field(bool, default=False)
    total_recipient = Field(int, default=0)
    total_sent      = Field(int, default=0)
    total_pending   = Field(int, default=0)
    total_error     = Field(int, default=0)
    total_softbounce= Field(int, default=0)
    # Add total_soft_bounce here (Q: should we remove soft-bounces from pending ?)
    created         = Field(datetime, default=datetime.utcnow)
    modified        = Field(datetime, default=datetime.utcnow)

    # class Meta:
    #     database = DATABASE
    #     collection = "mailing"
    #
    #     indices = (
    #         Index("id"),
    #     )

    _id_type = int

    def __init__(self, *args, **kwargs):
        super(Mailing, self).__init__(*args, **kwargs)
        if self.mail_from:
            self.domain_name = self.mail_from.split('@')[1]

    def save(self, *args, **kwargs):
        if not self._id:
            super(Model, self).__setitem__(self._id_field, Sequence.get_next('mailing_id'))
        self.modified = datetime.utcnow()
        return super(Mailing, self).save(*args, **kwargs)

    @staticmethod
    def create_from_message(msg,
                            mail_from=None, sender_name=None,
                            scheduled_start=None, scheduled_duration=None):
        assert(isinstance(msg, email.message.Message))

        text = msg.as_bytes()
        p = text.find(b"\n\n")
        header = text[:p+2]
        body = text[p+2:]
        if not mail_from:
            name, mail_from = email.utils.parseaddr(header_to_unicode(msg.get("From")))
            if not sender_name:
                sender_name = name
        if not mail_from:
            raise RuntimeError("'mail_from' must be defined or 'From' field must be present into Message object.")

        sender_name = sender_name or ""
        mailing = Mailing(mail_from=mail_from, sender_name=sender_name,
                          subject=header_to_unicode(msg.get("Subject")),
                          header=header, body=body,
                          scheduled_start=scheduled_start, scheduled_duration=scheduled_duration)
        mailing.save()
        return mailing

    def __str__(self):
        return "%d:%s" % (self.id, self.mail_from)

    def full_remove(self):
        """
        Remove the mailing and all its recipients
        """
        MailingRecipient.remove({'mailing.$id': self.id})
        self.delete()

    def activate(self):
        """Activate the mailing, allowing it to be handled by the mailing sender."""
        if self.status != MAILING_STATUS.FILLING_RECIPIENTS:
            raise ValueError(_('Only mailings in FILLING_RECIPIENTS state can be activated'))
        self.update(status=MAILING_STATUS.READY)

    def update_stats(self):
        results = MailingRecipient._get_collection().aggregate([
            {'$match': { 'mailing.$id': self.id}},
            {'$group': {'_id': "$send_status", 'count': {'$sum': 1}}}
        ])
        values = dict([(d['_id'], d['count']) for d in results])
        self.total_recipient = sum(values.values())
        self.total_pending = values.get('READY', 0) + values.get('IN_PROGRESS', 0) + values.get('WARNING', 0)
        self.total_sent = values.get('FINISHED', 0)
        self.total_error = values.get('ERROR', 0) + values.get('GENERAL_ERROR', 0)

    def get_message(self):
        """
        Returns the mailing content as email message object.
        """
        mparser = email.parser.BytesFeedParser(policy=email.policy.default)
        mparser.feed(force_bytes(self.header))
        mparser.feed(force_bytes(self.body))
        return mparser.close()


class MailingRecipient(Model):
    # id              = AutoField(primary_key=True)
    mailing         = ReferenceField(Mailing, required=True)
    tracking_id     = Field()
    contact         = Field()  # Python dictionary containing all recipient fields
    email           = Field(required=True)
    domain_name     = Field(required=True)   # Recipient's domain name
    first_try  = Field(datetime)
    next_try   = Field(datetime, required=True) # TODO maybe a int from EPOCH would be faster
    try_count  = Field(int)
    send_status     = EnumField(recipient_status, default=RECIPIENT_STATUS.READY)
    reply_code     = Field(int)
    reply_enhanced_code = Field()
    reply_text = Field()
    smtp_log         = Field()
    dsn              = Field()  # Delivery Status Notification (if received) RFC-3464
    in_progress     = Field(bool, default=False)  # added to a satellite for sending
    report_ready    = Field(bool, default=False)  # data ready to report to API client
    cloud_client    = Field()   # help_text="Client used to send the email (serial)
    date_delegated  = Field(datetime)    # When this recipient has been delegated to the client.
    primary         = Field(bool, default=False)  # if true, this recipient should be addressed in priority
    created         = Field(datetime, default=datetime.utcnow)
    modified        = Field(datetime, default=datetime.utcnow)

    # class Meta:
    #     database = DATABASE
    #     collection = "mailing_recipient"
    #
    #     indices = (
    #         Index("serial"),
    #     )

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.modified = datetime.utcnow()
        return super(MailingRecipient, self).save(*args, **kwargs)

    def update_send_status(self, send_status, smtp_code=None, smtp_e_code=None, smtp_message=None, in_progress=False,
                           smtp_log=None):
        self.send_status = send_status
        if send_status == RECIPIENT_STATUS.FINISHED:
            self.next_try = datetime.utcnow()
        self.reply_code = smtp_code and smtp_code or None
        self.reply_enhanced_code = smtp_e_code and smtp_e_code or None
        self.reply_text = smtp_message and smtp_message or None
        self.smtp_log = smtp_log and smtp_log or None
        self.in_progress = in_progress

    def set_send_mail_next_time(self):
        """
        This implement the mailing specific strategy for retries.
        """
        self.in_progress = False
        if self.try_count < 3:
            self.next_try = datetime.utcnow() + timedelta(minutes=10)
        elif self.try_count < 10:
            self.next_try = datetime.utcnow() + timedelta(minutes=60)
        else:
            self.next_try = datetime.utcnow() + timedelta(hours=6)


class MailingHourlyStats(Model):
    sender      = Field()   # Serial of the sender
    date        = Field(datetime)
    epoch_hour  = Field(int)
    sent        = Field(int, default=0)
    failed      = Field(int, default=0)
    tries       = Field(int, default=0)  # Total tentatives count, including sent, failed and temporary failed.

    # class Meta:
    #     database = DATABASE
    #     collection = "mailing_hourly_stats"
    #
    #     indices = (
    #         Index("serial"),
    #         Index("epoch_hour"),
    #     )

    @staticmethod
    def __generic_update(serial, operations):
        r = MailingHourlyStats.update({'epoch_hour': int(time.time() / 3600), 'sender': serial},
                                      operations,
                                      upsert=True,
                                      w=1)
        if r is None or not r['updatedExisting']:
            # entry = MailingHourlyStats.search_or_create(epoch_hour=int(time.time() / 3600), sender=serial)
            entry = MailingHourlyStats.grab(r['upserted'])
            entry.update(date=datetime.utcnow().replace(minute=0, second=0, microsecond=0))

    @staticmethod
    def add_sent(serial):
        MailingHourlyStats.__generic_update(serial, {'$inc': {'sent': 1, 'tries': 1}})

    @staticmethod
    def add_failed(serial):
        MailingHourlyStats.__generic_update(serial, {'$inc': {'failed': 1, 'tries': 1}})

    @staticmethod
    def add_try(serial):
        MailingHourlyStats.__generic_update(serial, {'$inc': {'tries': 1}})


class SenderDomain(Model):
    domain_name   = Field(required=True)
    dkim          = Field()  # dkim settings (dictionary). Fields are enabled (Default=True), selector, domain, privkey

