# Copyright 2015-2019 Cedric RICARD
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
import logging
from datetime import datetime

import pymongo

from ..common.db_common import create_index
from ..common.encoding import force_bytes

__author__ = 'Cedric RICARD'



def init_master_db(db):
    create_index(db.mailingrecipient, [('next_try', pymongo.ASCENDING)])
    create_index(db.mailinghourlystats, [('epoch_hour', pymongo.ASCENDING)])
    do_migrations(db)


def do_migrations(db):
    log = logging.getLogger('migrations')
    for migration in migrations:
        m = db['_migrations'].find_one({'name': migration.__name__})
        if not m:
            log.info("Running migration '%s'...", migration.__name__)
            migration(db)
            db['_migrations'].insert_one({'name': migration.__name__, 'applied': datetime.now()})


def _0001_remove_temp_queue(db):
    for recipient in db.mailingrecipient.find({'domain_name': None}):
        db.mailingrecipient.update_one({'_id': recipient['_id']},
                                       {'$set': {'domain_name': recipient['email'].split('@', 1)[1]}})

    if 'mailingtempqueue' in db.collection_names(include_system_collections=False):
        for item in db.mailingtempqueue.find():
            if 'client' in item:
                client = db.cloudclient.find_one({'_id': item['client'].id})
                db.mailingrecipient.update_one({'_id': item['recipient']['_id']},
                                               {'$set': {
                                                   'in_progress': True,
                                                   'date_delegated': item['date_delegated'],
                                                   'cloud_client': client['serial']
                                               }})

        db.drop_collection('mailingtempqueue')

    # reset all real orphans
    db.mailingrecipient.update_many({'in_progress': True, 'date_delegated': None},
                                    {'$set': {'in_progress': False}})


def _0002_set_subject(db):
    for mailing in db.mailing.find({'subject': None}, projection=('header',)):
        parser = email.parser.BytesHeaderParser(policy=email.policy.default)
        header = parser.parsebytes(force_bytes(mailing.get('header', b'')))
        subject = header.get("Subject")
        db.mailing.update_one({'_id': mailing['_id']}, {'$set': {'subject': subject}})

def _0003_convert_headers_and_bodies_to_bytes_object(db):
    for mailing in db.mailing.find({}, projection=('header', 'body')):
        header = force_bytes(mailing.get('header', b''))
        body = force_bytes(mailing.get('body', b''))
        db.mailing.update_one({'_id': mailing['_id']}, {'$set': {
            'header': header,
            'body': body,
        }})


migrations = [
    _0001_remove_temp_queue,
    _0002_set_subject,
    _0003_convert_headers_and_bodies_to_bytes_object,
]
