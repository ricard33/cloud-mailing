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

# from django.contrib.auth import get_user_model
from datetime import datetime
import uuid
import factory
from ..models import Mailing, MailingRecipient, CloudClient, RECIPIENT_STATUS


class CloudClientFactory(factory.MogoFactory):
    class Meta:
        model = CloudClient

    serial = "CXM_SERIAL"
    shared_key = "ThisIsTheKey"
    enabled = True


class MailingFactory(factory.MogoFactory):
    class Meta:
        model = Mailing

    mail_from = "sender@my-company.biz"
    sender_name = "Mailing Sender"
    header = "Subject: Great news!"
    body = "This is a mailing body."


class RecipientFactory(factory.MogoFactory):
    class Meta:
        model = MailingRecipient

    mailing = factory.SubFactory(MailingFactory)
    email = "firstname.lastname@domain.com"
    send_status = RECIPIENT_STATUS.READY
    next_try = datetime.utcnow()
    tracking_id = factory.LazyAttribute(lambda a: str(uuid.uuid4()))
    # report_ready = factory.LazyAttribute(lambda rcpt: rcpt.send_status in (RECIPIENT_STATUS.ERROR,
    #                                                                        RECIPIENT_STATUS.WARNING,
    #                                                                        RECIPIENT_STATUS.GENERAL_ERROR,
    #                                                                        RECIPIENT_STATUS.FINISHED) or None)
    report_ready = None
