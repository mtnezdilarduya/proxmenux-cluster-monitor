"""
Cluster manager — zero-config multi-node aggregation for ProxMenux Monitor.

Design goals (mirrors the single-node "install and forget" philosophy):

  * NO manual configuration of peer IPs or credentials. Peers are
    auto-discovered by reading ``/etc/pve/.members`` — a JSON file that
    pmxcfs keeps in sync across every node of a Proxmox cluster.
  * Node-to-node trust with zero setup: a shared token is stored under
    ``/etc/pve/`` which pmxcfs replicates cluster-wide automatically, so
    every node accepts calls from every other node without the operator
    ever typing a secret.

The node whose dashboard you are browsing acts as the aggregator: it
fans out to each *online* peer's existing REST API (``:8008``) using the
shared token, then merges the per-node payloads into one cluster view.
The per-node views are untouched and remain the fallback.

Everything here degrades gracefully:
  * not in a cluster / single node  -> overview with just this node
  * a peer is offline / unreachable -> that node is marked unreachable
    but never breaks the whole response

Dev/testing overrides (so this can run off a real Proxmox node):
  * PROXMENUX_MEMBERS_FILE       -> path to a mock ``.members`` JSON
  * PROXMENUX_CLUSTER_TOKEN_FILE -> path to the shared token file
  * PROXMENUX_API_PORT           -> peer API port (default 8008)
"""

import os
import json
import time
import socket
import secrets
import logging

logger = logging.getLogger("proxmenux.cluster")

# ── Paths & constants ────────────────────────────────────────────────────
MEMBERS_FILE = os.environ.get("PROXMENUX_MEMBERS_FILE", "/etc/pve/.members")
TOKEN_FILE = os.environ.get(
    "PROXMENUX_CLUSTER_TOKEN_FILE", "/etc/pve/proxmenux/cluster_token"
)
API_PORT = int(os.environ.get("PROXMENUX_API_PORT", "8008"))

# Per-peer HTTP timeout. Generous but bounded — an unreachable node must
# never stall the whole aggregation. The aggregator queries peers in
# parallel, so total latency ~= the slowest single peer, not the sum.
PEER_TIMEOUT_S = 4.0

# Short cache for the members file to avoid re-reading /etc/pve on every
# request burst. pmxcfs is fast but this is called from a hot path.
_members_cache = {"ts": 0.0, "data": None}
_MEMBERS_TTL_S = 5.0


# ── Peer discovery ───────────────────────────────────────────────────────
def read_members(force=False):
    """Parse ``/etc/pve/.members`` and return a normalized dict.

    Returns::

        {
          "in_cluster": bool,
          "cluster_name": str | None,
          "quorate": bool,
          "local_node": str,
          "nodes": [
            {"name": str, "id": int, "ip": str, "online": bool, "local": bool},
            ...
          ],
        }

    A missing/malformed file (single node without a cluster, or a dev
    box) yields a valid single-node structure instead of raising.
    """
    now = time.time()
    if not force and _members_cache["data"] is not None:
        if now - _members_cache["ts"] < _MEMBERS_TTL_S:
            return _members_cache["data"]

    local_node = socket.gethostname()
    result = {
        "in_cluster": False,
        "cluster_name": None,
        "quorate": True,
        "local_node": local_node,
        "nodes": [],
    }

    try:
        with open(MEMBERS_FILE, "r") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.debug("read_members: no usable .members (%s) — single node", exc)
        result["nodes"] = [
            {"name": local_node, "id": 1, "ip": "127.0.0.1",
             "online": True, "local": True}
        ]
        _members_cache.update(ts=now, data=result)
        return result

    local_node = raw.get("nodename", local_node)
    result["local_node"] = local_node

    cluster = raw.get("cluster") or {}
    if cluster:
        result["in_cluster"] = True
        result["cluster_name"] = cluster.get("name")
        result["quorate"] = bool(cluster.get("quorate", 0))

    nodelist = raw.get("nodelist") or {}
    nodes = []
    for name, info in nodelist.items():
        nodes.append({
            "name": name,
            "id": info.get("id"),
            "ip": info.get("ip"),
            "online": bool(info.get("online", 0)),
            "local": name == local_node,
        })

    if not nodes:
        nodes = [{"name": local_node, "id": 1, "ip": "127.0.0.1",
                  "online": True, "local": True}]
        result["in_cluster"] = False

    nodes.sort(key=lambda n: (n.get("id") or 0, n["name"]))
    result["nodes"] = nodes
    _members_cache.update(ts=now, data=result)
    return result


