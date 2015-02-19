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

from random import random, randint
from datetime import datetime

__author__ = 'ricard'

import factory
from satellite.models import Mailing, MailingRecipient


class MailingFactory(factory.MogoFactory):
    FACTORY_FOR = Mailing

    _id = factory.Sequence(lambda n: n+1)
    tracking_url = 'http://localhost/ml/'

    # faked fields needed because used by create() function in models.Manager of Mailing
    header = "Subject: Great news!\n"
    body = 'This is a %%custom%% mailing.'
    body_downloaded = True


class RecipientFactory(factory.MogoFactory):
    FACTORY_FOR = MailingRecipient

    # id = factory.Sequence(lambda n: n+1)
    mailing = factory.SubFactory(MailingFactory)
    email = factory.LazyAttribute(lambda a: a.contact_data['email'])
    # recipient_id = factory.Sequence(lambda n: n+1)
    tracking_id = factory.LazyAttribute(lambda a: "SHA1_UID_%d" % randint(0, 1000))
    contact_data = {
        'email': 'firstname.lastname@domain.com',
        'custom': 'very simple',
    }
    domain_name = 'domain.com'
    mail_from = "sender@my-company.biz"
    sender_name = "Mailing Sender"
    next_try = factory.LazyAttribute(lambda x: datetime.utcnow())
