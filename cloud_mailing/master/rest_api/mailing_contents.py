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
import email.errors
import email.message
import json

from twisted.web import server
from twisted.web.resource import Resource

from ...common import http_status
from ...common.rest_api_common import ApiResource
from ...common.db_common import get_db

__author__ = 'Cedric RICARD'


# noinspection PyPep8Naming
class MailingContentApi(ApiResource):
    """
    Display mailing content
    """
    def __init__(self, mailing_id=None):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def getChild(self, name, request):
        if name == 'cid':
            return MailingContentIDsApi(self.mailing_id)
        return ApiResource.getChild(self, name, request)


    def render_GET(self, request):
        self.log_call(request)
        db = get_db()
        db.mailing.find_one({'_id': self.mailing_id})\
            .addCallback(self.cb_get_mailing, request)\
            .addErrback(self.eb_get_mailing, request)
        return server.NOT_DONE_YET

    def cb_get_mailing(self, mailing, request):
        mparser = email.parser.FeedParser()
        mparser.feed(mailing['header'])
        mparser.feed(mailing['body'])
        msg = mparser.close()

        def get_html_body(part):
            self.log.debug("***")
            import email.message
            assert (isinstance(part, email.message.Message))
            if part.is_multipart():
                self.log.debug(part.get_content_type())
                subtype = part.get_content_subtype()
                if subtype == 'mixed':
                    return get_html_body(part.get_payload(0))

                elif subtype == 'alternative':
                    for p in part.get_payload():
                        self.log.debug("  sub = %s", p.get_content_type())
                        if p.get_content_type() == 'text/html' or p.get_content_type() == "multipart/related":
                            return get_html_body(p)

                elif subtype == 'digest':
                    raise email.errors.MessageParseError, "multipart/digest not supported"

                elif subtype == 'parallel':
                    raise email.errors.MessageParseError, "multipart/parallel not supported"

                elif subtype == 'related':
                    return get_html_body(part.get_payload(0))

                else:
                    self.log.warn("Unknown multipart subtype '%s'" % subtype)

            else:
                maintype, subtype = part.get_content_type().split('/')
                if maintype == 'text':
                    self.log.debug("body found (%s/%s)", maintype, subtype)
                    # request.setHeader('Content-Type', part.get_content_type())
                    part_body = part.get_payload().encode('utf8')
                    self.log.debug("body type: %s", type(part_body))
                    return part_body
                else:
                    self.log.warn("get_html_body(): can't handle '%s' parts" % part.get_content_type())
            return ""

        request.setResponseCode(http_status.HTTP_200_OK)
        request.setHeader('Content-Type', 'text/html')

        request.write(get_html_body(msg))
        request.finish()

    def eb_get_mailing(self, error, request):
        self.log.error("Error returning HTML content for mailing [%d]: %s", self.mailing_id, error)
        request.setResponseCode(http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        request.write("<html><body><b>ERROR</b>: can't get content.</body></html>")
        request.finish()


class MailingContentIDsApi(ApiResource):
    """
    Should display mailing related attachments (but currently does nothing)
    """
    def __init__(self, mailing_id):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def getChild(self, name, request):
        return MailingRelatedAttachmentApi(self.mailing_id, name)


class MailingRelatedAttachmentApi(ApiResource):
    """
    Returns a related attachment
    """
    def __init__(self, mailing_id, cid):
        Resource.__init__(self)
        self.mailing_id = mailing_id
        self.cid = cid

    def render_GET(self, request):
        self.log_call(request)
        db = get_db()
        db.mailing.find_one({'_id': self.mailing_id}) \
            .addCallback(self.cb_get_mailing, request) \
            .addErrback(self.eb_get_mailing, request)
        return server.NOT_DONE_YET

    def cb_get_mailing(self, mailing, request):
        mparser = email.parser.FeedParser()
        mparser.feed(mailing['header'])
        mparser.feed(mailing['body'])
        msg = mparser.close()

        cid = '<%s>' % self.cid
        for part in msg.walk():
            if part.get('Content-ID', None) == cid:
                request.setHeader('Content-Type', part.get_content_type())
                request.write(part.get_payload(decode=True))
                request.finish()
                return

        request.setResponseCode(http_status.HTTP_404_NOT_FOUND)
        request.setHeader('Content-Type', 'application/json')
        request.write(json.dumps({'error': "Part CID '%s' not found" % self.cid}))
        request.finish()
        return

    def eb_get_mailing(self, error, request):
        self.log.error("Error returning HTML content for mailing [%d]: %s", self.mailing_id, error)
        request.setResponseCode(http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        request.write("<html><body><b>ERROR</b>: can't get content.</body></html>")
        request.finish()


