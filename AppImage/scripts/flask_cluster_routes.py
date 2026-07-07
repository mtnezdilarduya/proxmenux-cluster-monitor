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
