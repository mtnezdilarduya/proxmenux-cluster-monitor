# ProxMenux Cluster Monitor — EXPERIMENTAL FORK (dev notes)

Unofficial, throwaway fork of **[MacRimi/ProxMenux](https://github.com/MacRimi/ProxMenux)**
(GPL-3.0) to prototype a **zero-config multi-node cluster overview**. Repo:
`mtnezdilarduya/proxmenux-cluster-monitor` (public). Working branch:
`feat/cluster-overview` (remote `private`).

> Read `AppImage/` docs / upstream conventions before touching Next.js. Always
> read a file before editing it.

## Coexistence & the TEMPORARY port 38008

The fork runs **side by side** with the official monitor:
- service `proxmenux-monitor-fork.service` (vs `proxmenux-monitor.service`)
- dir `/usr/local/share/proxmenux-fork` (vs `/usr/local/share/proxmenux`)
- **port `38008`** (vs `8008`) — **TEMPORARY**, must revert to `8008` before any
  real release. Marked `TEMP` in every touch site:
  - `AppImage/scripts/flask_server.py` → `LISTEN_PORT` (env `PROXMENUX_LISTEN_PORT`)
  - `AppImage/scripts/cluster_manager.py` → `API_PORT` (env `PROXMENUX_API_PORT`)
  - `AppImage/lib/api-config.ts` → `API_PORT` default (env `NEXT_PUBLIC_API_PORT`)
    — critical: `getApiBaseUrl()` builds `${protocol}//${hostname}:${API_PORT}`.
  - `install_fork.sh` firewall rule (opens 38008/tcp, tagged, reverted on uninstall).

## Install (one-liner, per node — needs it on every node)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/mtnezdilarduya/proxmenux-cluster-monitor/feat/cluster-overview/install_fork.sh)"
```
Uninstall: `bash install_fork.sh --uninstall` (removes service, dir, fw rule; never
touches the official install). Overridable: `PROXMENUX_FORK_APPIMAGE_URL`,
`PROXMENUX_LISTEN_PORT`. Downloads the AppImage from GitHub Release
`v0.1.0-cluster-experimental`, asset `ProxMenux-Cluster-Fork.AppImage`, extracts
squashfs (`--appimage-extract`, no FUSE → avoids rkhunter/Wazuh false positives).

## Zero-config cluster mechanism

- Peers discovered from `/etc/pve/.members` (pmxcfs-replicated). No IPs configured.
- Shared token in `/etc/pve/proxmenux/cluster_token` (cluster-replicated) sent as
  `X-Cluster-Token`; accepted by `jwt_middleware.require_auth`.
- **Key insight:** `pvesh get /cluster/resources --type vm --output-format json` is
  already **cluster-wide** (each row has a `node` field) and callable from any node
  → guest/storage aggregation needs **no fan-out**. Likewise `pvesh get
  /nodes/<any-node>/qemu/<vmid>/...` routes cluster-wide, so per-guest ops only need
  the guest's real node in the path.

## Design split (per-tab consolidation plan)

- **Group A — aggregate** (list everything, tag by node): **VMs & LXCs**, Storage.
- **Group B — per-node selector** (pick a node, load its data): Hardware, Network,
  System Logs, Security, Settings, Terminal.
- **Terminal deferred** (WebSocket proxying) → stays local for now.

## Backend node-awareness

`AppImage/scripts/flask_server.py`:
- `_resolve_guest_node(vmid)` — maps a vmid to its node via the cached
  `/cluster/resources` payload (fallback: local node name).
- Used by `get_vm_config` (detail) and `api_vm_metrics`. `api_vm_control` already
  resolved node from `vm_info.get('node')`. `get_proxmox_vms()` still local-only
  (backs stock `/api/vms`).

`AppImage/scripts/flask_cluster_routes.py` (blueprint `cluster_bp`):
- `/api/cluster/status`, `/api/cluster/overview`, **`/api/cluster/vms`** (Phase 1a:
  cluster-wide guest list; reuses cached `/cluster/resources`, keeps every node's
  guests + `node` field; lazy import of `flask_server` helpers to dodge circular
  import; stable sort by (node, vmid)).

Frontend `AppImage/components/virtual-machines.tsx`:
- SWR key `"/api/cluster/vms"`; `VMData.node`; `nodeFilter` state + `nodesInData` /
  `displayVMData` memos; node-filter `<Select>` (shown only if >1 node); purple Node
  badge (desktop row + mobile). Summary cards stay cluster-wide (`safeVMData`).

UI markers (`AppImage/components/proxmox-dashboard.tsx`): amber `cluster-fork` badge
by the title + footer `v1.2.2.1-beta · cluster-fork (experimental)`.

## Build / release

- Rebuild: `AppImage/scripts/build_appimage.sh` (bundles `cluster_manager.py` +
  `flask_cluster_routes.py` by explicit `cp`; requests/gevent already bundled).
  `next build` = `npm run export`.
- **Disk is tight (`/dev/sda1`).** Free space before each build:
  `npm cache clean --force`, `pip3 cache purge`, `rm -rf AppImage/.next
  /tmp/proxmenux_build`.
- Build byproducts to revert after each run: `git checkout -- AppImage/package-lock.json
  AppImage/tsconfig.json`; delete stray `=X.Y.Z` files (upstream unquoted
  `pip install pkg>=ver` bug) and `build.log`.
- Upload asset to release `v0.1.0-cluster-experimental` via `gh release upload
  ... --clobber`; verify `latest/download` serves the new sha256.

## Phase status

- ✅ **Phase 1a — VMs & LXCs consolidated** (list + node badge + filter + node-aware
  detail/metrics/control). Deployed to release. Commit `e38c5da0`.
- ⏳ **Phase 1b** — make remaining per-guest endpoints node-aware via
  `_resolve_guest_node()`: `/api/vms/<id>/logs`, `/firewall/log`, `/backups` +
  `/backup`, `/description`.
- ⏳ **Phase 2** — single-node proxy primitive `GET /api/cluster/node/<node>/<path>`
  + node selector; pilot on a Group-B tab (Hardware).
- ⏳ **Phase 3** — aggregate Storage (Group A); per-node selector on
  Network/Logs/Security/Settings (Group B). Terminal last.

## Gotchas

- Vercel/60s and Doppler notes belong to the *porra* project, not here.
- `next build` reformats `package-lock.json`/`tsconfig.json` — always a byproduct,
  revert it.
- Do NOT clobber the official install (installer refuses if fork paths collide).
