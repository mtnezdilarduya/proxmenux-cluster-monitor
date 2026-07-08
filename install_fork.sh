#!/usr/bin/env bash
# ==========================================================================
#  ProxMenux Cluster Monitor — EXPERIMENTAL FORK installer
# --------------------------------------------------------------------------
#  Unofficial, unsupported fork of MacRimi/ProxMenux used ONLY to test a
#  zero-config multi-node cluster overview. It installs SIDE BY SIDE with an
#  official ProxMenux Monitor:
#
#    * separate service  : proxmenux-monitor-fork.service   (original: proxmenux-monitor.service)
#    * separate directory: /usr/local/share/proxmenux-fork  (original: /usr/local/share/proxmenux)
#    * separate port     : 38008                            (original: 8008)
#
#  The original install is NEVER touched. To remove the fork:
#      bash install_fork.sh --uninstall
#
#  Not for production. Go use the real thing: https://github.com/MacRimi/ProxMenux
# ==========================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
FORK_NAME="proxmenux-monitor-fork"
INSTALL_DIR="/usr/local/share/proxmenux-fork"
RUNTIME_DIR="$INSTALL_DIR/monitor-app"
SERVICE_FILE="/etc/systemd/system/${FORK_NAME}.service"
LISTEN_PORT="${PROXMENUX_LISTEN_PORT:-38008}"
ASSET_NAME="ProxMenux-Cluster-Fork.AppImage"
APPIMAGE_URL="${PROXMENUX_FORK_APPIMAGE_URL:-https://github.com/mtnezdilarduya/proxmenux-cluster-monitor/releases/latest/download/${ASSET_NAME}}"
APPIMAGE_PATH="$INSTALL_DIR/$ASSET_NAME"

# TEMPORARY firewall rule — tied to the TEMPORARY side-by-side port 38008.
# This exists only so the fork is reachable (UI + node-to-node cluster
# fan-out) while it runs next to the official monitor on 8008. It is scoped
# to $LISTEN_PORT and tagged so `--uninstall` can remove exactly this rule.
# When the fork goes back to 8008 (the real port), this whole block is moot
# and must be dropped along with the port change.
HOST_FW="/etc/pve/local/host.fw"
FW_RULE_TAG="ProxMenux FORK (TEMP port ${LISTEN_PORT} - remove via install_fork.sh --uninstall)"
FW_RULE_LINE="IN ACCEPT -p tcp -dport ${LISTEN_PORT} -log nolog # ${FW_RULE_TAG}"

# ── Colours ───────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    RD="\033[01;31m"; GN="\033[1;92m"; YW="\033[33m"; BL="\033[36m"; CL="\033[0m"
else
    RD=""; GN=""; YW=""; BL=""; CL=""
fi
info()  { echo -e "${BL}ℹ ${CL}$*"; }
ok()    { echo -e "${GN}✓ ${CL}$*"; }
warn()  { echo -e "${YW}⚠ ${CL}$*"; }
die()   { echo -e "${RD}✗ ${CL}$*" >&2; exit 1; }

# ── Preconditions ─────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "This installer must run as root (try: sudo bash install_fork.sh)"

fetch() {  # fetch <url> <dest>
    if command -v wget >/dev/null 2>&1; then
        wget -qO "$2" "$1"
    elif command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$2" "$1"
    else
        die "Neither wget nor curl is available."
    fi
}

# ── TEMPORARY firewall rule (tied to the TEMPORARY port ${LISTEN_PORT}) ────
# Opens ${LISTEN_PORT}/tcp in the Proxmox host firewall so the fork is
# reachable and its cluster fan-out can hit peer nodes. Idempotent, tagged,
# and paired with remove_fw_rule() for clean uninstall. Only meaningful
# while we run on the temporary side-by-side port — drop it when reverting
# to 8008.
add_fw_rule() {
    command -v pve-firewall >/dev/null 2>&1 || { info "No pve-firewall found; skipping firewall rule."; return 0; }
    mkdir -p "$(dirname "$HOST_FW")" 2>/dev/null || true

    if [ -f "$HOST_FW" ] && grep -qF "$FW_RULE_TAG" "$HOST_FW"; then
        ok "Firewall rule for ${LISTEN_PORT}/tcp already present."
        return 0
    fi

    if [ -f "$HOST_FW" ] && grep -q '^\[RULES\]' "$HOST_FW"; then
        # Insert right after the [RULES] header.
        awk -v rule="$FW_RULE_LINE" '
            {print}
            !done && /^\[RULES\]/ {print rule; done=1}
        ' "$HOST_FW" > "${HOST_FW}.tmp" && mv "${HOST_FW}.tmp" "$HOST_FW"
    else
        # No [RULES] section yet — append one.
        { [ -f "$HOST_FW" ] && [ -n "$(tail -c1 "$HOST_FW" 2>/dev/null)" ] && echo ""; \
          echo "[RULES]"; echo "$FW_RULE_LINE"; } >> "$HOST_FW"
    fi

    if pve-firewall reload >/dev/null 2>&1; then
        ok "Firewall rule added (TEMP): ${LISTEN_PORT}/tcp allowed for the fork."
    else
        warn "Rule written to $HOST_FW but 'pve-firewall reload' failed — reload manually."
    fi
}

