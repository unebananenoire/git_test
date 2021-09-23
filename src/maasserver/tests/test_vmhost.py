# Copyright 2021 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


import random

from twisted.internet.defer import succeed

from maasserver import vmhost as vmhost_module
from maasserver.enum import BMC_TYPE
from maasserver.exceptions import PodProblem
from maasserver.testing.factory import factory
from maasserver.testing.testcase import (
    MAASServerTestCase,
    MAASTransactionServerTestCase,
)
from maasserver.utils.threads import deferToDatabase
from maastesting.crochet import wait_for
from provisioningserver.drivers.pod import (
    DiscoveredPod,
    DiscoveredPodHints,
    DiscoveredPodStoragePool,
)


def make_pod_info():
    pod_ip_adddress = factory.make_ipv4_address()
    pod_power_address = "qemu+ssh://user@%s/system" % pod_ip_adddress
    return {
        "type": "virsh",
        "power_address": pod_power_address,
        "ip_address": pod_ip_adddress,
    }


def fake_pod_discovery(testcase):
    discovered_pod = DiscoveredPod(
        architectures=["amd64/generic"],
        cores=random.randint(2, 4),
        memory=random.randint(2048, 4096),
        local_storage=random.randint(1024, 1024 * 1024),
        cpu_speed=random.randint(2048, 4048),
        hints=DiscoveredPodHints(
            cores=random.randint(2, 4),
            memory=random.randint(1024, 4096),
            local_storage=random.randint(1024, 1024 * 1024),
            cpu_speed=random.randint(2048, 4048),
        ),
        storage_pools=[
            DiscoveredPodStoragePool(
                id=factory.make_name("pool_id"),
                name=factory.make_name("name"),
                type=factory.make_name("type"),
                path="/var/lib/path/%s" % factory.make_name("path"),
                storage=random.randint(1024, 1024 * 1024),
            )
            for _ in range(3)
        ],
    )
    discovered_rack_1 = factory.make_RackController()
    discovered_rack_2 = factory.make_RackController()
    failed_rack = factory.make_RackController()
    testcase.patch(vmhost_module, "post_commit_do")
    testcase.patch(vmhost_module, "discover_pod").return_value = (
        {
            discovered_rack_1.system_id: discovered_pod,
            discovered_rack_2.system_id: discovered_pod,
        },
        {failed_rack.system_id: factory.make_exception()},
    )
    return (
        discovered_pod,
        [discovered_rack_1, discovered_rack_2],
        [failed_rack],
    )


class TestDiscoverAndSyncVMHost(MAASServerTestCase):
    def test_sync_details(self):
        (
            discovered_pod,
            discovered_racks,
            failed_racks,
        ) = fake_pod_discovery(self)
        zone = factory.make_Zone()
        pod_info = make_pod_info()
        power_parameters = {"power_address": pod_info["power_address"]}
        orig_vmhost = factory.make_Pod(
            zone=zone, pod_type=pod_info["type"], parameters=power_parameters
        )
        vmhost = vmhost_module.discover_and_sync_vmhost(
            orig_vmhost, factory.make_User()
        )
        self.assertEqual(vmhost.id, orig_vmhost.id)
        self.assertEqual(vmhost.bmc_type, BMC_TYPE.POD)
        self.assertEqual(vmhost.architectures, ["amd64/generic"])
        self.assertEqual(vmhost.name, orig_vmhost.name)
        self.assertEqual(vmhost.cores, discovered_pod.cores)
        self.assertEqual(vmhost.memory, discovered_pod.memory)
        self.assertEqual(vmhost.cpu_speed, discovered_pod.cpu_speed)
        self.assertEqual(vmhost.zone, zone)
        self.assertEqual(vmhost.power_type, "virsh")
        self.assertEqual(vmhost.power_parameters, power_parameters)
        self.assertEqual(vmhost.ip_address.ip, pod_info["ip_address"])
        routable_racks = [
            relation.rack_controller
            for relation in vmhost.routable_rack_relationships.all()
            if relation.routable
        ]
        not_routable_racks = [
            relation.rack_controller
            for relation in vmhost.routable_rack_relationships.all()
            if not relation.routable
        ]
        self.assertCountEqual(routable_racks, discovered_racks)
        self.assertCountEqual(not_routable_racks, failed_racks)

    def test_raises_exception_from_rack_controller(self):
        failed_rack = factory.make_RackController()
        exc = factory.make_exception()
        self.patch(vmhost_module, "discover_pod").return_value = (
            {},
            {failed_rack.system_id: exc},
        )
        pod_info = make_pod_info()
        power_parameters = {"power_address": pod_info["power_address"]}
        vmhost = factory.make_Pod(
            pod_type=pod_info["type"],
            parameters=power_parameters,
        )
        error = self.assertRaises(
            PodProblem,
            vmhost_module.discover_and_sync_vmhost,
            vmhost,
            factory.make_User(),
        )
        self.assertEqual(str(exc), str(error))


