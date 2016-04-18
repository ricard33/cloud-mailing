#!/usr/bin/env python
# Copyright 2015 Cedric RICARD
#
# This file is part of mf.
#
# mf is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mf is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with mf.  If not, see <http://www.gnu.org/licenses/>.
import os
import shutil
import subprocess
import sys
import time
from ConfigParser import RawConfigParser
from datetime import datetime

import pymongo
from bson import DBRef

__author__ = 'Cedric RICARD'

BASE_PATH = os.path.join(os.path.dirname(__file__), "root_dir")
SOURCES_PATH = os.path.join(os.path.dirname(__file__), '..', '..')
API_KEY = "CM_PERFS"

db_client = pymongo.MongoClient()


def _get_next_sequence(db, name):
    result = db.sequence.find_one_and_update({'_id': name}, {'$inc': {'seq': 1}},
                                             projection={'seq': True, '_id': False},
                                             upsert=True)
    return result and result['seq'] or 1


def initialize_cm(nb_satellites=3):
    if not os.path.exists(BASE_PATH):
        os.makedirs(BASE_PATH)

    make_database(nb_satellites)

    processes = []
    # master
    master_path = os.path.join(BASE_PATH, "master")
    processes.append(make_master(master_path))

    for i in range(nb_satellites):
        index = i + 1
        sat_path = os.path.join(BASE_PATH, "sat%d" % index)
        processes.append(make_satellite(sat_path, index))

    processes.append(make_fakesmtp())
    return processes


def terminate(processes):
    for p in processes:
        p.terminate()


def make_database(nb_satellites):
    db = db_client.perfs_cm_master

    for col in db.collection_names(include_system_collections=False):
        db.drop_collection(col)

    for i in range(nb_satellites):
        index = i + 1
        db.cloudclient.insert_one({
            '_id': index,
            'serial': 'SAT%d' % index,
            'shared_key': 'PERFS',
            'enabled': True
        })

    db.sequence.insert_one({'_id': 'cloud_client_id', 'seq': nb_satellites})

    add_mailing(db, 10000)


def add_mailing(db, nb_recipients):
    result = db.mailing.insert_one(
        {
            "_id": _get_next_sequence(db, 'mailing_id'),
            "status": "READY",
            "body": "X" * 10000 + "{{unsubscribe}}",
            "dont_close_if_empty": False,
            "sender_name": "Sender",
            "total_recipient": nb_recipients,
            "start_time": datetime.utcnow(),
            "testing": True,
            "header": "Content-Type: text/plain\nMIME-Version: 1.0\nFrom: Sender <news@cloud-mailing.net>\nDate: Mon, 01 Jun 2015 13:32:07 -0000\nSubject: Dear {{ firstname }}\n\n",
            "read_tracking": True,
            "backup_customized_emails": False,
            "mail_from": "news@cloud-mailing.net",
            "total_pending": nb_recipients,
            "total_sent": 0,
            "click_tracking": True,
            "domain_name": "cloud-mailing.net",
            "tracking_url": "http://cloud-mailing.net/t/",
            "total_softbounce": 0,
            "type": "REGULAR",
            "total_error": 0
        }
    )

    add_recipients2(db, result.inserted_id, nb_recipients)
    return result.inserted_id


def add_recipients(db, mailing_id, count):
    for i in range(count):
        db.mailingrecipient.insert_one({
            # "next_try": datetime.now(),
            # "in_progress": False,
            "mailing": DBRef("mailing", mailing_id),
            "contact": {
                "attachments": [
                ],
                "firstname": "John",
                "gender": "M",
                "email": "john.doe%d@cloud-mailing.net" % i,
                "lastname": "DOE",
                "id": i
            },
            "tracking_id": "e6992614-90ad-422b-8827-%d" % i,
            "send_status": "READY",
            "email": "john.doe%d@cloud-mailing.net" % i,
        })


def add_recipients2(db, mailing_id, count):
    db.mailingrecipient.insert_many([{
            "next_try": datetime.utcnow(),
            "in_progress": False,
            "mailing": DBRef("mailing", mailing_id),
            "contact": {
                "attachments": [
                ],
                "firstname": "John",
                "gender": "M",
                "email": "john.doe%d@cloud-mailing.net" % i,
                "lastname": "DOE",
                "id": i
            },
            "tracking_id": "e6992614-90ad-422b-8827-%d" % i,
            "send_status": "READY",
            "email": "john.doe%d@cloud-mailing.net" % i,
        } for i in range(count)])


def make_master(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    config_dir = os.path.join(path, 'config')
    os.makedirs(config_dir)
    config = RawConfigParser()
    config.add_section("ID")
    config.set("ID", "serial", "MASTER")
    config.add_section("CM_MASTER")
    config.set("CM_MASTER", "api_key", API_KEY)
    config.add_section("MASTER_DATABASE")
    config.set("MASTER_DATABASE", "name", "perfs_cm_master")
    with file(os.path.join(config_dir, 'cloud-mailing.ini'), 'wt') as fp:
        config.write(fp)

    shutil.copy(os.path.join(SOURCES_PATH, '..', 'config', 'logging-master.py'), config_dir)

    cm_script = os.path.join(SOURCES_PATH, "bin", "cm_master.py")
    p = subprocess.Popen([sys.executable, cm_script, '-p', '33700', '--api-port', '33701'], cwd=path)
    return p


def make_satellite(path, index):
    if os.path.exists(path):
        shutil.rmtree(path)
    config_dir = os.path.join(path, 'config')
    os.makedirs(config_dir)
    config = RawConfigParser()
    config.add_section("ID")
    config.set("ID", "serial", "SAT%d" % index)
    config.add_section("MAILING")
    config.set("MAILING", "shared_key", "PERFS")
    config.set("MAILING", "master_port", 33700)
    config.set("MAILING", "test_target_ip", "127.0.0.1")
    config.set("MAILING", "test_faked_dns", True)
    config.add_section("SATELLITE_DATABASE")
    config.set("SATELLITE_DATABASE", "name", "perfs_cm_satellite_%d" % index)
    with file(os.path.join(config_dir, 'cloud-mailing.ini'), 'wt') as fp:
        config.write(fp)

    cm_script = os.path.join(SOURCES_PATH, "bin", "cm_satellite.py")
    p = subprocess.Popen([sys.executable, cm_script], cwd=path, stdout=None, stderr=None)
    return p


def make_fakesmtp():
    cm_script = os.path.join(SOURCES_PATH, 'scripts', 'FakeSMTPD.py')
    p = subprocess.Popen([sys.executable, cm_script, '33625'])
    return p


def main():
    t0 = time.time()
    print "Preparing..."
    p_list = initialize_cm()

    print "Running..."
    try:
        print
        db = db_client.perfs_cm_master
        while not db.mailing.find_one({'status': 'FINISHED'}):
            ml = db.mailing.find_one({}, projection={'total_pending':True, 'total_recipient': True, '_id': False})
            if ml:
                print '%d / %d' % (ml['total_recipient'] - ml['total_pending'], ml['total_recipient'])
            # if time.time() - t0 > 30:
            #     break

            time.sleep(1)

    finally:
        terminate(p_list)

    print "All operations toke %.1f s" % (time.time() - t0)

if __name__ == '__main__':
    main()