remove_fw_rule() {
    [ -f "$HOST_FW" ] || return 0
    grep -qF "$FW_RULE_TAG" "$HOST_FW" || return 0
    grep -vF "$FW_RULE_TAG" "$HOST_FW" > "${HOST_FW}.tmp" && mv "${HOST_FW}.tmp" "$HOST_FW"
    command -v pve-firewall >/dev/null 2>&1 && pve-firewall reload >/dev/null 2>&1 || true
    ok "Temporary firewall rule for ${LISTEN_PORT}/tcp removed."
}

# ── Uninstall ─────────────────────────────────────────────────────────────
uninstall_fork() {
    warn "Removing the EXPERIMENTAL fork (the official monitor is left untouched)…"
    if systemctl list-unit-files 2>/dev/null | grep -q "^${FORK_NAME}.service"; then
        systemctl stop "${FORK_NAME}.service" 2>/dev/null || true
        systemctl disable "${FORK_NAME}.service" 2>/dev/null || true
    fi
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    remove_fw_rule   # drop the TEMPORARY ${LISTEN_PORT}/tcp rule this installer added
    ok "Fork removed. The official proxmenux-monitor.service (if any) was not modified."
    exit 0
}

[ "${1:-}" = "--uninstall" ] && uninstall_fork

# ── Banner ────────────────────────────────────────────────────────────────
echo -e "${YW}"
echo "┌──────────────────────────────────────────────────────────────────┐"
echo "│  ⚠  EXPERIMENTAL, UNOFFICIAL ProxMenux fork — NOT FOR PRODUCTION  │"
echo "│     Installs side by side with the real monitor, on port ${LISTEN_PORT}.   │"
echo "│     Removes cleanly with:  bash install_fork.sh --uninstall       │"
echo "└──────────────────────────────────────────────────────────────────┘"
echo -e "${CL}"

# ── Guard: don't clobber the official install ─────────────────────────────
if [ "$INSTALL_DIR" = "/usr/local/share/proxmenux" ] || [ "$FORK_NAME" = "proxmenux-monitor" ]; then
    die "Refusing to run: fork paths collide with the official install."
fi

# ── Download AppImage ─────────────────────────────────────────────────────
info "Preparing $INSTALL_DIR …"
mkdir -p "$INSTALL_DIR"

info "Downloading fork AppImage…"
info "  $APPIMAGE_URL"
fetch "$APPIMAGE_URL" "$APPIMAGE_PATH" \
    || die "Download failed. Is the release published? Override with PROXMENUX_FORK_APPIMAGE_URL=<url>."
[ -s "$APPIMAGE_PATH" ] || die "Downloaded AppImage is empty."
chmod +x "$APPIMAGE_PATH"
ok "AppImage downloaded."

# ── Extract squashfs (no FUSE mount; avoids rkhunter/Wazuh false positives)
info "Extracting runtime…"
TMP_EXTRACT="$(mktemp -d /tmp/proxmenux-fork-extract.XXXXXX)"
trap 'rm -rf "$TMP_EXTRACT"' EXIT
( cd "$TMP_EXTRACT" && "$APPIMAGE_PATH" --appimage-extract >/dev/null 2>&1 ) \
    || die "Failed to extract AppImage."
[ -x "$TMP_EXTRACT/squashfs-root/AppRun" ] || die "Extracted AppImage missing AppRun."

if systemctl is-active --quiet "${FORK_NAME}.service" 2>/dev/null; then
    systemctl stop "${FORK_NAME}.service" || true
fi
rm -rf "${RUNTIME_DIR}.old"
[ -d "$RUNTIME_DIR" ] && mv "$RUNTIME_DIR" "${RUNTIME_DIR}.old"
mv "$TMP_EXTRACT/squashfs-root" "$RUNTIME_DIR"
rm -rf "${RUNTIME_DIR}.old"
ok "Runtime extracted to $RUNTIME_DIR."

# ── systemd service (isolated from the official one) ──────────────────────
info "Installing systemd service ${FORK_NAME}.service…"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ProxMenux Monitor — EXPERIMENTAL cluster fork (port ${LISTEN_PORT})
After=network.target
Before=shutdown.target reboot.target halt.target
Conflicts=shutdown.target reboot.target halt.target

[Service]
Type=simple
User=root
WorkingDirectory=$RUNTIME_DIR
ExecStart=$RUNTIME_DIR/AppRun
Environment="PROXMENUX_LISTEN_PORT=${LISTEN_PORT}"
Environment="PROXMENUX_API_PORT=${LISTEN_PORT}"
Restart=on-failure
RestartSec=10
TimeoutStopSec=45
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${FORK_NAME}.service" >/dev/null 2>&1 || true
systemctl restart "${FORK_NAME}.service"
sleep 3

# ── Report ────────────────────────────────────────────────────────────────
if systemctl is-active --quiet "${FORK_NAME}.service"; then
    # Open the TEMPORARY port ${LISTEN_PORT} in the host firewall so the UI and
    # the node-to-node cluster fan-out are reachable. Tagged + reverted on
    # --uninstall. This is only needed because of the temporary side-by-side
    # port; it goes away when the fork returns to 8008.
    add_fw_rule

    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo
    ok "Fork monitor is running."
    echo -e "   ${BL}→${CL} http://${IP:-<node-ip>}:${LISTEN_PORT}"
    echo -e "   ${BL}→${CL} The official monitor (if installed) is still on :8008, untouched."
else
    die "Service failed to start. Inspect: journalctl -u ${FORK_NAME} -n 50 --no-pager"
fi
