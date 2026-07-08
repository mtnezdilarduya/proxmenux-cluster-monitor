<div align="center">

# ⚠️ EXPERIMENTAL FORK — NOT FOR PRODUCTION ⚠️

</div>

> [!CAUTION]
> **This is an unofficial, experimental fork. Do not use it.**
>
> - It is **not** affiliated with, endorsed by, or supported by the original **ProxMenux** project or its author.
> - It exists **only** to prototype and test one feature (a multi-node cluster overview) against a real Proxmox cluster.
> - It is **incomplete, unstable, and may break, hang, or misbehave** on your nodes.
> - It ships a **temporary port change (`38008` instead of `8008`)** so it can run *side by side* with the real monitor for comparison — this is **not** a supported configuration.
> - There is **no support, no warranty, and no guarantee of updates.** Issues and PRs here may be ignored.
>
> **If you actually want ProxMenux, install the real thing instead:**
> 👉 **https://github.com/MacRimi/ProxMenux** · **https://proxmenux.com**

---

## What is this?

A personal, throwaway fork of **[ProxMenux Monitor](https://github.com/MacRimi/ProxMenux)** (the `AppImage/` web dashboard) used to prototype a **zero-config, multi-node cluster overview**:

- A new **"Cluster"** tab that aggregates every node of a Proxmox cluster into a single view — total CPU (thread-weighted), memory, VM/LXC rollup, and per-node cards — with **no IPs or credentials to configure**.
- The backend of the node you're browsing auto-discovers its peers from `/etc/pve/.members` (replicated by pmxcfs) and fans out to each peer's existing API using a shared token stored under `/etc/pve/proxmenux/` (also cluster-replicated). Nothing to set up by hand.

This is a **prototype**. The upstream project is the real, maintained, supported product.

## Why it runs on port 38008

During development this fork **temporarily** binds `38008` (overridable via `PROXMENUX_LISTEN_PORT`) so it can coexist with an official ProxMenux Monitor still running on `8008`, for real-time comparison. **This is a temporary testing decision and would be reverted to `8008` before anything real.**

## Credit & license

- Original work: **ProxMenux** by **[MacRimi](https://github.com/MacRimi)** and contributors — © 2024–2025.
- Licensed under **GPL-3.0** (see [`LICENSE`](./LICENSE)). This fork inherits the same license.
- All credit for the underlying monitor goes to the upstream authors. The cluster-overview experiment is the only meaningful difference here.

---

<div align="center">
<sub>Seriously — go use <a href="https://github.com/MacRimi/ProxMenux">the real ProxMenux</a>.</sub>
</div>
