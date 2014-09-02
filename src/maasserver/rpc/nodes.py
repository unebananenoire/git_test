# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""RPC helpers relating to nodes."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = [
    "mark_node_failed",
    "update_node_power_state",
]


from maasserver.models import (
    Node,
    NodeGroup,
    )
from maasserver.utils.async import transactional
from provisioningserver.rpc.exceptions import (
    NoSuchCluster,
    NoSuchNode,
    )
from provisioningserver.utils.twisted import synchronous


@synchronous
@transactional
def mark_node_failed(system_id, error_description):
    """Mark a node as failed.

    for :py:class:`~provisioningserver.rpc.region.MarkBroken`.
    """
    try:
        node = Node.objects.get(system_id=system_id)
    except Node.DoesNotExist:
        raise NoSuchNode.from_system_id(system_id)
    node.mark_failed(error_description)


@synchronous
@transactional
def list_cluster_nodes_power_parameters(uuid):
    """Query a cluster controller and return all of its nodes
    power parameters

    for :py:class:`~provisioningserver.rpc.region.ListNodePowerParameters`.
    """
    try:
        nodegroup = NodeGroup.objects.get_by_natural_key(uuid)
    except NodeGroup.DoesNotExist:
        raise NoSuchCluster.from_uuid(uuid)
    else:
        power_info_by_node = (
            (node, node.get_effective_power_info())
            for node in nodegroup.node_set.all()
        )
        return [
            {
                'system_id': node.system_id,
                'hostname': node.hostname,
                'power_state': node.power_state,
                'power_type': power_info.power_type,
                'context': power_info.power_parameters,
            }
            for node, power_info in power_info_by_node
            if power_info.power_type is not None
        ]


@synchronous
@transactional
def update_node_power_state(system_id, power_state):
    """Update a node power state.

    for :py:class:`~provisioningserver.rpc.region.UpdateNodePowerState.
    """
    try:
        node = Node.objects.get(system_id=system_id)
    except Node.DoesNotExist:
        raise NoSuchNode.from_system_id(system_id)
    node.update_power_state(power_state)