# ── Shared cluster token ─────────────────────────────────────────────────
def get_cluster_token():
    """Return the shared node-to-node token, generating it on first use.

    Stored under ``/etc/pve/`` so pmxcfs replicates it to every node.
    The first node to call this creates it; all others read the same
    value moments later. Falls back to an in-memory token if the path
    is not writable (dev box) so callers never crash.
    """
    try:
        with open(TOKEN_FILE, "r") as fh:
            tok = fh.read().strip()
            if tok:
                return tok
    except (FileNotFoundError, OSError):
        pass

    tok = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        # Write atomically-ish; pmxcfs does not support os.replace across
        # some ops, so a direct write with restrictive mode is fine here.
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(tok)
        # Re-read in case another node won the race and wrote first.
        with open(TOKEN_FILE, "r") as fh:
            disk = fh.read().strip()
            if disk:
                return disk
    except OSError as exc:
        logger.warning("get_cluster_token: cannot persist token (%s) — "
                       "using ephemeral token", exc)
    return tok


def is_valid_cluster_token(token):
    """Constant-time comparison of a presented token against the shared one."""
    if not token:
        return False
    try:
        return secrets.compare_digest(str(token), get_cluster_token())
    except Exception:
        return False


# ── Peer fan-out ─────────────────────────────────────────────────────────
def _fetch_peer(node, endpoint, token):
    """GET ``endpoint`` from a single peer. Returns (node_name, data|None, err)."""
    import requests  # gevent-patched; cooperative

    url = f"http://{node['ip']}:{API_PORT}{endpoint}"
    try:
        resp = requests.get(
            url,
            headers={"X-Cluster-Token": token},
            timeout=PEER_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return node["name"], None, f"HTTP {resp.status_code}"
        return node["name"], resp.json(), None
    except Exception as exc:  # noqa: BLE001 — a bad peer must not break the view
        return node["name"], None, str(exc)


def fetch_all(endpoint):
    """Fan out ``endpoint`` to every online node in parallel.

    Returns a dict ``{node_name: {"data": ..., "error": ...}}``. Uses
    gevent greenlets when available (the Flask server runs under gevent),
    otherwise falls back to a bounded thread pool.
    """
    members = read_members()
    token = get_cluster_token()
    online = [n for n in members["nodes"] if n["online"]]

    results = {}

    try:
        import gevent
        jobs = [gevent.spawn(_fetch_peer, n, endpoint, token) for n in online]
        gevent.joinall(jobs, timeout=PEER_TIMEOUT_S + 1)
        for n, job in zip(online, jobs):
            if job.ready() and job.value:
                name, data, err = job.value
            else:
                name, data, err = n["name"], None, "timeout"
            results[name] = {"data": data, "error": err}
    except ImportError:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, len(online))) as pool:
            for name, data, err in pool.map(
                lambda n: _fetch_peer(n, endpoint, token), online
            ):
                results[name] = {"data": data, "error": err}

    # Offline nodes are reported too, so the UI can show them as down.
    for n in members["nodes"]:
        if not n["online"]:
            results[n["name"]] = {"data": None, "error": "offline"}
    return results


