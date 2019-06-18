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

"""SSL management module"""
import logging
import os
from . import settings

__author__ = 'ricard'

from OpenSSL import crypto, SSL
from socket import gethostname
from pprint import pprint
from time import time, gmtime, mktime
from os.path import exists, join


def create_self_signed_cert(cert_dir, basename):
    """
    If datacard.crt and datacard.key don't exist in cert_dir, create a new
    self-signed cert and keypair and write them into that directory.
    """

    CERT_FILE = basename + ".crt"
    KEY_FILE = basename + ".key"

    if not exists(join(cert_dir, CERT_FILE)) \
            or not exists(join(cert_dir, KEY_FILE)):

        # create a key pair
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 1024)

        # create a self-signed cert
        cert = crypto.X509()
        cert.get_subject().C = "FR"
        cert.get_subject().ST = "Gironde"
        cert.get_subject().L = "Pessac"
        cert.get_subject().O = "CRD"
        cert.get_subject().OU = "CloudMailing"
        cert.get_subject().CN = gethostname()
        cert.set_serial_number(int(time()))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10*365*24*60*60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha1')

        open(join(cert_dir, CERT_FILE), "wb").write(
            crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        open(join(cert_dir, KEY_FILE), "wb").write(
            crypto.dump_privatekey(crypto.FILETYPE_PEM, k))


def make_SSL_context():
    """Returns an SSLContextFactory object, usable to create SSL TCP listeners."""
    ssl_crt_file = os.path.join(settings.SSL_CERTIFICATE_PATH, settings.SSL_CERTIFICATE_NAME + ".crt")
    ssl_key_file = os.path.join(settings.SSL_CERTIFICATE_PATH, settings.SSL_CERTIFICATE_NAME + ".key")
    try:
        if not os.path.exists(ssl_crt_file) or not os.path.exists(ssl_key_file):
            logging.warn("SSL certificate not found!")
            if not os.path.exists(settings.SSL_CERTIFICATE_PATH):
                os.makedirs(settings.SSL_CERTIFICATE_PATH)
            logging.info("Generating self signed SSL certificate...")
            create_self_signed_cert(settings.SSL_CERTIFICATE_PATH,
                                              settings.SSL_CERTIFICATE_NAME)
        if os.path.exists(ssl_crt_file) or os.path.exists(ssl_key_file):
            from twisted.internet.ssl import DefaultOpenSSLContextFactory, PrivateCertificate
            return DefaultOpenSSLContextFactory(privateKeyFileName = ssl_key_file,
                                                certificateFileName = ssl_crt_file)
        else:
            logging.error("SSL Certificate is missing! Some services won't be able to start.")
    except Exception:
        logging.exception("Can't initialize SSL certificate. Some services won't be able to start.")
