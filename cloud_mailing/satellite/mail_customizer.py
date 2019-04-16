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
from email.headerregistry import Address

import base64
import pickle
import io
import email
import email.generator
import email.parser
import email.policy
import logging
import os
import re
import threading
import urllib.request, urllib.parse, urllib.error
from email.message import EmailMessage

import dkim
import jinja2
from jinja2 import nodes
from jinja2.ext import Extension

import sys
print(sys.path)
from ..common.encoding import force_bytes, force_str
from .models import MailingRecipient
from ..common import settings
from ..common.email_tools import header_to_unicode

__author__ = 'ricard'


class MailCustomizer:
    """Customize the mailing email to a recipient, then save it to a folder."""

    mailingsContent = {} # key = mailing__id, value = email.message.EmailMessage
    _parserLock = threading.Lock()
    re_links = re.compile(r"(<a [^>]*href\s*=\s*['\"])(https?://[^'\"]*)(['\"])")

    def __init__(self, recipient, read_tracking=True, click_tracking=False, url_encoding=None):
        assert(isinstance(recipient, MailingRecipient))

        self.recipient = recipient
        self.unsubscribe_url = self.make_unsubscribe_url(recipient.mailing.tracking_url, recipient.tracking_id)
        self.tracking_url = self.make_tracking_url(recipient.mailing.tracking_url, recipient.tracking_id)
        self.log = logging.getLogger("mailing")
        self.temp_path = settings.MAIL_TEMP
        if not os.path.exists(settings.MAIL_TEMP):
            os.makedirs(settings.MAIL_TEMP)
        self.read_tracking = read_tracking
        self.click_tracking = click_tracking
        self.url_encoding = url_encoding

    @staticmethod
    def make_original_file_name(mailing_id):
        """compose the filename where the original email is stored."""
        return 'orig_ml_%d.rfc822' % mailing_id

    @staticmethod
    def make_file_name(mailing_id, recipient_id):
        """compose the filename where the customized email is stored."""
        return 'cust_ml_%d_rcpt_%s.rfc822' % (mailing_id, str(recipient_id))

    @staticmethod
    def make_patten_for_queue(queue_id):
        """compose the pattern that match with all filenames generated for this queue."""
        return 'cust_ml_%d_rcpt_*.rfc822*' % queue_id

    def make_unsubscribe_url(self, base_url, contact_sha1):
        if not base_url:
            return ""
        return "%(base_url)su/%(sha1)s" % {'base_url': base_url,
                                           'sha1': contact_sha1,
        }

    def make_tracking_url(self, base_url, contact_sha1):
        if not base_url:
            return ""
        return "%(base_url)sr/%(sha1)s/blank.gif" % {'base_url': base_url,
                                                     'sha1': contact_sha1,
        }

    def make_clic_url(self, base_url, contact_sha1):
        if not base_url:
            return ""
        return "%(base_url)sc/%(sha1)s/" % {'base_url': base_url,
                                            'sha1': contact_sha1,
        }

    def _do_customization(self, body, contact_data, is_html=False):
        body = body.replace(r"%7B%7B%20unsubscribe%20%7D%7D", r"{{ unsubscribe }}")
        body = body.replace(r"%7B%7Bunsubscribe%7D%7D", r"{{ unsubscribe }}")
        if is_html and self.click_tracking:
            output_link = r"\1{{ _tracking_url }}?"
            if self.url_encoding == 'base64':
                output_link += 'c=b64&'
            body = self.re_links.sub(output_link + r"o={{ '\2'|url_encode }}&t={% click %}\2{% endclick %}\3", body)
        context = {
            'UNSUBSCRIBE': self.unsubscribe_url,
            'unsubscribe': self.unsubscribe_url,
            '_tracking_url': self.make_clic_url(self.recipient.mailing.tracking_url, self.recipient.tracking_id),
            '_url_encoding': self.url_encoding,
        }
        context.update(contact_data)
        template = jinja2.Template(body, extensions=['jinja2.ext.with_', ClickExtension])
        if is_html and self.read_tracking:
            tracking_img = '<img src="%s" border="0" alt="" width="1" height="1" />\n' % self.tracking_url
        else:
            tracking_img = ''
        return template.render(context) + tracking_img

    def _customize_message(self, message, contact_data):
        """Do all dirty job to customize the content of this message.

        The given message HAVE TO be single part and of type "text/*".
        """
        assert(isinstance(message, EmailMessage))
        assert(message.is_multipart() == False)
        assert(message.get_content_maintype() == 'text')

        # charset = message.get_content_charset(failobj='us-ascii')
        # original = message.get_payload(decode=True)
        original = message.get_content()
        assert isinstance(original, str)
        decoded = original
        # encoding = message['Content-Transfer-Encoding']
        # del message['Content-Transfer-Encoding']
        new_body = self._do_customization(decoded,
                                          contact_data,
                                          message.get_content_subtype() == 'html'
                                          )
        message.set_content(new_body, message.get_content_subtype())
        # if encoding == 'quoted-printable':
        #     email.encoders.encode_quopri(message)
        # elif encoding == 'base64':
        #     email.encoders.encode_base64(message)
        # else:
        #     email.encoders.encode_7or8bit(message)

    def _make_mime_part(self, attachment):
        from email import encoders

        data = base64.b64decode(attachment['data'])
        mimetype = attachment['content-type']
        filename = attachment.get('filename')
        content_id = attachment.get('content-id')

        maintype, subtype = mimetype.split('/')
        if maintype == 'text':
            import email.mime.text

            charset = attachment['charset']
            p =  email.mime.text.MIMEText(data, _subtype=subtype, _charset=charset or 'us-ascii')
        elif maintype == 'image':
            import email.mime.image
            p = email.mime.image.MIMEImage(data, subtype)
        else:
            import email.mime.nonmultipart
            p = email.mime.nonmultipart.MIMENonMultipart(maintype, subtype)
            p.set_payload(data)
            encoders.encode_base64(p)

        if filename:
            p['Content-Disposition'] = 'attachment'
            p.set_param('filename', filename, header='Content-Disposition')
        if content_id:
            p['Content-ID'] = content_id
        return p

    def make_contact_data_dict(self, recipient):
        #noinspection PyBroadException
        try:
            contact_data = recipient.contact_data
        except Exception as ex:
            self.log.exception("Error evaluating Contact data: '%s'", repr(recipient.contact_data))
            contact_data = {'email': str(recipient.email)}
        return contact_data

    def _run_customizer(self):
        """Executes the entire process of customize a mailing for a recipient
        and returns its full path.

        This may take some time and shouldn't be run from the reactor thread.
        """
        try:
            fullpath = os.path.join(self.temp_path, MailCustomizer.make_file_name(self.recipient.mailing.id, self.recipient.id))
            if os.path.exists(fullpath):
                self.log.debug("Customized email found here: %s", fullpath)
                parser = email.parser.Parser(policy=email.policy.default)
                with open(fullpath, 'rt') as fd:
                    header = parser.parse(fd, headersonly=True)
                    return header['Message-ID'], fullpath
            contact_data = self.make_contact_data_dict(self.recipient)
            message = self._parse_message()
            assert(isinstance(contact_data, dict))
            assert(isinstance(message, EmailMessage))
            #email.iterators._structure(message)

            mixed_attachments=[]
            related_attachments=[]
            for attachment in contact_data.get('attachments', []):
                if 'content-id' in attachment:
                    related_attachments.append(attachment)
                else:
                    mixed_attachments.append(attachment)

            #bodies = MailingBody.objects.filter(relay = self.recipient.mailing_queue).order_by('header_pos')
            def convert_to_mixed(part, mixed_attachments, subtype):
                import email.mime.multipart

                part2 = email.mime.multipart.MIMEMultipart(_subtype=subtype)
                part2.set_payload(part.get_payload())
                del part['Content-Type']
                part['Content-Type'] = 'multipart/mixed'
                part.set_payload(None)
                part.attach(part2)
                for attachment in mixed_attachments:
                    part.attach(self._make_mime_part(attachment))

            def personalise_bodies(part, mixed_attachments=[], related_attachments=[]):
                import email.message
                assert(isinstance(part, email.message.EmailMessage))
                if part.is_multipart():
                    subtype = part.get_content_subtype()
                    if subtype == 'mixed':
                        personalise_bodies(part.get_payload(0), related_attachments=related_attachments)
                        for attachment in mixed_attachments:
                            part.attach(self._make_mime_part(attachment))

                    elif subtype == 'alternative':
                        for p in part.get_payload():
                            personalise_bodies(p, related_attachments=related_attachments)
                        if mixed_attachments:
                            convert_to_mixed(part, mixed_attachments, subtype="alternative")

                    elif subtype == 'digest':
                        raise email.errors.MessageParseError("multipart/digest not supported")

                    elif subtype == 'parallel':
                        raise email.errors.MessageParseError("multipart/parallel not supported")

                    elif subtype == 'related':
                        personalise_bodies(part.get_payload(0))
                        for attachment in related_attachments:
                            part.attach(self._make_mime_part(attachment))
                        if mixed_attachments:
                            convert_to_mixed(part, mixed_attachments, subtype="related")

                    else:
                        self.log.warn("Unknown multipart subtype '%s'" % subtype)

                else:
                    maintype = part.get_content_maintype()
                    if maintype == 'text':
                        self._customize_message(part, contact_data)

                        if mixed_attachments:
                            import email.mime.text

                            part2 = email.mime.text.MIMEText(part.get_payload(decode=True).decode())
                            del part['Content-Type']
                            part['Content-Type'] = 'multipart/mixed'
                            part.set_payload(None)
                            part.attach(part2)
                            for attachment in mixed_attachments:
                                part.attach(self._make_mime_part(attachment))

                    else:
                        self.log.warn("personalise_bodies(): can't handle '%s' parts" % part.get_content_type())

            personalise_bodies(message, mixed_attachments, related_attachments)

            # Customize the subject
            subject = self._do_customization(header_to_unicode('subject', message.get("Subject", "")), contact_data)
            # Remove some headers
            for header in ('Subject', 'Received', 'To', 'From', 'User-Agent', 'Date', 'Message-ID', 'List-Unsubscribe',
                           'DKIM-Signature', 'Authentication-Results', 'Received-SPF', 'Received-SPF', 'X-Received',
                           'Delivered-To', 'Feedback-ID', 'Precedence', 'Return-Path'):
                if header in message:
                    del message[header]

            message['Subject'] = subject

            # Adding missing headers
            # message['Precedence'] = "bulk"
            message['From'] = Address(self.recipient.sender_name, *self.recipient.mail_from.split('@'))
            message['To'] = Address(('%s %s' % (contact_data.get('firstname', ''), contact_data.get('lastname', ''))).strip(),
                                    *contact_data['email'].split('@'))
            message['Date'] = email.utils.formatdate()
            # message['Message-ID'] = email.utils.make_msgid()  # very very slow on certain circumstance
            message['Message-ID'] = "<%s.%d@cm.%s>" % (self.recipient.id, self.recipient.mailing.id, self.recipient.domain_name )
            if self.unsubscribe_url:
                message['List-Unsubscribe'] = self.unsubscribe_url

            fp = io.StringIO()
            generator = email.generator.Generator(fp, mangle_from_=False)
            generator.flatten(message)
            flattened_message = fp.getvalue()
            flattened_message = self.add_dkim_signature(flattened_message)
            flattened_message = self.add_fbl(flattened_message)

            with open(fullpath+'.tmp', 'wt') as fp:
                fp.write(flattened_message)
                fp.close()
            if os.path.exists(fullpath):
                os.remove(fullpath)
            os.rename(fullpath+'.tmp', fullpath)
            return message['Message-ID'], fullpath

        except Exception:
            self.log.exception("Failed to customize mailing '%s' for recipient '%s'" % (self.recipient.mail_from, self.recipient.email))
            raise

    def add_dkim_signature(self, flattened_message):
        sig = ''
        dkim_settings = self.recipient.mailing.get('dkim', None)
        if dkim_settings and dkim_settings.get('enabled', True):
            sig = dkim.sign(flattened_message.encode(), dkim_settings['selector'].encode(), dkim_settings['domain'].encode(),
                            dkim_settings['privkey'].encode(),
                            canonicalize=map(force_bytes, dkim_settings.get('canonicalize', (b'relaxed', b'simple'))),
                            signature_algorithm=dkim_settings.get('signature_algorithm', 'rsa-sha256').encode(),
                            include_headers=list(map(force_bytes, dkim_settings.get('include_headers', []))) or None,
                            length=dkim_settings.get('length', False),
                            logger=self.log)
            sig = sig.replace(b'\r\n', b'\n').decode()
        return sig + flattened_message

    def add_fbl(self, flattened_message):
        sig = ''
        mailing = self.recipient.mailing
        fbl_settings = mailing.get('feedback_loop', {})
        if not fbl_settings:
            return flattened_message
        dkim_settings = fbl_settings.get('dkim', None)
        sender_id = fbl_settings.get('sender_id', None)
        if dkim_settings and sender_id:
            campaign_id = fbl_settings.get('campaign_id', mailing.id)
            customer_id = fbl_settings.get('customer_id', mailing.domain_name)
            mail_type_id = fbl_settings.get('mail_type_id', mailing.type)
            fbl_header = 'Feedback-ID: %s:%s:%s:%s\n' % (campaign_id, customer_id, mail_type_id, sender_id)
            flattened_message = fbl_header + flattened_message
            d = dkim.DKIM(flattened_message.encode(),
                          signature_algorithm=dkim_settings.get('signature_algorithm', 'rsa-sha256').encode(),
                          logger=self.log)
            sig = d.sign(dkim_settings['selector'].encode(), dkim_settings['domain'].encode(), dkim_settings['privkey'].encode(),
                         canonicalize=map(force_bytes, dkim_settings.get('canonicalize', (b'relaxed', b'simple'))),
                         include_headers=map(force_bytes, dkim_settings.get('include_headers', d.default_sign_headers()) + [b'Feedback-ID']),
                         length=dkim_settings.get('length', False),
                         )
            sig = sig.replace(b'\r\n', b'\n').decode()  # sig is in unicode
        return sig + flattened_message

    def _parse_message(self):
        MailCustomizer._parserLock.acquire()
        try:
            result = MailCustomizer.mailingsContent.get(self.recipient.mailing.id, None)
            if result:
                return pickle.loads(result)
            else:
                result = self.recipient.mailing.get_message()
                MailCustomizer.mailingsContent[self.recipient.mailing.id] = pickle.dumps(result)
            return result
        finally:
            MailCustomizer._parserLock.release()

    def customize(self):
        """Start the customization process. Returns a deferred.
        """
        return self._run_customizer()
        #return deferToThread(self._run_customizer)




