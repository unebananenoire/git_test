# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""RPC helpers related to chassis."""

__all__ = [
    "discover_chassis",
    ]

from maasserver.rpc import getAllClients
from provisioningserver.rpc.cluster import DiscoverChassis
from provisioningserver.utils.twisted import (
    asynchronous,
    deferWithTimeout,
    FOREVER,
)
from twisted.internet.defer import DeferredList


@asynchronous(timeout=FOREVER)
def discover_chassis(
        chassis_type, context, system_id=None, hostname=None, timeout=120):
    """Discover a chassis.

    :param chassis_type: Type of chassis to discover.
    :param context: Chassis driver information to connect to chassis.
    :param system_id: ID of the chassis in the database (None if new chassis).
    :param hostname: Hostname of the chassis in the database (None if
        new chassis).

    :returns: Return a tuple with mapping of rack controller system_id and the
        discovered chassis information and a mapping of rack controller
        system_id and the failure exception.
    """
    def discover(client):
        return deferWithTimeout(
            timeout, client, DiscoverChassis, chassis_type=chassis_type,
            context=context, system_id=system_id, hostname=hostname)

    clients = getAllClients()
    dl = DeferredList(map(discover, clients), consumeErrors=True)

    def cb_results(results):
        discovered, failures = {}, {}
        for client, (success, result) in zip(clients, results):
            if success:
                discovered[client.ident] = result["chassis"]
            else:
                failures[client.ident] = result.value
        return discovered, failures

    return dl.addCallback(cb_results)