class TestDiscoverAndSyncVMHostAsync(MAASTransactionServerTestCase):

    wait_for_reactor = wait_for(30)

    @wait_for_reactor
    async def test_sync_details(self):
        discovered_pod, discovered_racks, failed_racks = await deferToDatabase(
            fake_pod_discovery, self
        )
        vmhost_module.discover_pod.return_value = succeed(
            vmhost_module.discover_pod.return_value
        )
        zone = await deferToDatabase(factory.make_Zone)
        pod_info = await deferToDatabase(make_pod_info)
        power_parameters = {"power_address": pod_info["power_address"]}
        orig_vmhost = await deferToDatabase(
            factory.make_Pod,
            zone=zone,
            pod_type=pod_info["type"],
            parameters=power_parameters,
        )
        user = await deferToDatabase(factory.make_User)
        vmhost = await vmhost_module.discover_and_sync_vmhost_async(
            orig_vmhost, user
        )
        self.assertEqual(vmhost.id, orig_vmhost.id)
        self.assertEqual(vmhost.bmc_type, BMC_TYPE.POD)
        self.assertEqual(vmhost.architectures, ["amd64/generic"])
        self.assertEqual(vmhost.name, orig_vmhost.name)
        self.assertEqual(vmhost.cores, discovered_pod.cores)
        self.assertEqual(vmhost.memory, discovered_pod.memory)
        self.assertEqual(vmhost.cpu_speed, discovered_pod.cpu_speed)
        self.assertEqual(vmhost.zone, zone)
        self.assertEqual(vmhost.power_type, "virsh")
        self.assertEqual(vmhost.power_parameters, power_parameters)
        self.assertEqual(vmhost.ip_address.ip, pod_info["ip_address"])

        def validate_rack_routes():
            routable_racks = [
                relation.rack_controller
                for relation in vmhost.routable_rack_relationships.all()
                if relation.routable
            ]
            not_routable_racks = [
                relation.rack_controller
                for relation in vmhost.routable_rack_relationships.all()
                if not relation.routable
            ]
            self.assertCountEqual(routable_racks, discovered_racks)
            self.assertCountEqual(not_routable_racks, failed_racks)

        await deferToDatabase(validate_rack_routes)

    @wait_for_reactor
    async def test_raises_exception_from_rack_controller(self):
        failed_rack = await deferToDatabase(factory.make_RackController)
        exc = factory.make_exception()
        self.patch(vmhost_module, "discover_pod").return_value = succeed(
            ({}, {failed_rack.system_id: exc})
        )
        pod_info = await deferToDatabase(make_pod_info)
        power_parameters = {"power_address": pod_info["power_address"]}
        vmhost = yield deferToDatabase(
            factory.make_Pod,
            pod_type=pod_info["type"],
            parameters=power_parameters,
        )
        user = await deferToDatabase(factory.make_User)
        try:
            await vmhost_module.discover_and_sync_vmhost_async(vmhost, user)
        except Exception as error:
            self.assertIsInstance(error, PodProblem)
            self.assertEqual(str(exc), str(error))
        else:
            self.fail("No exception raised")