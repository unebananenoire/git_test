# Copyright 2014-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for IP addresses API."""

__all__ = []

import http.client
from unittest import skip

from django.conf import settings
from django.core.urlresolvers import reverse
from maasserver.enum import (
    INTERFACE_LINK_TYPE,
    INTERFACE_TYPE,
    IPADDRESS_TYPE,
)
from maasserver.models import StaticIPAddress
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from maasserver.utils.converters import json_load_bytes
from maasserver.utils.orm import reload_object
from testtools.matchers import Equals


class TestIPAddressesAPI(APITestCase):

    def post_reservation_request(
            self, subnet=None, ip_address=None, network=None,
            mac=None, hostname=None):
        params = {
            'op': 'reserve',
        }
        if ip_address is not None:
            params["ip_address"] = ip_address
        if subnet is not None:
            params["subnet"] = subnet.cidr
        if network is not None and subnet is None:
            params["subnet"] = str(network)
        if mac is not None:
            params["mac"] = mac
        if hostname is not None:
            params["hostname"] = hostname
        return self.client.post(reverse('ipaddresses_handler'), params)

    def post_release_request(self, ip, mac=None):
        params = {
            'op': 'release',
            'ip': ip,
        }
        if mac is not None:
            params["mac"] = mac
        return self.client.post(reverse('ipaddresses_handler'), params)

    def assertNoMatchingNetworkError(self, response, net):
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response.content)
        expected = (
            "Unable to identify subnet %s." % str(net))
        self.assertEqual(
            expected.encode(settings.DEFAULT_CHARSET),
            response.content)

    def test_handler_path(self):
        self.assertEqual(
            '/api/2.0/ipaddresses/', reverse('ipaddresses_handler'))

    def test_POST_reserve_creates_ipaddress(self):
        subnet = factory.make_Subnet()
        response = self.post_reservation_request(subnet)
        self.assertEqual(http.client.OK, response.status_code)
        returned_address = json_load_bytes(response.content)
        [staticipaddress] = StaticIPAddress.objects.all()
        # We don't need to test the value of the 'created' datetime
        # field. By removing it, we also test for its presence.
        del returned_address['created']
        del returned_address['subnet']
        expected = dict(
            alloc_type=staticipaddress.alloc_type,
            ip=staticipaddress.ip,
            resource_uri=reverse('ipaddresses_handler'),
            )
        self.assertEqual(expected, returned_address)
        self.assertEqual(
            IPADDRESS_TYPE.USER_RESERVED, staticipaddress.alloc_type)
        self.assertEqual(self.logged_in_user, staticipaddress.user)

    def test_POST_reserve_with_MAC_links_MAC_to_ip_address(self):
        subnet = factory.make_Subnet()
        mac = factory.make_mac_address()

        response = self.post_reservation_request(subnet=subnet, mac=mac)
        self.assertEqual(http.client.OK, response.status_code)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            staticipaddress.interface_set.first().mac_address,
            Equals(mac))

    def test_POST_returns_error_when_MAC_exists_on_node(self):
        subnet = factory.make_Subnet()
        nic = factory.make_Interface(
            INTERFACE_TYPE.PHYSICAL, vlan=subnet.vlan)

        response = self.post_reservation_request(
            subnet=subnet, mac=nic.mac_address)
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response.content)

    def test_POST_allows_claiming_of_new_static_ips_for_existing_MAC(self):
        subnet = factory.make_Subnet()
        nic = factory.make_Interface(INTERFACE_TYPE.UNKNOWN)

        response = self.post_reservation_request(
            subnet=subnet, mac=nic.mac_address)
        self.expectThat(response.status_code, Equals(http.client.OK))
        [staticipaddress] = nic.ip_addresses.all()
        self.assertEqual(
            staticipaddress.interface_set.first().mac_address,
            nic.mac_address)

    def test_POST_reserve_errors_for_no_matching_subnet(self):
        network = factory.make_ipv4_network()
        factory.make_Subnet(cidr=str(network.cidr))
        other_net = factory.make_ipv4_network(but_not=[network])
        response = self.post_reservation_request(network=other_net)
        self.assertNoMatchingNetworkError(response, other_net)

    def test_POST_reserve_creates_ip_address(self):
        subnet = factory.make_Subnet()
        ip_in_network = factory.pick_ip_in_Subnet(subnet)
        response = self.post_reservation_request(ip_address=ip_in_network)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        returned_address = json_load_bytes(response.content)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            returned_address["alloc_type"],
            Equals(IPADDRESS_TYPE.USER_RESERVED))
        self.expectThat(returned_address["ip"], Equals(ip_in_network))
        self.expectThat(staticipaddress.ip, Equals(ip_in_network))

    def test_POST_reserve_ip_address_detects_in_use_address(self):
        subnet = factory.make_Subnet()
        ip_in_network = factory.pick_ip_in_Subnet(subnet)
        response = self.post_reservation_request(subnet, ip_in_network)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        # Do same request again and check it is rejected.
        response = self.post_reservation_request(subnet, ip_in_network)
        self.expectThat(response.status_code, Equals(http.client.NOT_FOUND))
        self.expectThat(
            response.content, Equals((
                "The IP address %s is already in use." % ip_in_network).encode(
                settings.DEFAULT_CHARSET)))

    @skip(
        "XXX bug=1539248 2015-01-28 blake_r: We need to take into account "
        "all dynamic ranges inside the subnet.")
    def test_POST_reserve_ip_address_rejects_ip_in_dynamic_range(self):
        interface = self.make_interface()
        net = interface.network
        ip_in_network = interface.ip_range_low
        response = self.post_reservation_request(net, ip_in_network)
        self.assertEqual(
            http.client.FORBIDDEN, response.status_code, response.content)

    def test_POST_reserve_without_hostname_creates_ip_without_hostname(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        response = self.post_reservation_request(subnet=subnet)
        self.assertEqual(http.client.OK, response.status_code)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            staticipaddress.dnsresource_set.all().count(), Equals(0))
        # We expect 1 call from the Subnet creation.
        self.expectThat(dns_update_subnets.call_count, Equals(1))

    def test_POST_reserve_with_bad_fqdn_fails(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        hostname = factory.make_hostname()
        domainname = factory.make_name('domain')
        fqdn = "%s.%s" % (hostname, domainname)
        response = self.post_reservation_request(
            subnet=subnet, hostname=fqdn)
        self.assertEqual(http.client.NOT_FOUND, response.status_code)
        # We expect no calls
        self.expectThat(dns_update_subnets.call_count, Equals(0))

    def test_POST_reserve_with_hostname_creates_ip_with_hostname(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        hostname = factory.make_hostname()
        response = self.post_reservation_request(
            subnet=subnet, hostname=hostname)
        self.assertEqual(http.client.OK, response.status_code)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            staticipaddress.dnsresource_set.first().name, Equals(hostname))
        # We expect one from the Subnet, and one from linking DNSResource to
        # the StaticIPAddress.
        self.expectThat(dns_update_subnets.call_count, Equals(2))

    def test_POST_reserve_with_hostname_and_ip_creates_ip_with_hostname(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        hostname = factory.make_hostname()
        ip_in_network = factory.pick_ip_in_Subnet(subnet)
        response = self.post_reservation_request(
            subnet=subnet, ip_address=ip_in_network, hostname=hostname)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        returned_address = json_load_bytes(response.content)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            returned_address["alloc_type"],
            Equals(IPADDRESS_TYPE.USER_RESERVED))
        self.expectThat(returned_address["ip"], Equals(ip_in_network))
        self.expectThat(staticipaddress.ip, Equals(ip_in_network))
        self.expectThat(
            staticipaddress.dnsresource_set.first().name, Equals(hostname))
        # We expect one from the Subnet, and one from linking the DNSResource
        # to the StaticIPAddress.
        self.expectThat(dns_update_subnets.call_count, Equals(2))

    def test_POST_reserve_with_fqdn_creates_ip_with_hostname(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        hostname = factory.make_hostname()
        domainname = factory.make_Domain().name
        fqdn = "%s.%s" % (hostname, domainname)
        response = self.post_reservation_request(
            subnet=subnet, hostname="%s.%s" % (hostname, domainname))
        self.assertEqual(http.client.OK, response.status_code)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            staticipaddress.dnsresource_set.first().name, Equals(hostname))
        self.expectThat(
            staticipaddress.dnsresource_set.first().fqdn, Equals(fqdn))
        # We expect one from the Subnet, and one from linking the DNSResource
        # to the StaticIPAddress.
        self.expectThat(dns_update_subnets.call_count, Equals(2))

    def test_POST_reserve_with_fqdn_and_ip_creates_ip_with_hostname(self):
        from maasserver.dns import config as dns_config_module
        dns_update_subnets = self.patch(
            dns_config_module, 'dns_update_subnets')
        subnet = factory.make_Subnet()
        hostname = factory.make_hostname()
        domainname = factory.make_Domain().name
        fqdn = "%s.%s" % (hostname, domainname)
        ip_in_network = factory.pick_ip_in_Subnet(subnet)
        response = self.post_reservation_request(
            subnet=subnet, ip_address=ip_in_network,
            hostname="%s.%s" % (hostname, domainname))
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        returned_address = json_load_bytes(response.content)
        [staticipaddress] = StaticIPAddress.objects.all()
        self.expectThat(
            returned_address["alloc_type"],
            Equals(IPADDRESS_TYPE.USER_RESERVED))
        self.expectThat(returned_address["ip"], Equals(ip_in_network))
        self.expectThat(staticipaddress.ip, Equals(ip_in_network))
        self.expectThat(
            staticipaddress.dnsresource_set.first().fqdn, Equals(fqdn))
        # We expect one from the Subnet.
        self.expectThat(dns_update_subnets.call_count, Equals(2))

    def test_POST_reserve_with_no_parameters_fails_with_bad_request(self):
        response = self.post_reservation_request()
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response.content)

    def test_POST_reserve_rejects_invalid_ip(self):
        response = self.post_reservation_request(
            ip_address="1690.254.0.1")
        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(
            dict(ip_address=["Enter a valid IPv4 or IPv6 address."]),
            json_load_bytes(response.content))

    def test_POST_release_rejects_invalid_ip(self):
        response = self.post_release_request("1690.254.0.1")
        self.assertEqual(http.client.BAD_REQUEST, response.status_code)
        self.assertEqual(
            dict(ip=["Enter a valid IPv4 or IPv6 address."]),
            json_load_bytes(response.content))

    def test_GET_returns_ipaddresses(self):
        original_ipaddress = factory.make_StaticIPAddress(
            user=self.logged_in_user)
        response = self.client.get(reverse('ipaddresses_handler'))
        self.assertEqual(
            http.client.OK, response.status_code, response.content)

        parsed_result = json_load_bytes(response.content)
        self.assertEqual(1, len(parsed_result), response.content)
        [returned_address] = parsed_result
        fields = {'alloc_type', 'ip'}
        self.assertEqual(
            fields.union({'resource_uri', 'created', 'subnet'}),
            set(returned_address.keys()))
        expected_values = {
            field: getattr(original_ipaddress, field)
            for field in fields
            if field not in ('resource_uri', 'created')
        }
        # We don't need to test the value of the 'created' datetime
        # field.
        del returned_address['created']
        del returned_address['subnet']
        expected_values['resource_uri'] = reverse('ipaddresses_handler')
        self.assertEqual(expected_values, returned_address)

    def test_GET_returns_empty_if_no_ipaddresses(self):
        response = self.client.get(reverse('ipaddresses_handler'))
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        self.assertEqual([], json_load_bytes(response.content))

    def test_GET_only_returns_request_users_addresses(self):
        ipaddress = factory.make_StaticIPAddress(user=self.logged_in_user)
        factory.make_StaticIPAddress(user=factory.make_User())
        response = self.client.get(reverse('ipaddresses_handler'))
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        parsed_result = json_load_bytes(response.content)
        [returned_address] = parsed_result
        self.assertEqual(ipaddress.ip, returned_address['ip'])

    def test_GET_sorts_by_id(self):
        addrs = []
        for _ in range(3):
            addrs.append(
                factory.make_StaticIPAddress(user=self.logged_in_user))
        response = self.client.get(reverse('ipaddresses_handler'))
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        parsed_result = json_load_bytes(response.content)
        expected = [
            addr.ip for addr in
            sorted(addrs, key=lambda addr: getattr(addr, "id"))]
        observed = [result['ip'] for result in parsed_result]
        self.assertEqual(expected, observed)

    def test_POST_release_deallocates_address(self):
        ipaddress = factory.make_StaticIPAddress(
            alloc_type=IPADDRESS_TYPE.USER_RESERVED, user=self.logged_in_user)
        response = self.post_release_request(ipaddress.ip)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        self.assertIsNone(reload_object(ipaddress))

    def test_POST_release_deletes_unknown_interface(self):
        subnet = factory.make_Subnet()
        unknown_nic = factory.make_Interface(INTERFACE_TYPE.UNKNOWN)
        ipaddress = unknown_nic.link_subnet(
            INTERFACE_LINK_TYPE.STATIC, subnet,
            alloc_type=IPADDRESS_TYPE.USER_RESERVED, user=self.logged_in_user)

        self.post_release_request(ipaddress.ip)
        self.assertIsNone(reload_object(unknown_nic))

    def test_POST_release_does_not_delete_interfaces_linked_to_nodes(self):
        node = factory.make_Node()
        attached_nic = factory.make_Interface(node=node)
        subnet = factory.make_Subnet()
        ipaddress = attached_nic.link_subnet(
            INTERFACE_LINK_TYPE.STATIC, subnet,
            alloc_type=IPADDRESS_TYPE.USER_RESERVED, user=self.logged_in_user)

        self.post_release_request(ipaddress.ip)
        self.assertEqual(attached_nic, reload_object(attached_nic))

    def test_POST_release_does_not_delete_IP_that_I_dont_own(self):
        ipaddress = factory.make_StaticIPAddress(user=factory.make_User())
        response = self.post_release_request(ipaddress.ip)
        self.assertEqual(
            http.client.BAD_REQUEST, response.status_code, response.content)

    def test_POST_release_does_not_delete_other_IPs_I_own(self):
        ipaddress = factory.make_StaticIPAddress(
            alloc_type=IPADDRESS_TYPE.USER_RESERVED, user=self.logged_in_user)
        other_address = factory.make_StaticIPAddress(
            alloc_type=IPADDRESS_TYPE.USER_RESERVED, user=self.logged_in_user)
        response = self.post_release_request(ipaddress.ip)
        self.assertEqual(
            http.client.OK, response.status_code, response.content)
        self.assertIsNotNone(reload_object(other_address))
