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

import logging
from twisted.internet import defer
from twisted.internet.error import DNSLookupError
from twisted.mail.relaymanager import CanonicalNameLoop, CanonicalNameChainTooLong
from twisted.names.dns import RRHeader, Record_MX
from twisted.python.failure import Failure

__author__ = 'ricard'


class MXCalculator:
    """
    A utility for looking up mail exchange hosts and tracking whether they are
    working or not.

    @ivar clock: L{IReactorTime} provider which will be used to decide when to
        retry mail exchanges which have not been working.
    """
    timeOutBadMX = 1 * 60 # 5 minutes
    fallbackToDomain = False

    def __init__(self, resolver=None, clock=None):
        self.log = logging.getLogger('mx_calc')
        self.badMXs = {}
        if resolver is None:
            from twisted.names.client import createResolver
            resolver = createResolver()
        self.resolver = resolver
        if clock is None:
            from twisted.internet import reactor as clock
        self.clock = clock


    def markBad(self, mx):
        """Indicate a given mx host is not currently functioning.

        @type mx: C{str}
        @param mx: The hostname of the host which is down.
        """
        #noinspection PyUnresolvedReferences
        self.badMXs[str(mx)] = self.clock.seconds() + self.timeOutBadMX
        self.log.warn("MX '%s' marked as bad", str(mx))

    def markGood(self, mx):
        """Indicate a given mx host is back online.

        @type mx: C{str}
        @param mx: The hostname of the host which is up.
        """
        try:
            del self.badMXs[mx]
            self.log.info("MX '%s' marked as good", str(mx))
        except KeyError:
            pass

    def cleanupBadMXs(self):
        #noinspection PyUnresolvedReferences
        t = self.clock.seconds()
        toBeDeleted = []
        for key, value in list(self.badMXs.items()):
            if value < t:
                toBeDeleted.append(key)
        for key in toBeDeleted:
            del self.badMXs[key]

    def getMX(self, domain, maximumCanonicalChainLength=3):
        """
        Find an MX record for the given domain.

        @type domain: C{str}
        @param domain: The domain name for which to look up an MX record.

        @type maximumCanonicalChainLength: C{int}
        @param maximumCanonicalChainLength: The maximum number of unique CNAME
            records to follow while looking up the MX record.

        @return: A L{Deferred} which is called back with a string giving the
            name in the found MX record or which is errbacked if no MX record
            can be found.
        """
        mailExchangeDeferred = self.resolver.lookupMailExchange(domain)
        mailExchangeDeferred.addCallback(self._filterRecords)
        mailExchangeDeferred.addCallback(
            self._cbMX, domain, maximumCanonicalChainLength)
        mailExchangeDeferred.addErrback(self._ebMX, domain)
        return mailExchangeDeferred


    def _filterRecords(self, records):
        """
        Convert a DNS response (a three-tuple of lists of RRHeaders) into a
        mapping from record names to lists of corresponding record payloads.
        """
        self.log.debug("_filterRecords: %s", records)
        recordBag = {}
        for answer in records[0]:
            self.log.debug("_filterRecords: answer = %s", repr(answer))
            self.log.debug("_filterRecords:   name = %s", repr(answer.name))
            recordBag.setdefault(str(answer.name).lower(), []).append(answer.payload)

        self.log.debug("_filterRecords: recordBag = %s", repr(recordBag))
        return recordBag


    def _cbMX(self, answers, domain, cnamesLeft):
        """
        Try to find the MX host from the given DNS information.

        This will attempt to resolve CNAME results.  It can recognize loops
        and will give up on non-cyclic chains after a specified number of
        lookups.
        """
        # Do this import here so that relaymanager.py doesn't depend on
        # twisted.names, only MXCalculator will.
        from twisted.names import dns, error

        seenAliases = set()
        exchanges = []
        # Examine the answers for the domain we asked about
        pertinentRecords = answers.get(domain, [])
        while pertinentRecords:
            record = pertinentRecords.pop()

            # If it's a CNAME, we'll need to do some more processing
            if record.TYPE == dns.CNAME:

                # Remember that this name was an alias.
                seenAliases.add(domain)

                canonicalName = str(record.name)
                # See if we have some local records which might be relevant.
                if canonicalName in answers:

                    # Make sure it isn't a loop contained entirely within the
                    # results we have here.
                    if canonicalName in seenAliases:
                        self.log.warn("Infinite loop detected for '%s' (querying MX for domain '%s')", canonicalName, domain)
                        return Failure(CanonicalNameLoop(record))

                    pertinentRecords = answers[canonicalName]
                    exchanges = []
                else:
                    if cnamesLeft:
                        # Request more information from the server.
                        self.log.debug("_cbMX: recursive request for CNAME %s", canonicalName)
                        return self.getMX(canonicalName, cnamesLeft - 1)
                    else:
                        # Give up.
                        self.log.warn("Canonical name chain is too long for '%s' (querying MX for domain '%s')", canonicalName, domain)
                        return Failure(CanonicalNameChainTooLong(record))

            # If it's an MX, collect it.
            if record.TYPE == dns.MX:
                exchanges.append((record.preference, record))

        if exchanges:
            records = []
            exchanges.sort(key=lambda x: x[0])
            for (preference, record) in exchanges:
                #print preference, record, type(record)
                host = str(record.name)
                if host not in self.badMXs:
                    #return record
                    records.append(record)
                else:
                    #noinspection PyUnresolvedReferences
                    t = self.clock.seconds() - self.badMXs[host]
                    if t >= 0:
                        del self.badMXs[host]
                        #return record
                        records.append(record)
            if not records:
                records.append(exchanges[0][1])
            self.log.debug("_cbMX: records = %s", repr(records))
            return records
        else:
            # Treat no answers the same as an error - jump to the errback to try
            # to look up an A record.  This provides behavior described as a
            # special case in RFC 974 in the section headed I{Interpreting the
            # List of MX RRs}.
            self.log.error("No MX records for %r", domain)
            return Failure(
                error.DNSNameError("No MX records for %r" % (domain,)))


    #noinspection PyExceptionInherit
    def _ebMX(self, failure, domain):
        self.log.error("DNS Error for domain %s: %s", domain, failure)
        from twisted.names import error as dns_error, dns

        if self.fallbackToDomain:
            failure.trap(dns_error.DNSNameError)
            self.log.error("MX lookup failed; attempting to use hostname (%s) directly" % (domain,))

            # Alright, I admit, this is a bit icky.
            d = self.resolver.getHostByName(domain)
            def cbResolved(addr):
                return [dns.Record_MX(name=addr)]

            def ebResolved(err):
                err.trap(dns_error.DNSNameError)
                raise DNSLookupError()
            d.addCallbacks(cbResolved, ebResolved)
            return d
        elif failure.check(dns_error.DNSNameError):
            self.log.error("No MX records for %r", domain)
            raise DNSLookupError("No MX found for %r" % (domain,))
        self.log.error("Error during MX query for domain '%s': %s", domain, failure)
        return failure


class FakedMXCalculator:
    def getMX(self, domain):
        return defer.succeed([RRHeader(name=domain,
                                       type=Record_MX.TYPE,
                                       payload=Record_MX(1, 'localhost',))])

    def markBad(self, ip):
        pass

    def cleanupBadMXs(self):
        pass
