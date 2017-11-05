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
from ...common.email_tools import header_to_unicode
from ...common.unittest_mixins import DatabaseMixin
from ..models import Mailing
from twisted.trial import unittest
import email.parser
import email.message
from mogo import connect
from ...common import settings


class MailingTestCase(DatabaseMixin, unittest.TestCase):

    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_create_mailing_from_message(self):

        parser = email.parser.BytesParser()
        msg = parser.parsebytes(b"""Content-Transfer-Encoding: 7bit
Content-Type: multipart/alternative; boundary="===============2840728917476054151=="
Subject: Great news!
From: Mailing Sender <sender@my-company.biz>
To: <firstname.lastname@domain.com>
Date: Wed, 05 Jun 2013 06:05:56 -0000

This is a multi-part message in MIME format.
--===============2840728917476054151==
Content-Type: text/plain; charset="windows-1252"
Content-Transfer-Encoding: quoted-printable

This is a very simple mailing. I=92m happy.
--===============2840728917476054151==
Content-Type: text/html; charset="windows-1252"
Content-Transfer-Encoding: quoted-printable

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html><head>
<META http-equiv=3DContent-Type content=3D"text/html; charset=3Diso-8859-1">
</head>
<body>
This is <strong> a very simple</strong> <u>mailing</u>. =
I=92m happy! Nothing else to say...
</body></html>

--===============2840728917476054151==--
""")
        mailing = Mailing.create_from_message(msg, mail_from='sender@my-company.biz',
                                                   sender_name='Mailing Sender',
                                                   scheduled_start=None, scheduled_duration=None)

        message = parser.parsebytes(mailing.header + mailing.body)
        assert(isinstance(message, email.message.Message))
        self.assertTrue(message.is_multipart())
        self.assertEqual("multipart/alternative", message.get_content_type())
        self.assertIsInstance(message.get_payload(i=0), email.message.Message)
        self.assertEqual("text/plain", message.get_payload(i=0).get_content_type())
        self.assertEqual("windows-1252", message.get_payload(i=0).get_param('charset'))
        self.assertEqual("text/html", message.get_payload(i=1).get_content_type())
        self.assertEqual("windows-1252", message.get_payload(i=1).get_param('charset'))
        self.assertEqual(b"This is a very simple mailing. I\x92m happy.", message.get_payload(i=0).get_payload(decode=True))
        self.assertIn(b"This is <strong> a very simple</strong> <u>mailing</u>. I\x92m happy! ", message.get_payload(i=1).get_payload(decode=True))
        # print message.as_string()

    def test_create_mailing_from_message_with_encoded_headers(self):

        parser = email.parser.BytesParser()
        msg = parser.parsebytes(b"""Content-Transfer-Encoding: 7bit
Content-Type: multipart/alternative; boundary="===============2840728917476054151=="
Subject: Great news!
From: =?UTF-8?B?Q2VkcmljIFJJQ0FSRA==?= <my-mailing@cm-unittest.net>
To: <firstname.lastname@domain.com>
Date: Wed, 05 Jun 2013 06:05:56 -0000

This is a multi-part message in MIME format.
--===============2840728917476054151==
Content-Type: text/plain; charset="windows-1252"
Content-Transfer-Encoding: quoted-printable

This is a very simple mailing. I=92m happy.
--===============2840728917476054151==
Content-Type: text/html; charset="windows-1252"
Content-Transfer-Encoding: quoted-printable

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html><head>
<META http-equiv=3DContent-Type content=3D"text/html; charset=3Diso-8859-1">
</head>
<body>
This is <strong> a very simple</strong> <u>mailing</u>. =
I=92m happy! Nothing else to say...
</body></html>

--===============2840728917476054151==--
""")
        mailing = Mailing.create_from_message(msg, scheduled_start=None, scheduled_duration=None)

        message = parser.parsebytes(mailing.header + mailing.body)
        assert(isinstance(message, email.message.Message))
        mail_from = header_to_unicode(message.get("From"))

        self.assertEqual("Cedric RICARD <my-mailing@cm-unittest.net>", mail_from)
        # print message.as_string()
