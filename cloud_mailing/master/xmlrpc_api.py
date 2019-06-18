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

# coding=utf-8
import base64
import email
import email.header
import email.mime
import email.mime.multipart
import email.mime.text
import inspect
import os
import re
import time
import xmlrpc.client
from io import StringIO
from datetime import datetime, timedelta

import pymongo
from bson import DBRef
from mogo.connection import Connection
from twisted.internet import defer
from twisted.internet.threads import deferToThread
from twisted.web import xmlrpc as tx_xmlrpc, resource, http, static

from ..common.encoding import force_text, force_bytes
from .api_common import compute_hourly_stats
from .api_common import log_cfg, log_security, log_api, pause_mailing, delete_mailing
from .api_common import set_mailing_properties, start_mailing
from .cloud_master import make_customized_file_name
from .mailing_manager import MailingManager
from .models import CloudClient, Mailing, relay_status, MAILING_STATUS, MailingRecipient, RECIPIENT_STATUS, \
    recipient_status
from .serializers import MailingSerializer
from ..common import settings
from ..common.config_file import ConfigFile
from ..common.db_common import get_db
from ..common.html_tools import strip_tags
from ..common.xml_api_common import withRequest, doc_signature, BasicHttpAuthXMLRPC, XMLRPCDocGenerator, doc_hide

Fault = xmlrpc.client.Fault
Binary = xmlrpc.client.Binary
Boolean = xmlrpc.client.Boolean
DateTime = xmlrpc.client.DateTime

email_re = re.compile(
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"  # dot-atom
    #r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*"' # quoted-string
    r')@(?:[A-Z0-9-]+\.)+[A-Z]{2,6}$', re.IGNORECASE)  # domain


#--------------------------------------------

def authenticate(rpc_server, username, password, remote_ip):
    config = ConfigFile()
    config.read(settings.CONFIG_FILE)

    key = config.get('CM_MASTER', 'API_KEY', '')
    if key and force_text(username) == 'admin' and force_text(password) == key:
        return username

    log_security.warn("XMLRPC authentication failed for user '%s' (%s)" % (username, remote_ip))
    raise Fault(http.UNAUTHORIZED, 'Authorization Failed!')

#--------------------------------------------


def ensure_no_null_values(d):
    null_values = [name for name, value in list(d.items()) if value is None]
    for name in null_values:
        del d[name]


