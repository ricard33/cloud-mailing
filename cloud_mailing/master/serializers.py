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
import base64
import calendar
import json
import bson
import bson.json_util
from bson.py3compat import PY3, binary_type, string_types
import datetime

__author__ = 'Cedric RICARD'


def _json_convert(obj):
    """Recursive helper method that converts BSON types so they can be
    converted into json.
    """
    if hasattr(obj, 'iteritems') or hasattr(obj, 'items'):  # PY3 support
        return bson.SON(((k, _json_convert(v)) for k, v in obj.iteritems()))
    elif hasattr(obj, '__iter__') and not isinstance(obj, string_types):
        return list((_json_convert(v) for v in obj))
    try:
        return json_default(obj)
    except TypeError:
        return obj


def json_default(obj):
    # Modified version from bson package

    # We preserve key order when rendering SON, DBRef, etc. as JSON by
    # returning a SON for those types instead of a dict. This works with
    # the "json" standard library in Python 2.6+ and with simplejson
    # 2.1.0+ in Python 2.5+, because those libraries iterate the SON
    # using PyIter_Next. Python 2.4 must use simplejson 2.0.9 or older,
    # and those versions of simplejson use the lower-level PyDict_Next,
    # which bypasses SON's order-preserving iteration, so we lose key
    # order in Python 2.4.
    if isinstance(obj, bson.ObjectId):
        return str(obj)
    if isinstance(obj, bson.DBRef):
        return bson.json_util._json_convert(obj.as_doc())
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    # if isinstance(obj, bson.Timestamp):
    #     return bson.SON([("t", obj.time), ("i", obj.inc)])
    # if isinstance(obj, bson.Code):
    #     return bson.SON([('$code', str(obj)), ('$scope', obj.scope)])
    # if isinstance(obj, bson.Binary):
    #     return bson.SON([
    #         ('$binary', base64.b64encode(obj).decode()),
    #         ('$type', "%02x" % obj.subtype)])
    # if PY3 and isinstance(obj, binary_type):
    #     return bson.SON([
    #         ('$binary', base64.b64encode(obj).decode()),
    #         ('$type', "00")])
    if bson.has_uuid() and isinstance(obj, bson.uuid.UUID):
        return obj.hex
    raise TypeError("%r is not JSON serializable" % obj)


class Serializer(object):
    """
    Base class to serialize/unserialize objects to/from json or XMLRPC `struct` format
    """
    def to_json(self, obj):
        raise NotImplemented


class MailingSerializer(Serializer):
    """
    Mailing serialiser
    """
    fields = (
        '_id', 'domain_name', 'satellite_group', 'owner_guid',
        'mail_from', 'sender_name', 'status',
        'type', 'tracking_url',
        'header',
        'dont_close_if_empty',
        'submit_time', 'scheduled_start', 'scheduled_end', 'scheduled_duration',
        'start_time', 'end_time',
        'total_recipient', 'total_sent', 'total_pending', 'total_error',
        'total_softbounce',
        'read_tracking', 'click_tracking'
    )

    def to_json(self, obj):
        return json.dumps(obj, default=json_default)
