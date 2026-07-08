"""
Flask routes for the zero-config cluster overview.

  GET /api/cluster/status    -> membership + quorum (cheap; reads .members)
  GET /api/cluster/overview  -> aggregated CPU/mem/VM view across all nodes

Both are user-facing and protected by the normal auth (@require_auth).
The aggregation itself reaches peer nodes' existing endpoints using the
shared cluster token (see cluster_manager + the X-Cluster-Token branch in
jwt_middleware.require_auth), so no per-endpoint changes are needed.
"""

from flask import Blueprint, jsonify

import cluster_manager
from jwt_middleware import require_auth

cluster_bp = Blueprint("cluster", __name__)


@cluster_bp.route("/api/cluster/status", methods=["GET"])
@require_auth
def cluster_status():
    """Lightweight membership/quorum info (no peer fan-out)."""
    try:
        members = cluster_manager.read_members()
        return jsonify({
            "in_cluster": members["in_cluster"],
            "cluster_name": members["cluster_name"],
            "quorate": members["quorate"],
            "local_node": members["local_node"],
            "nodes_total": len(members["nodes"]),
            "nodes_online": sum(1 for n in members["nodes"] if n["online"]),
            "nodes": members["nodes"],
        })
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@cluster_bp.route("/api/cluster/overview", methods=["GET"])
@require_auth
def cluster_overview():
    """Aggregated cluster view: totals + per-node resource usage."""
    try:
        return jsonify(cluster_manager.build_overview())
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@cluster_bp.route("/api/cluster/vms", methods=["GET"])
@require_auth
def cluster_vms():
    """Cluster-wide VM/LXC list — every guest on every node, each tagged
    with its ``node``.

    This is the aggregated counterpart of the stock ``/api/vms`` (which
    filters to the local node). No peer fan-out is needed: Proxmox's
    ``pvesh get /cluster/resources --type vm`` is already cluster-wide, so
    we reuse the same cached payload that ``/api/vms`` uses and simply keep
    every node's guests, adding the ``node`` field the single-node endpoint
    drops. Helpers are imported lazily to avoid a circular import (this
    blueprint is imported by flask_server at startup).
    """
    try:
        from flask_server import (
            get_cached_pvesh_cluster_resources_vm,
            _get_lxc_update_status_map,
        )

        resources = get_cached_pvesh_cluster_resources_vm() or []
        try:
            lxc_updates_map = _get_lxc_update_status_map()
        except Exception:  # noqa: BLE001
            lxc_updates_map = {}

        vms = []
        for resource in resources:
            vm_type = "lxc" if resource.get("type") == "lxc" else "qemu"
            vm_data = {
                "vmid": resource.get("vmid"),
                "name": resource.get("name", f"VM-{resource.get('vmid')}"),
                "status": resource.get("status", "unknown"),
                "type": vm_type,
                "node": resource.get("node", ""),
                "cpu": resource.get("cpu", 0),
                "mem": resource.get("mem", 0),
                "maxmem": resource.get("maxmem", 0),
                "disk": resource.get("disk", 0),
                "maxdisk": resource.get("maxdisk", 0),
                "uptime": resource.get("uptime", 0),
                "netin": resource.get("netin", 0),
                "netout": resource.get("netout", 0),
                "diskread": resource.get("diskread", 0),
                "diskwrite": resource.get("diskwrite", 0),
                "maxcpu": resource.get("maxcpu", 0),
            }
            if vm_type == "lxc":
                upd = lxc_updates_map.get(str(resource.get("vmid")))
                if upd is not None:
                    vm_data["update_check"] = upd
            vms.append(vm_data)

        # Stable order: by node, then vmid — keeps the list from reshuffling
        # on every poll (cluster/resources ordering isn't guaranteed).
        vms.sort(key=lambda v: (str(v.get("node") or ""), int(v.get("vmid") or 0)))
        return jsonify(vms)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500
