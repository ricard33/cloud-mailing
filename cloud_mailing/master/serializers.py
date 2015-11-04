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
import datetime
import json

from cloud_mailing.common import settings
from cloud_mailing.master import models
from ..common.rest_api_common import log

__author__ = 'Cedric RICARD'


class NotFound(Exception):
    pass


class Serializer(object):
    """
    Base class to serialize/unserialize objects to/from json or XMLRPC `struct` format
    """

    fields = []
    model_class = None

    def __init__(self, instance=None, data=None, fields_filter=None, many=False):
        self._instance = instance
        self._data = data
        self._fields_filter = fields_filter or []
        if fields_filter == 'total':
            self._fields_filter = ['.total']
        elif fields_filter == 'none':
            self._fields_filter = []
        elif fields_filter == 'default' or fields_filter is None:
            self._fields_filter = self.fields
        # elif not isinstance(fields_filter, (list, tuple)):
        #     raise ValueError("Bad value for 'fields_filter' (was '%s')" % fields_filter)
        else:
            self._fields_filter = fields_filter or []

        self._many = many

    @property
    def filtered_fields(self):
        return list(set(self.fields) & set(self._fields_filter))

    def make_filter(self, args):
        _filter = {}
        for field, value in args.items():
            if isinstance(value, (list, tuple)):
                _filter['satellite_group'] = {'$in': value}
            else:
                _filter['satellite_group'] = value
        return _filter

    def get(self, id):
        try:
            obj = self.model_class._get_collection().find({'_id': id}, fields=self.filtered_fields)[0]
            if obj:
                obj['id'] = obj.pop('_id')
                return obj
            raise NotFound
        except IndexError:
            raise NotFound

    def find(self, spec, skip=0, limit=settings.PAGE_SIZE):
        _filter = self.make_filter(spec)
        cursor = self.model_class._get_collection().find(_filter, fields=self.filtered_fields, skip=skip, limit=limit)
        items = []
        for obj in cursor:
            if '_id' in  obj:
                obj['id'] = obj.pop('_id')
            items.append(obj)
        response = {
            'items': items
        }
        if '.total' in self._fields_filter:
            response['total'] = cursor.count()
        return response


class MailingSerializer(Serializer):
    """
    Mailing serializer
    """
    model_class = models.Mailing
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

    def make_filter(self, args):
        mailings_filter = {}
        if args:
            available_filters = ('domain', 'id', 'status', 'owner_guid')
            for key in args.keys():
                if key not in available_filters:
                    log.error("Bad filter name '%s'. Available filters are: %s", key, ', '.join(available_filters))
                    raise ValueError("Bad filter name '%s'. Available filters are: %s" % (key, ', '.join(available_filters)))
            if 'domain' in args:
                domain = args['domain']
                if isinstance(domain, basestring):
                    mailings_filter['domain_name'] = domain
                else:
                    mailings_filter['domain_name'] = {'$in': domain}
            if 'id' in args:
                mailings_filter['_id'] = {'$in': args['id']}
            if 'status' in args:
                value = args['status']
                status_list = isinstance(value, (list, tuple)) and value or [value]
                for status in status_list:
                    available_status = models.relay_status
                    if status not in available_status:
                        log.error("Bad status '%s'. Available status are: %s",
                                  status, ', '.join(available_status))
                        raise ValueError("Bad status '%s'. Available status are: %s"
                                         % (status, ', '.join(available_status)))
                mailings_filter['status'] = {'$in': status_list}
            if 'owner_guid' in args:
                owners = args['owner_guid']
                if isinstance(owners, basestring):
                    mailings_filter['owner_guid'] = owners
                else:
                    mailings_filter['owner_guid'] = {'$in': owners}
            if 'satellite_group' in args:
                satellite_groups = args['satellite_group']
                if isinstance(satellite_groups, basestring):
                    mailings_filter['satellite_group'] = satellite_groups
                else:
                    mailings_filter['satellite_group'] = {'$in': satellite_groups}
        return mailings_filter