class CloudMailingRpc(BasicHttpAuthXMLRPC, XMLRPCDocGenerator):
    """The CloudMailing XML-RPC server allows to directly manage CloudMailing Engine.

    You should be authenticated to be able to use it. Authentication is done by
    simple HTTP authentication method.
    A special API key should be used as password (login is fixed to 'admin').
    This key has to be generated from Web administration pages.
    """
    server_name = 'CloudMailing API'
    server_title = "CloudMailing XML-RPC Server Documentation"

    _authenticate_method = authenticate

    # -------------------------------------
    # Satellites management

    @withRequest
    @doc_signature('<i>integer</i> satellites_count')
    def xmlrpc_cloud_get_satellites_count(self, request):
        """
        Returns the total number of satellites
        :return: the number of satellites
        """
        log_api.debug("XMLRPC: get_satellites_count()")
        return CloudClient.count()

    @doc_signature('array')
    def xmlrpc_cloud_list_satellites(self):
        """
        List all cloud mailing satellites

        :return: Array of satellite descriptions. Each satellite is described by a properties dictionary.
        Fields are:
         - id: internal id of this satellite
         - serial: CM serial number of the satellite
         - enabled: can be used or not
         - paired: True if this satellite is online and has been accepted by CM Master
         - date_paired: Date when the paired status has been updated
         - shared_key:
         - domain_affinity:
        """
        log_api.debug("XMLRPC: cloud_list_satellites()")
        l = []
        for satellite in CloudClient._get_collection().find():
            d = dict(satellite)
            d['id'] = d.pop('_id')
            ensure_no_null_values(d)
            l.append(d)
        return l

    def check_satellite_properties(self, properties, valid_keys):
        for keys in properties:
            if keys not in valid_keys:
                raise Fault(http.NOT_ACCEPTABLE, "Invalid property named '%s' for satellite")
        if 'enabled' in properties:
            try:
                properties['enabled'] = bool(properties['enabled'])
            except Exception as ex:
                log_api.exception("Can't convert '%s' to boolean (property 'enabled')", properties['enabled'])
                raise Fault(http.NOT_ACCEPTABLE,
                            "Can't convert '%s' to boolean (property 'enabled')" % properties['enabled'])
        if 'domain_affinity' in properties:
            domain_affinity = properties['domain_affinity']
            if isinstance(domain_affinity, str):     # old format
                import ast

                try:
                    v = ast.literal_eval(properties['domain_affinity'])
                    if not isinstance(v, dict):
                        raise Fault(http.NOT_ACCEPTABLE, "'domain_affinity' property has to be a valid dictionary")
                except Exception:
                    log_api.exception("Badly formated string for 'domain_affinity' property.")
                    raise Fault(http.NOT_ACCEPTABLE,
                                "Badly formated string for 'domain_affinity' property. It has to be a valid Python dictionary.")
            elif not isinstance(domain_affinity, dict):
                raise Fault(http.NOT_ACCEPTABLE, "'domain_affinity' property has to be a valid dictionary")

    @doc_signature('<i>string</i> serial', '<i>struct</i> properties', 'id')
    def xmlrpc_cloud_add_satellite(self, serial, properties):
        """
        Add a new satellite.
         
         Satellite properties can be set by a struct with following valid keys:
         - enabled: can be used or not
         - shared_key:
         - domain_affinity:

        :param serial: Serial number of the Satellite to add
        :param properties: struct containing properties for this new satellite
        :return: Satellite ID
        """
        log_api.debug("XMLRPC: cloud_add_satellite(%s, %s)", serial, repr(properties))
        self.check_satellite_properties(properties, valid_keys=('enabled', 'shared_key', 'domain_affinity'))

        s = CloudClient.create(serial=serial, **properties)
        return s.id

    @doc_signature('<i>int</i> id', '<i>struct</i> properties', 'id')
    def xmlrpc_cloud_set_satellite_properties(self, id, properties):
        """
        Change some satellite's properties. Satellite properties can be set by a struct with following valid keys:
         - serial: serial number
         - enabled: can be used or not
         - shared_key:
         - domain_affinity:

        :param id: ID of the Satellite to change
        :param properties: struct containing properties to change for this satellite
        :return: id
        """
        log_api.debug("XMLRPC: cloud_set_satellite_properties(%s, %s)", id, repr(properties))
        self.check_satellite_properties(properties, valid_keys=('serial', 'enabled', 'shared_key', 'domain_affinity'))
        s = CloudClient.grab(id)
        if not s:
            raise Fault(http.NOT_FOUND, "Unknown satellite with id %d" % id)

        for name, value in list(properties.items()):
            setattr(s, name, value)
        s.save()
        return s.id

    @doc_signature('<i>int</i> id', '0')
    def xmlrpc_cloud_delete_satellite(self, id):
        """
        Delete a satellite.
        :param id: ID of the Satellite to delete
        :return: 0
        """
        log_api.debug("XMLRPC: cloud_delete_satellite(%s)", id)
        s = CloudClient.grab(id)
        if not s:
            raise Fault(http.NOT_FOUND, "Unknown satellite with id %d" % id)

        s.delete()
        return 0

    # -------------------------------------
    # Mailings management

    def _make_mailings_filter(self, filters):
        mailings_filter = {}
        if filters:
            if isinstance(filters, str):
                mailings_filter['domain_name'] = filters
            else:
                if not isinstance(filters, dict):
                    raise Fault(http.NOT_ACCEPTABLE, "Filters argument has to be a dictionary.")
                available_filters = ('domain', 'id', 'status', 'owner_guid')
                for key in list(filters.keys()):
                    if key not in available_filters:
                        raise Fault(http.NOT_ACCEPTABLE,
                                    "Bad filter name. Available filters are: %s" % ', '.join(available_filters))
                if 'domain' in filters:
                    mailings_filter['domain_name'] = {'$in': filters['domain']}
                if 'id' in filters:
                    mailings_filter['_id'] = {'$in': filters['id']}
                if 'status' in filters:
                    for status in filters['status']:
                        available_status = relay_status
                        if status not in available_status:
                            raise Fault(http.NOT_ACCEPTABLE, "Bad status '%s'. Available status are: %s"
                                        % (status, ', '.join(available_status)))
                    mailings_filter['status'] = {'$in': filters['status']}
                if 'owner_guid' in filters:
                    owners = filters['owner_guid']
                    if isinstance(owners, str):
                        mailings_filter['owner_guid'] = owners
                    else:
                        mailings_filter['owner_guid'] = {'$in': owners}
                if 'satellite_group' in filters:
                    satellite_groups = filters['satellite_group']
                    if isinstance(satellite_groups, str):
                        mailings_filter['satellite_group'] = satellite_groups
                    else:
                        mailings_filter['satellite_group'] = {'$in': satellite_groups}
        return mailings_filter

    @withRequest
    @doc_signature('<i>struct</i> filter (optional)', '<i>integer</i> mailings_count')
    def xmlrpc_get_mailings_count(self, request, filters=None):
        """
        Returns the number of mailings corresponding to the specified filter
        :param filters: if present, should be a struct containing filters.
                        Available filters are:
                            - 'domain': list of mailing sender domain name
                            - 'id': will only returns mailing which id are in this list.
                            - 'status': will only returns mailing which status are in this list.
                            - 'owner_guid': list of owner GUID to use as filter
                            - 'satellite_group': list of groups to use as filter
        :return: the number of mailings for the specified filter
        """
        log_api.debug("XMLRPC: get_mailings_count(%s)", filters or {})
        mailings_filter = self._make_mailings_filter(filters)
        return Mailing._get_collection().find(mailings_filter).count()

    @withRequest
    @doc_signature('<i>struct</i> filter (optional)', 'array')
    def xmlrpc_list_mailings(self, request, filters=None):
        """
        List all mailings for the logged user
        :param filters: if present, should be a struct containing filters.
                        Available filters are:
                            - 'domain': list of mailing sender domain name
                            - 'id': will only returns mailing which id are in this list.
                            - 'status': will only returns mailing which status are in this list.
                            - 'owner_guid': list of owner GUID to use as filter
                            - 'satellite_group': list of groups to use as filter
        :return: Array of mailings descriptions. Each mailing is described by a properties dictionary.
        Fields are:
         - id: internal id of this mailing
         - domain_name: Related domain name = mailing sender identity
         - satellite_group: group name for satellites allowed to handle this mailing
         - mail_from: email address displayed in sender field
         - sender_name: Full name displayed in sender field
         - subject: Mailing subject
         - status: Mailing status
         - type: the Mailing Type - one of "REGULAR", "OPENED"
         - tracking_url: base url for tracking links
         - dkim: dkim settings (dictionary). Fields are enabled (Default=True), selector, domain, privkey
         - submit_time: Date and time when mailing was submitted
         - scheduled_start: Date and time when mailing should start
         - scheduled_end: Date and time when mailing should stop
         - scheduled_duration: Original mailing duration (in minutes)
         - start_time: Date and time when mailing really started
         - end_time: Date and time when mailing should stop
         - total_recipient: Total recipients count
         - total_sent: Number of recipients that were successfully handled
         - total_pending: Number of recipients not yet handled (including soft bounces)
         - total_error: Number of hard bounces
         - total_softbounce: Number of soft bounces
         - read_tracking: True if tracking for reads is activated
         - click_tracking: True if tracking for clicks is activated
         - url_encoding: <encoding>. If present, all links in mailing content will be encoded using the specified encoding.
        """
        log_api.debug("XMLRPC: list_mailings(%s)", filters or {})

        mailings_filter = self._make_mailings_filter(filters)

        l = []

        for mailing in Mailing._get_collection().find(mailings_filter, projection=MailingSerializer.fields,
                                                      sort=[('_id', pymongo.ASCENDING), ]):
            mailing['id'] = mailing.pop('_id')
            ensure_no_null_values(mailing)
            #print mailing
            l.append(mailing)

        return l

    @withRequest
    @doc_signature('<i>string</i> mail_from', '<i>string</i> sender_name', '<i>string</i> subject',
                   '<i>string</i> html_content', '<i>string</i> plain_content', '<i>string</i> charset', 'mailing_id')
    def xmlrpc_create_mailing(self, request, mail_from, sender_name, subject, html_content, plain_content=None,
                               charset='utf-8'):
        """
        Creates a new mailing.

        :param mail_from: Sender email address
        :param sender_name: Sender name (used to compose the From header : "Sender Name <sender-email@domain.tdl>")
        :param subject: Mailing subject
        :param html_content: HTML message
        :param plain_content: Plain text message
        :param charset: Encoding of both HTML and plain text messages
        :return: Returns the mailing internal id
        """
        log_api.debug("XMLRPC: create_mailing(%s, %s, %s, ...)", mail_from, sender_name, subject)
        msg = email.message.EmailMessage()

        if not plain_content:
            # TODO MAILING improve this too simple conversion...
            plain_content = strip_tags(html_content)

        msg.set_content(force_text(plain_content, encoding=charset))
        msg.add_alternative(force_text(html_content, encoding=charset), subtype="html")

        msg['Subject'] = force_text(subject, encoding=charset)
        msg['Date'] = email.utils.formatdate()
        return self._create_mailing(msg, mail_from=mail_from, sender_name=sender_name)

    @withRequest
    @doc_signature('<i>string</i> rfc822_string', 'mailing_id')
    def xmlrpc_create_mailing_ext(self, request, rfc822_string):
        """Create a new mailing using the rfc822_string parameter as email content.

        The well named parameter 'rfc822_string' is an RFC822 compliant email string encoded in base64 to avoid any
         encoding problem.
        """
        import email.parser
        import email.policy
        log_api.debug("XMLRPC: create_mailing_ext(...)")
        try:
            if isinstance(rfc822_string, Binary):
                rfc822_string = rfc822_string.data
            m_parser = email.parser.BytesFeedParser(policy=email.policy.default)
            m_parser.feed(base64.b64decode(force_bytes(rfc822_string)))
            message = m_parser.close()
            return self._create_mailing(message)
        except Fault as ex:
            request.setResponseCode(ex.faultCode)
            raise

    def _create_mailing(self, msg, mail_from=None, sender_name=None):
        assert (isinstance(msg, email.message.EmailMessage))

        mailing = Mailing.create_from_message(msg, mail_from=mail_from, sender_name=sender_name,
                                                               scheduled_start=None, scheduled_duration=None)
        return mailing.id

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '<i>structure</i> properties', '0')
    def xmlrpc_set_mailing_properties(self, request, mailing_id, properties):
        """
            Set one or several properties of a mailing. Only mailings in 'FILLING_RECIPIENTS' status
            can change their properties.
            Properties are passed as a dictionary with property names as keys, and properties values as values.
            Available properties are:
                - type: the Mailing Type to create - one of "REGULAR", "OPENED"
                - satellite_group
                - mail_from
                - sender_name
                - shown_name (DEPRECATED: use 'sender_name' instead)
                - tracking_url: base url for tracking links
                - backup_customized_emails: If True, customized emails will be included in recipients reports
                - owner_guid: free string (max 50 characters) that can be used to identify (and filter) mailings we own.
                - scheduled_start: datetime in isoformat, or empty string to remove its value
                - scheduled_end: datetime in isoformat. Imperative mailing ending. Mailing life can be reduced by
                                 scheduled_duration, but not extended over this date. An empty string allows to reset
                                 this value.
                - scheduled_duration: mailing max duration in minutes. Set to 0 to remove this limitation.
                - dont_close_if_empty: flag used by REGULAR mailing to be able to start the mailing before adding
                                       recipients. This allows to send first recipients as soon as they have been added
                                       without the need to wait for all while ensuring the mailing is not closed
                                       automatically due to lake of recipients.
                - subject: a new subject, encoded with 'charset'
                - html_content: a new html content, encoded with 'charset'.
                - plain_content: a new plain text content, encoded with 'charset'.
                - charset: mandatory field if 'subject', 'html_content' or 'plain_content' are present. Specifies the
                           encoding of these fields.
                - header
                - body
                - read_tracking: set True to active tracking for reads (default: True)
                - click_tracking: set True to active tracking for clicks (default: False)
                - dkim: dkim settings (dictionary). Fields are enabled (Default=True), selector, domain, privkey
                - url_encoding: <encoding>. If present, all links in mailing content will be encoded using the specified encoding.
                        Only supported value is: base64.
        """
        log_api.debug("XMLRPC: set_mailing_properties(%s, %s)", mailing_id, repr(properties))
        try:
            set_mailing_properties(mailing_id, properties)
        except Fault as ex:
            request.setResponseCode(ex.faultCode)
            raise
        return 0

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '')
    def xmlrpc_delete_mailing(self, request, mailing_id):
        """Delete a mailing.
        """
        log_api.debug("XMLRPC: delete_mailing(%s)", mailing_id)
        try:
            delete_mailing(mailing_id)
        except Fault as ex:
            request.setResponseCode(ex.faultCode)
            raise

        return 0

    @withRequest
    @doc_signature('<i>string</i> domain_name', 'removed_count')
    def xmlrpc_delete_all_mailings_for_domain(self, request, domain_name):
        """Delete all mailings for a given domain name.
        """
        log_api.debug("XMLRPC: delete_all_mailings_for_domain(%s)", domain_name)
        mailings = Mailing.search(domain_name=domain_name)
        c = 0
        for mailing in mailings:
            manager = MailingManager.getInstance()
            manager.close_mailing(mailing.id)
            mailing.full_remove()
            c += 1
        return c

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '<i>date_time</i> when', '<i>string</i> mailing_status')
    def xmlrpc_start_mailing(self, request, mailing_id, when=None):
        """
        Activate a mailing: its recipients will be available to be handled by mailing queues.
        :return: new mailing status
        """
        log_api.debug("XMLRPC: start_mailing(%s, %s)", mailing_id, when)
        try:
            mailing = start_mailing(mailing_id)
        except Fault as ex:
            request.setResponseCode(ex.faultCode)
            raise
        return mailing.status

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '<i>string</i> mailing_status')
    def xmlrpc_pause_mailing(self, request, mailing_id):
        """
        Temporary stop a mailing (mailing is paused).
        :return: new mailing status
        """
        log_api.debug("XMLRPC: pause_mailing(%s)", mailing_id)
        try:
            mailing = pause_mailing(mailing_id)
        except Fault as ex:
            request.setResponseCode(ex.faultCode)
            raise
        return mailing.status

    # -------------------------------------
    # Recipients management

    def _make_recipients_filter(self, filters, for_reports=False):
        filters = filters or {}
        recipients_filter = {}
        only_status = filters.get('status')
        if only_status:
            if not isinstance(only_status, (list, tuple)):
                raise Fault(http.NOT_ACCEPTABLE, "Parameter 'only_status' has to be an array of strings.")
            for value in only_status:
                if value not in recipient_status:
                    raise Fault(http.NOT_ACCEPTABLE,
                                "Parameter 'only_status' has invalid status. Valid values are (%s)"
                                % ', '.join(recipient_status))
            recipients_filter['send_status'] = {'$in': only_status}

        if for_reports:
            recipients_filter['$or'] = [{'report_ready': True}, {'report_ready': None}]

        def apply_filter(filters, name, filter_type, type_description, qs_filter, qs_op, qs_mapper=lambda x: x):
            filter = filters.get(name)
            if filter is not None:
                if not isinstance(filter, filter_type):
                    raise Fault(http.NOT_ACCEPTABLE, "Filter '%s' has to be %s." % (name, type_description))
                return {qs_filter: {qs_op: qs_mapper(filter)}}
            return {}

        def apply_mailing_filter(filters, name, filter_type, type_description, field, op, qs_mapper=lambda x: x):
            filter = filters.get(name)
            if filter is not None:
                if not isinstance(filter, filter_type):
                    raise Fault(http.NOT_ACCEPTABLE, "Filter '%s' has to be %s." % (name, type_description))
                ids = [x['_id'] for x in Mailing._get_collection().find({field: {op: qs_mapper(filter)}}, projection=[])]
                filters.setdefault('mailings', []).extend(ids)

        apply_mailing_filter(filters, 'owners', (list, tuple), 'an array of strings', 'owner_guid', '$in')
        apply_mailing_filter(filters, 'sender_domains', (list, tuple), 'an array of strings', 'domain_name', '$in')
        recipients_filter.update(
            apply_filter(filters, 'mailings', (list, tuple), 'an array of mailing_ids', 'mailing.$id', '$in', qs_mapper=lambda x: list(map(int, x))))
        return recipients_filter

    def _update_pending_recipients(self, result):
        recipients, mailing_id, total_added = result
        Mailing.update({'_id': mailing_id}, {'$inc': {
            'total_recipient': total_added,
            'total_pending': total_added
        }})
        return recipients

    @withRequest
    @doc_signature('<i>struct</i> filter (optional)', '<i>integer</i> recipients_count')
    def xmlrpc_get_recipients_count(self, request, filters=None):
        """
        Returns the number of recipients corresponding to the specified filter
        :param filters: allows to filter results. Filter is a structure containing following fields (all optional):
            - status: filter by recipient status. If specified, this parameter should contains a list of acceptable
                      statuses.
            - owners: list of 'owner_guid'. Only recipients contained in mailing owned by these uids are returned
            - mailings: list of mailing ids
            - sender_domains: list of domain names. Only recipients contained in mailings whose sender are from these
                      domains are selected.
        :return: the number of mailings for the specified filter
        """
        log_api.debug("XMLRPC: get_recipients_count(%s)", filters or {})
        recipients_filter = filters and self._make_recipients_filter(filters) or {}
        return MailingRecipient._get_collection().find(recipients_filter).count()

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '<i>array</i> recipients_dict', '<i>array</i> status')
    def xmlrpc_add_recipients(self, request, mailing_id, recipients):
        """Adds multiple recipients to a mailing.

        :param mailing_id: Target mailing id
        :param recipients: Array of recipient description.
            Recipients are passed as an array of struct, each struct containing fields for one recipient.
            Predefined fields are:
              - email     -- MANDATORY. Without it, recipient can't be added
              - tracking_id -- if set, will be used as tracking or unsubscribe id instead of an auto-generated one. It
                  will also be used as recipient_id. So it absolutely has to be unique! If not defined, CloudMailing
                  will generate it. Must be a string with less than 50 characters.
              - attachments -- optional: Array of struct, each one describes an attachment

            Attachment struct contains following fields:
              - filename : (optional)attachment file name
              - content-type : attachment mime type
              - content-id: (optional, not yet supported) content id. If present, attachment will be added in a multipart/related
                            and without 'disposition: attachment' header.
              - charset: (only for text/*) charset of the encoded text
              - data: (*)base64 encoded attachment data
              - url: (*)URL where attachment file can be downloaded (in its original format, i.e. not base64 encoded)
                     (Not yet supported)

            (*) 'data' and 'url' fields are mutually exclusive. But at least one of them has to be present.

            WARNING: You can't add more than 1000 recipients per call. If you need to add more, make multiple calls.

        :return: A list of structures, one for each recipient in input.
            The structure contains following fields:
                - email: recipient email. Can be missing if recipient doesn't contains email field.
                - id: recipient internal id (= tracking_id). Only present if recipient has been successfully added.
                        DEPRECATED: Use 'tracking_id' instead.
                - tracking_id: corresponding tracking_id. Only present if recipient has been successfully added.
                - error: in case of failure, this field is added and contains the failure reason.
            'id' (or 'tracking_id') and 'error' are mutually exclusive. In case of success, only 'id' is present; in case of failure,
            only 'error' can be found.
            Results are kept in same order than inputs.
        """
        log_api.debug("XMLRPC: add_recipients(%d, %s%s)", mailing_id, repr(recipients[:3])[:-1],
                      len(recipients) > 3 and "... count=%d]" % len(recipients) or "]")
        # return deferToThread(self._add_recipients, request, mailing_id, recipients)\
        #     .addCallback(self._update_pending_recipients)
        return self._add_recipients(request, mailing_id, recipients) \
            .addCallback(self._update_pending_recipients)

    @withRequest
    @doc_signature('<i>int</i> mailing_id', '<i>array</i> recipients_dict', '<i>array</i> status')
    def xmlrpc_send_test(self, request, mailing_id, recipients):
        """Send a test email to multiple recipients for a mailing.

        Test email is sent as soon as possible, bypassing any other 'standard recipients'. Test emails can be sent
        even if mailing is not started.
        Parameters and return value are exactly the same as add_recipients() function.
        """
        log_api.debug("XMLRPC: send_test(%d, %s%s)", mailing_id, repr(recipients[:3])[:-1],
                      len(recipients) > 3 and "... count=%d]" % len(recipients) or "]")

        @defer.inlineCallbacks
        def _send_test(request, mailing_id, recipients):
            rcpts = yield self._add_recipients(request, mailing_id, recipients, primary=True)

            # TODO Maybe we should push new recipients immediately to satellites
            defer.returnValue(rcpts)

        # return deferToThread(_send_test, request, mailing_id, recipients)\
        #     .addCallback(self._update_pending_recipients)
        return _send_test(request, mailing_id, recipients) \
            .addCallback(self._update_pending_recipients)

    @defer.inlineCallbacks
    def _add_recipients(self, request, mailing_id, recipients, primary=False):
        t0 = time.time()
        if len(recipients) > 1000:
            log_api.error('Too many recipients! Length = %d exceeded maximum write batch size of 1000', len(recipients))
            request.setResponseCode(http.BAD_REQUEST)
            raise Fault(http.BAD_REQUEST, 'Too many recipients! Exceeded maximum write batch size of 1000')
        db = get_db()
        mailing = yield db.mailing.find_one({'_id': mailing_id}, fields=['status', 'mail_from', 'sender_name'])
        if not mailing:
            log_api.warn('Mailing [%d] not found', mailing_id)
            request.setResponseCode(http.NOT_FOUND)
            raise Fault(http.NOT_FOUND, 'Mailing not found!')
        if mailing['status'] == MAILING_STATUS.FINISHED:
            log_api.warning("Trying to add recipients into finished mailing. Refused!")
            raise Fault(http.BAD_REQUEST, "Mailing finished!")

        result = []
        total_added = 0
        all_recipients = []
        for index, fields in enumerate(recipients):
            t1 = time.time()
            c = {}
            if 'email' not in fields:
                c['error'] = "'email' field is mandatory but not found in recipient [%d]" % index
                log_api.error(c['error'])
                result.append(c)
                continue
            c['email'] = fields['email'].lower()
            m = email_re.search(fields['email'])
            if not m:
                c['error'] = "'email' field is not a regular email address: '%s'" % fields['email']
                log_api.error(c['error'])
                result.append(c)
                continue
            errors = []
            for a in fields.get('attachments', []):
                if 'content-id' in a:
                    errors.append("'content-id' not yet supported for attachments!")
                    log_api.error(c['error'])
                if 'url' in a:
                    c['error'] = "'url' not yet supported for attachments!"
                    log_api.error(c['error'])
                if a['content-type'].split('/')[0] == 'text':
                    if not 'charset' in a:
                        c['error'] = "Field 'charset' is mandatory for 'text/*' attachments!"
                        log_api.error(c['error'])

            if errors:
                c['error'] = '\n'.join(errors)
                result.append(c)
                continue
            if 'tracking_id' not in fields:
                import uuid
                tracking_id = str(uuid.uuid4())
            else:
                tracking_id = fields.pop('tracking_id')
            all_recipients.append({
                'mailing': DBRef('mailing', mailing['_id']),
                'tracking_id': tracking_id,
                'contact': fields,
                'email': fields['email'],
                'domain_name': fields['email'].split('@', 1)[1],
                'send_status': RECIPIENT_STATUS.READY,
                'next_try': primary and datetime(2000, 1, 1) or datetime.utcnow(),
                'primary': primary
            })
            total_added += 1

            c['id'] = tracking_id
            c['tracking_id'] = tracking_id
            result.append(c)
            log_api.debug("add_recipients() recipient %s added to mailing [%d] in %.1f seconds",
                          fields['email'], mailing_id, time.time() - t1)
        insert_result = yield db.mailingrecipient.insert_many(all_recipients, ordered=False)

        total_added = len(insert_result.inserted_ids)
        if total_added != len(all_recipients):
            log_api.error("add_recipients() Not all recipients have been added! Only %d over %d.", total_added, len(all_recipients))

        log_api.debug("add_recipients() %d recipients added in %.1f seconds", total_added, time.time() - t0)
        defer.returnValue((result, mailing['_id'], total_added))

    @withRequest
    @doc_signature('<i>array</i> recipient_ids', '<i>array</i> recipients status')
    def xmlrpc_get_recipients_status(self, request, recipient_ids, options=None):
        """
        Returns the status of a list of recipients.
        :param recipient_ids: Array of recipient ids
        :param options: a struct containing options for retrieved data. Available keys are:
            - with_contact_data: by default, contact data are send back with report because there are useless. But if
                    this option is set to True, contact data are returned.
            - with_customized_content: if the customized email has been kept (mailing option), this flag allow to
                    retrieve this content along with the recipient report
            - delete_customized_content: if the customizer content exists and has been retrieved, setting this flag to
                    True ask CloudMailing to delete it and free disk space.
        :return: Returns an array of recipient status.
            A status is a structure containing following keys:
                - id: recipient id
                - email: recipient email
                - status: global status ('READY', 'FINISHED', 'TIMEOUT', 'GENERAL_ERROR', 'ERROR', 'WARNING', 'IN PROGRESS')
                - reply_code: the error code returned by remote SMTP server
                - reply_enhanced_code: The enhanced error code, if remote SMTP server supports ESMTP protocol
                - reply_text: The full message returned by remote SMTP server.
                - smtp_log: The full SMTP transaction log
                - modified: last modification date
                - first_try: The first time the recipient has been tried
                - next_try: When we will try to send email again (if case of soft bound)
                - try_count: Tentatives count
                - in_progress: This recipient is currently handled by a Satellite
                - cloud_client: Sender Satellite which did (or is doing) the sent
                - contact: OPTIONAL: contact data given at recipient creation. Used for email customization
                - customized_content: OPTIONAL: if mailing is configured to backup customized emails, this field contains
                    the email in RFC822 format. Warning: due to high volume data, email content can be retrieved only
                    once. Its content is destroyed just after this call.
        """
        log_api.debug("XMLRPC: get_recipients_status(%s, options=%s)", repr(recipient_ids), repr(options))
        options = options or {}
        def _get_recipients_status(recipient_ids):
            all_status = []
            for recipient in MailingRecipient.find({'tracking_id': {'$in': recipient_ids}}):
                status = self.make_recipient_status_structure(recipient, options.get('with_contact_data'))
                if options.get('with_customized_content'):
                    status['customized_content'] = self.get_customized_content(recipient.mailing.id, recipient.id,
                                                                               options.get('delete_customized_content'))
                all_status.append(status)
            return all_status
        return deferToThread(_get_recipients_status, recipient_ids)

    def make_recipient_status_structure(self, recipient, with_contact_data=False):
        status = recipient.copy()
        status.pop('_id')
        status['id'] = status.pop('tracking_id')
        status.pop('mailing', None)
        if not with_contact_data:
            status.pop('contact', None)
        status.pop('send_status', None)
        status['status'] = recipient.send_status
        ensure_no_null_values(status)
        return status

    def get_customized_content(self, mailing_id, recipient_id, delete_customized_content=False):
        data = None
        file_name = make_customized_file_name(mailing_id, recipient_id)
        fullpath = os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, file_name)
        if os.path.exists(fullpath):
            with open(fullpath, 'rt') as f:
                data = f.read()
                f.close()
            if delete_customized_content:
                log_api.debug("Removing customized content: %s", fullpath)
                os.remove(fullpath)
        return data

    @withRequest
    @doc_signature('<i>string</i> cursor', '<i>string array</i> filters',
                   '<i>int</i> max_results=1000',
                   '<i>struct</i> recipients status')
    def xmlrpc_get_recipients_status_updated_since(self, request, cursor=None, filters=None, max_results=1000, options=None):
        """
        Returns the status of all recipients that changed since the last call. The function will limit to 1000
        results and returns the cursor allowing to get next entries on the next call. 'cursor' is an obscure string and
        should not be interpreted nor manually generated. It change after every call, so it have to be stored by
        client.

        :param cursor: Obscure string allowing to get next results.
        :param filters: allows to filter results. Filter is a structure containing following fields (all optional):
            - status: filter by recipient status. If specified, this parameter should contains a list of acceptable
                      statuses. By default, the filter contains all statuses except READY.
            - owners: list of 'owner_guid'. Only recipients contained in mailing owned by these uids are returned
            - mailings: list of mailing ids
            - sender_domains: list of domain names. Only recipients contained in mailings whose sender are from these
                      domains are selected.
        :param max_results: How many results do you want ? There is a default and hard limit to 1000 results.
        :param options: a struct containing options for retrieved data. Available keys are:
            - with_contact_data: by default, contact data are send back with report because there are useless. But if
                    this option is set to True, contact data are returned.
            - with_customized_content: if the customized email has been kept (mailing option), this flag allow to
                    retrieve this content along with the recipient report
            - delete_customized_content: if the customizer content exists and has been retrieved, setting this flag to
                    True ask CloudMailing to delete it and free disk space.
        :return: Returns a struct with following fields:
            - cursor: the cursor string
            - recipients: an array of recipient status.
            A status is a structure containing following keys:
                - id: recipient id
                - email: recipient email
                - status: global status ('READY', 'FINISHED', 'TIMEOUT', 'GENERAL_ERROR', 'ERROR', 'WARNING', 'IN PROGRESS')
                - reply_code: the error code returned by remote SMTP server
                - reply_enhanced_code: The enhanced error code, if remote SMTP server supports ESMTP protocol
                - reply_text: The full message returned by remote SMTP server.
                - smtp_log: the full log of the SMTP transaction
                - modified: last modification date
                - first_try: The first time the recipient has been tried
                - next_try: When we will try to send email again (if case of soft bound)
                - try_count: Tentatives count
                - in_progress: This recipient is currently handled by a Satellite
                - cloud_client: Sender Satellite which did (or is doing) the sent
                - contact: OPTIONAL: contact data given at recipient creation. Used for email customization
                - customized_content: OPTIONAL: if mailing is configured to backup customized emails, this field contains
                    the email in RFC822 format. Warning: due to high volume data, email content can be retrieved only
                    once. Its content is destroyed just after this call.
        """
        log_api.debug("XMLRPC: get_recipients_status_updated_since(%s, %s, %d, %s)", cursor, repr(filters), max_results, options)
        options = options or {}

        def _count_recipient_for_a_date(from_date, recipients_filter):
            _filter = recipients_filter.copy()
            _filter['modified'] = from_date
            new_count = MailingRecipient.find(_filter).count()
            return new_count

        def _get_recipients_status(cursor, filters, max_results):
            if cursor:
                try:
                    from_date, count, offset = cursor.split(';')
                    from_date = datetime.strptime(from_date, "%Y-%m-%dT%H:%M:%S.%f")
                    count = int(count)
                    offset = int(offset)
                except Exception as ex:
                    log_api.error("Bad cursor format. Can't extract values: %s", ex)
                    from_date = None
                    offset = count = 0
            else:
                from_date = None
                offset = count = 0

            if from_date and not isinstance(from_date, datetime):
                raise Fault(http.NOT_ACCEPTABLE, "Parameter 'from_date' has to be a dateTime.iso8601.")
            if not filters:
                filters = {}
            filters.setdefault('status',
                               [RECIPIENT_STATUS.ERROR, RECIPIENT_STATUS.FINISHED, RECIPIENT_STATUS.GENERAL_ERROR,
                                RECIPIENT_STATUS.IN_PROGRESS, RECIPIENT_STATUS.TIMEOUT, RECIPIENT_STATUS.WARNING])
            recipients_filter = self._make_recipients_filter(filters, for_reports=True)
            if from_date:
                recipients_filter['modified'] = {'$gte': from_date}

            if max_results > 1000:
                max_results = 1000
            elif max_results < 1:
                max_results = 1

            if count:
                new_count = _count_recipient_for_a_date(from_date, recipients_filter)
                if count != new_count:
                    offset = 0
                    count = new_count
            all_status = []
            for recipient in MailingRecipient.find(recipients_filter).sort('modified').skip(offset).limit(max_results):
                status = self.make_recipient_status_structure(recipient, options.get('with_contact_data'))
                # print status
                if options.get('with_customized_content'):
                    status['customized_content'] = self.get_customized_content(recipient.mailing.id, recipient.id,
                                                                               options.get('delete_customized_content'))

                all_status.append(status)
            if all_status:
                min_date = all_status[0]['modified']
                max_date = all_status[-1]['modified']
                if min_date != max_date:
                    c = 0
                    for status in reversed(all_status):
                        if status['modified'] != max_date:
                            break
                        c += 1
                    offset = c
                    count = _count_recipient_for_a_date(max_date, recipients_filter)
                elif max_date == from_date:
                    offset += len(all_status)
                else:
                    offset = len(all_status)
                    count = _count_recipient_for_a_date(max_date, recipients_filter)

            else:
                min_date = max_date = datetime.utcnow()
                offset = count = 0
            r = {
                'cursor': ';'.join([max_date.strftime("%Y-%m-%dT%H:%M:%S.%f"), str(count), str(offset)]),
                'recipients': all_status,
            }

            log_api.debug("XMLRPC: get_recipients_status_updated_since returned %d results (count=%d, offset=%d)", len(all_status), count, offset)
            # print r
            return r

        return deferToThread(_get_recipients_status, cursor, filters, max_results)

    @withRequest
    @doc_signature('<i>array</i> recipient_ids', '')
    def xmlrpc_reset_recipients_status(self, request, recipient_ids):
        """
        Reset the status of a list of recipients. This allows recipients to be include again in mailing.
        :param recipient_ids: Array of recipient ids
        """
        log_api.debug("XMLRPC: reset_recipients_status(%s)", repr(recipient_ids))
        def _reset_recipients_status(recipient_ids):
            MailingRecipient.update({'tracking_id': {'$in': recipient_ids}},
                                    {'$set': {'send_status': RECIPIENT_STATUS.READY}},
                                    multi=True)
            return 0
        return deferToThread(_reset_recipients_status, recipient_ids)

    # -------------------------------------
    # Statistics functions

    @withRequest
    @doc_signature('<i>struct</i> filter',
                   '<i>struct</i> statistics')
    def xmlrpc_get_hourly_statistics(self, request, filters):
        """
        Returns hourly statistics for an time interval. The returned array contains one entry per hour into the
        interval, with a maximum of 1000 results.
        :param filters: allows to filter results. Filter is a structure containing following fields (some are optional):
            - from_date: Only returns statistics since this date (iso8601) - Mandatory
            - to_date: Only returns statistics up to this date (iso8601) - Optional
            - senders: array of satellite serial numbers - Optional
        :return: Returns an array of structs containing following fields:
                - sender: satellite serial number
                - date:
                - epoch_hour:
                - sent: number of emails successfully sent during this hour
                - failed: number of emails successfully sent during this hour
                - tries: number of emails successfully sent during this hour
        """
        log_api.debug("XMLRPC: get_hourly_statistics(%s)", filters)
        from_date = filters.get('from_date')
        if not isinstance(from_date, datetime):
            log_api.error("Bad format for 'from_date' parameter.")
            raise Fault(http.NOT_ACCEPTABLE, "Filter 'from_date' has to be a dateTime.iso8601.")
        to_date = filters.get('to_date')
        if to_date and not isinstance(to_date, datetime):
            log_api.error("Bad format for 'to_date' parameter.")
            raise Fault(http.NOT_ACCEPTABLE, "Filter 'to_date' has to be a dateTime.iso8601.")
        senders = filters.get('senders')

        filter = {}
        filter.setdefault('date', {})['$gte'] = from_date
        if not to_date:
            to_date = from_date + timedelta(hours=999)
        filter.setdefault('date', {})['$lte'] = to_date
        if senders:
            filter = {'sender': {'$in': senders}}

        return compute_hourly_stats(filter, from_date, to_date)

    # -------------------------------------
    # Deprecated functions

    @doc_hide
    def xmlrpc_update_statistics(self):
        """
        DEPRECATED as useless. Statistics are in real time now.
        Ask CloudMailing to update its mailings statistics now. Warning, this is a synchronous call
        and this operation may take some time.
        :return: 0
        """
        log_api.debug("XMLRPC: update_statistics()")
        log_api.warn("XMLRPC: update_statistics() is deprecated because it became useless since statistics are updated in real time.")
        #from cm_master.cron import UpdateMailingsStats
        #
        #UpdateMailingsStats.update_stats()
        return 0

    # -------------------------------------
    # Utility functions (not public)

    @doc_hide
    def xmlrpc_mailing_manager_force_check(self):
        """Force the MailingManager to immediately check for its queue."""
        log_api.debug("XMLRPC: mailing_manager_force_check() DEPRECATED as USELESS: no more temp queue")

        return 0

    @doc_hide
    def xmlrpc_force_purge_empty_mailings(self):
        """Force the MailingManager to immediately purge any empty or finished mailings."""
        log_api.debug("XMLRPC: force_purge_empty_mailings()")
        manager = MailingManager.getInstance()
        assert(isinstance(manager, MailingManager))
        return manager.update_status_for_finished_mailings()\
            .addCallback(lambda x: 0)  # force to return a '0' instead of 'None'

    @withRequest
    @doc_hide
    def xmlrpc_activate_unittest_mode(self, request, activated):
        from . import cloud_master
        if cloud_master.MailingPortal.instance:
            mailing_master = cloud_master.MailingPortal.instance.realm
            mailing_master.activate_unittest_mode(activated)
        else:
            log_cfg.error("Mailing Portal not started!")
        cloud_master.unit_test_mode = activated
        log_cfg.info("UNITTEST mode set to %s by admin (from %s) using XMLRPC API" % (activated, request.client.host))
        return 0

    #--------------------------------
    # unstable API

    @doc_hide
    def xmlrpc_get_global_stats(self, request):
        """
        Returns global statistics such as mailings count, recipients count, etc..
        """
        log_api.debug("XMLRPC: xmlrpc_get_global_stats()")
        stats = {
            'mailings_count': Mailing.count(),
            'active_mailings_count': Mailing.find({'status': {'$in': [MAILING_STATUS.READY,
                                                                       MAILING_STATUS.RUNNING,
                                                                       MAILING_STATUS.PAUSED]}}).count(),
            'recipients_count': MailingRecipient.count(),
            'active_recipients_count': MailingRecipient.find({'send_status': {'$in': [RECIPIENT_STATUS.READY,
                                                                                      RECIPIENT_STATUS.IN_PROGRESS,
                                                                                      RECIPIENT_STATUS.WARNING]}}).count()
        }

    @doc_hide
    def xmlrpc_master_db_find(self, request, collection, filter, projection, skip, limit, sort):
        """
        Executes a query to the master database and returns the results. This function expose part of the find()
        function in pymongo API.

        :param collection: the collection name
        :param filter: (optional) a SON object specifying elements which must be present for a document to be included
            in the result set
        :param projection: (optional) a list of field names that should be returned in the result set or a dict
            specifying the fields to include or exclude. If projection is a list "_id" will always be returned. Use a dict
            to exclude fields from the result (e.g. projection={'_id': False}).
        :param skip: (optional) the number of documents to omit (from the start of the result set) when returning the
            results
        :param limit: (optional) the maximum number of results to return
        :param sort: (optional) a list of (key, direction) pairs specifying the sort order for this query.

        :return: Returns an array of results
        """
        log_api.debug("XMLRPC: xmlrpc_master_db_find(collection=%s, filter=%s, projection=%s, skip=%s, limit=%s, sort=%s)",
                      collection, filter, projection, skip, limit, sort)
        conn = Connection.instance()
        coll = conn.get_collection(collection)
        return list(coll.find(spec=filter, projection=projection, skip=skip, limit=limit, sort=sort))