class ClickExtension(Extension):
    """
    Jinja2 extension to handle click tracking
    """
    # a set of names that trigger the extension.
    tags = set(['click'])

    def __init__(self, environment):
        super(ClickExtension, self).__init__(environment)

        # add the defaults to the environment
        # environment.extend(
        #     fragment_cache_prefix='',
        #     fragment_cache=None
        # )
        environment.filters['url_encode'] = self.do_url_encode

    def parse(self, parser):
        # the first token is the token that started the tag.  In our case
        # we only listen to ``'click'`` so this will be a name token with
        # `click` as value.  We get the line number so that we can give
        # that line number to the nodes we create by hand.
        lineno = next(parser.stream).lineno
        ctx_ref = jinja2.nodes.ContextReference()

        # # now we parse a single expression that is used as cache key.
        # args = [parser.parse_expression()]
        #
        # # if there is a comma, the user provided a timeout.  If not use
        # # None as second parameter.
        # if parser.stream.skip_if('comma'):
        #     args.append(parser.parse_expression())
        # else:
        #     args.append(nodes.Const(None))

        # now we parse the body of the cache block up to `endclick` and
        # drop the needle (which would always be `endclick` in that case)
        body = parser.parse_statements(['name:endclick'], drop_needle=True)

        # now return a `CallBlock` node that calls our _cache_support
        # helper method on this extension.
        return nodes.CallBlock(self.call_method('_click_support', [ctx_ref]),
                               [], [], body).set_lineno(lineno)

    def _click_support(self, context, caller):
        """Helper callback."""
        rv = caller()
        return self.do_url_encode(context, rv.encode('utf-8'))

    @jinja2.contextfilter
    def do_url_encode(self, context, s):
        s = force_bytes(s)
        if context['_url_encoding'] == 'base64':
            return force_str(base64.urlsafe_b64encode(s).strip(b'='))
        else:
            return urllib.parse.quote(s)