# ── Aggregation (pure, unit-testable) ────────────────────────────────────
def aggregate_overview(members, system_results, vms_results=None):
    """Merge per-node payloads into a single cluster overview.

    Pure function: no I/O. ``system_results``/``vms_results`` are the
    dicts returned by :func:`fetch_all` for ``/api/system`` and
    ``/api/vms``. Weighted CPU average uses each node's thread count so a
    big node counts more than a tiny one.
    """
    vms_results = vms_results or {}
    nodes_out = []
    tot_mem_total = tot_mem_used = 0.0
    cpu_weighted_sum = cpu_weight = 0.0
    tot_cores = tot_threads = 0
    vms_running = vms_total = lxc_running = lxc_total = 0
    online_count = 0

    for node in members["nodes"]:
        name = node["name"]
        sysr = system_results.get(name, {})
        data = sysr.get("data")
        entry = {
            "name": name,
            "id": node.get("id"),
            "ip": node.get("ip"),
            "local": node.get("local", False),
            "online": node.get("online", False),
            "reachable": data is not None,
            "error": sysr.get("error"),
        }

        if data:
            online_count += 1
            threads = data.get("cpu_threads") or 0
            cores = data.get("cpu_cores") or 0
            cpu = data.get("cpu_usage") or 0
            mem_total = data.get("memory_total") or 0
            mem_used = data.get("memory_used") or 0

            cpu_weighted_sum += cpu * (threads or 1)
            cpu_weight += (threads or 1)
            tot_cores += cores
            tot_threads += threads
            tot_mem_total += mem_total
            tot_mem_used += mem_used

            entry.update({
                "cpu_usage": cpu,
                "memory_usage": data.get("memory_usage"),
                "memory_total": mem_total,
                "memory_used": mem_used,
                "temperature": data.get("temperature"),
                "uptime": data.get("uptime"),
                "load_average": data.get("load_average"),
                "cpu_cores": cores,
                "cpu_threads": threads,
                "proxmox_version": data.get("proxmox_version"),
                "kernel_version": data.get("kernel_version"),
            })

            # Per-node VM/LXC rollup, if that node answered /api/vms.
            vmr = (vms_results.get(name) or {}).get("data")
            if isinstance(vmr, list):
                n_vm_run = n_vm = n_lxc_run = n_lxc = 0
                for guest in vmr:
                    is_lxc = (guest.get("type") == "lxc")
                    running = (guest.get("status") == "running")
                    if is_lxc:
                        n_lxc += 1
                        n_lxc_run += running
                    else:
                        n_vm += 1
                        n_vm_run += running
                entry["vms"] = {"running": n_vm_run, "total": n_vm}
                entry["lxc"] = {"running": n_lxc_run, "total": n_lxc}
                vms_running += n_vm_run
                vms_total += n_vm
                lxc_running += n_lxc_run
                lxc_total += n_lxc

        nodes_out.append(entry)

    cpu_avg = round(cpu_weighted_sum / cpu_weight, 1) if cpu_weight else 0.0

    return {
        "cluster": {
            "name": members.get("cluster_name"),
            "in_cluster": members.get("in_cluster", False),
            "quorate": members.get("quorate", True),
            "nodes_total": len(members["nodes"]),
            "nodes_online": online_count,
            "local_node": members.get("local_node"),
        },
        "totals": {
            "cpu_usage_avg": cpu_avg,
            "cpu_cores": tot_cores,
            "cpu_threads": tot_threads,
            "memory_total": round(tot_mem_total, 1),
            "memory_used": round(tot_mem_used, 1),
            "memory_usage": (
                round(tot_mem_used / tot_mem_total * 100, 1)
                if tot_mem_total else 0.0
            ),
            "vms": {"running": vms_running, "total": vms_total},
            "lxc": {"running": lxc_running, "total": lxc_total},
        },
        "nodes": nodes_out,
    }


def build_overview():
    """Full cluster overview: discover peers, fan out, aggregate."""
    members = read_members()
    system_results = fetch_all("/api/system")
    vms_results = fetch_all("/api/vms")
    return aggregate_overview(members, system_results, vms_results)
