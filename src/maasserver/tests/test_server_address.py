# Copyright 2012, 2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the server_address module."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from django.conf import settings
from maasserver import server_address
from maasserver.exceptions import (
    NoAddressFoundForHost,
    UnresolvableHost,
    )
from maasserver.server_address import get_maas_facing_server_address
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maastesting.fakemethod import FakeMethod
from netaddr import IPNetwork


class TestServerAddress(MAASServerTestCase):

    def make_hostname(self):
        return '%s.example.com' % factory.make_hostname()

    def set_DEFAULT_MAAS_URL(self, hostname=None, with_port=False):
        """Patch DEFAULT_MAAS_URL to be a (partly) random URL."""
        if hostname is None:
            hostname = self.make_hostname()
        if with_port:
            location = "%s:%d" % (hostname, factory.getRandomPort())
        else:
            location = hostname
        url = 'http://%s/%s' % (location, factory.make_name("path"))
        self.patch(settings, 'DEFAULT_MAAS_URL', url)

    def test_get_maas_facing_server_host_returns_host_name(self):
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_host_returns_ip_if_ip_configured(self):
        ip = factory.getRandomIPAddress()
        self.set_DEFAULT_MAAS_URL(ip)
        self.assertEqual(ip, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_host_returns_nodegroup_maas_url(self):
        hostname = factory.make_hostname()
        maas_url = 'http://%s' % hostname
        nodegroup = factory.make_node_group(maas_url=maas_url)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host(nodegroup))

    def test_get_maas_facing_server_host_strips_out_port(self):
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname, with_port=True)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_address_returns_IP(self):
        ip = factory.getRandomIPAddress()
        self.set_DEFAULT_MAAS_URL(hostname=ip)
        self.assertEqual(ip, get_maas_facing_server_address())

    def test_get_maas_facing_server_address_returns_local_IP(self):
        ip = factory.getRandomIPInNetwork(IPNetwork('127.0.0.0/8'))
        self.set_DEFAULT_MAAS_URL(hostname=ip)
        self.assertEqual(ip, get_maas_facing_server_address())

    def test_get_maas_facing_server_address_returns_nodegroup_maas_url(self):
        ip = factory.getRandomIPInNetwork(IPNetwork('127.0.0.0/8'))
        maas_url = 'http://%s' % ip
        nodegroup = factory.make_node_group(maas_url=maas_url)
        self.assertEqual(
            ip, server_address.get_maas_facing_server_host(nodegroup))

    def test_get_maas_facing_server_address_returns_local_v6_IP(self):
        ip = factory.getRandomIPInNetwork(IPNetwork('::1/128'))
        self.set_DEFAULT_MAAS_URL(hostname=ip)
        self.assertEqual(ip, get_maas_facing_server_address())

    def test_get_maas_facing_server_address_returns_ng_maas_url_ipv6(self):
        ip = factory.get_random_ipv6_address()
        # To put a literal IPv6 address in a URL we must wrap it in
        # brackets, per RFC2732.
        maas_url = 'http://[%s]' % ip
        nodegroup = factory.make_node_group(maas_url=maas_url)
        self.assertEqual(
            ip, server_address.get_maas_facing_server_host(nodegroup))

    def test_get_maas_facing_sa_returns_v4_address_if_mixed_addresses(self):
        # If a server has mixed v4 and v6 addresses,
        # get_maas_facing_server_address() will return a v4 address
        # rather than a v6 one.
        v4_ip = factory.getRandomIPAddress()
        v6_ip = factory.get_random_ipv6_address()
        addr_info_result = [
            (server_address.AF_INET, None, None, None, (v4_ip, None)),
            (server_address.AF_INET6, None, None, None,
                (v6_ip, None, None, None))]
        self.patch(server_address, 'getaddrinfo').return_value = (
            addr_info_result)
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname=hostname)
        self.assertEqual(
            v4_ip, get_maas_facing_server_address())

    def test_get_maas_facing_server_address_resolves_hostname(self):
        ip = factory.getRandomIPAddress()
        addr_info_result = [(
            server_address.AF_INET, None, None, None, (ip, None))]
        resolver = FakeMethod(result=addr_info_result)
        self.patch(server_address, 'getaddrinfo', resolver)
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname=hostname)
        self.assertEqual(
            (ip, [(hostname, server_address.PORT)]),
            (get_maas_facing_server_address(), resolver.extract_args()))

    def test_get_maas_facing_server_address_raises_error_on_no_addrs(self):
        self.patch(server_address, 'getaddrinfo').return_value = []
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname=hostname)
        self.assertRaises(
            NoAddressFoundForHost, get_maas_facing_server_address)

    def test_get_maas_facing_server_address_handles_unresolvable_hosts(self):
        self.patch(server_address, 'getaddrinfo').side_effect = (
            server_address.gaierror())
        hostname = self.make_hostname()
        self.set_DEFAULT_MAAS_URL(hostname=hostname)
        self.assertRaises(
            UnresolvableHost, get_maas_facing_server_address)
