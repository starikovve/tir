#!/usr/bin/env bash
# mlag-onbox-failover.sh - on-box MLAG failover helper for IP Infusion OcNOS.
#
# Runs on the STANDBY node of an MCEC/MLAG domain (OcNOS Linux shell, root).
# Primary signal : local MCEC domain adjacency (read via OcNOS CLI).
# Secondary only : ping to the peer (master) IDP/mgmt address.
#
# Decision matrix (standby node, not in failover):
#   adjacency UP                          -> nothing
#   local MLAG state already ACTIVE       -> nothing (planned CLI reload: standby took over itself)
#   adjacency DOWN + peer answers ping    -> link/IDP problem, log only, stay silent
#   adjacency DOWN + peer silent for FAIL_THRESHOLD checks AND still standby
#                                         -> node considered dead -> disable strict mode
# Ping alone NEVER triggers anything.
#
# Recovery (in failover): adjacency UP and peer pings -> wait RECOVERY_WAIT, recheck,
# re-enable strict mode. Role revert (reload) is NOT automatic unless AUTO_RELOAD=yes.
#
# !!! Verify every CLI command and output pattern below on your OcNOS release in a lab.
# !!! Per OcNOS docs, "mcec strict-active-standby" takes effect on the NEXT adjacency
# !!! DOWN event and is allowed only with a single IDL/IDP channel - test carefully.

set -u
set -o pipefail

# ---------------------------------------------------------------- settings
# All values can be overridden via environment or /etc/default/mlag-onbox-failover.
CONF_FILE="${CONF_FILE:-/etc/default/mlag-onbox-failover}"
# shellcheck source=/dev/null
[ -r "$CONF_FILE" ] && . "$CONF_FILE"

PEER_IP="${PEER_IP:-192.0.2.1}"            # master IDP/mgmt address (placeholder)
PING_VRF="${PING_VRF:-management}"         # empty = ping in default VRF
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"      # consecutive "dead" checks before action
CHECK_INTERVAL="${CHECK_INTERVAL:-10}"     # seconds between checks in --daemon mode
RECOVERY_WAIT="${RECOVERY_WAIT:-60}"       # seconds to wait before re-enabling strict
REVERTIVE="${REVERTIVE:-yes}"              # switchover type revertive on mlag ifaces?
AUTO_RELOAD="${AUTO_RELOAD:-no}"           # yes = reload this node to hand role back (dangerous)
DRY_RUN="${DRY_RUN:-no}"                   # yes = log actions, change nothing

STATE_DIR="${STATE_DIR:-/var/lib/mlag-onbox-failover}"
LOCK_FILE="${LOCK_FILE:-/run/mlag-onbox-failover.lock}"
LOG="${LOG:-/var/log/mlag-onbox-failover.log}"
TAG="mlag-onbox-failover"

# OcNOS CLI invocation from bash. VERIFY on your release (cmlsh option for
# non-interactive execution is not documented in public OcNOS docs).
CLI_BIN="${CLI_BIN:-cmlsh}"
CLI_OPT="${CLI_OPT:--e}"

# Show/config commands (verified syntax noted in README).
CMD_ADJ="${CMD_ADJ:-show mlag domain summary}"     # expects "Domain Adjacency : UP|DOWN"
CMD_STATE="${CMD_STATE:-show mlag detail}"          # local MLAG role; VERIFY pattern
CMD_STRICT_OFF="${CMD_STRICT_OFF:-mcec strict-active-standby disable}"
CMD_STRICT_ON="${CMD_STRICT_ON:-no mcec strict-active-standby}"
CMD_RELOAD="${CMD_RELOAD:-reload}"

# Output patterns (case-insensitive extended regex). VERIFY against real output.
RE_ADJ_UP="${RE_ADJ_UP:-Domain Adjacency[[:space:]]*:[[:space:]]*UP}"
RE_ADJ_DOWN="${RE_ADJ_DOWN:-Domain Adjacency[[:space:]]*:[[:space:]]*DOWN}"
RE_ACTIVE="${RE_ACTIVE:-(Mlag|MLAG)?[[:space:]]*(State|Status|Role|Mode)[[:space:]]*:[[:space:]]*Active}"

FAIL_FILE="$STATE_DIR/fail_count"
FAILOVER_FILE="$STATE_DIR/in_failover"

# ---------------------------------------------------------------- helpers
log() {
    local msg="$*"
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S%z')" "$msg" >> "$LOG" 2>/dev/null
    logger -t "$TAG" -- "$msg" 2>/dev/null || true
}

# Run one or more OcNOS exec-mode commands; prints CLI output.
cli() {
    "$CLI_BIN" "$CLI_OPT" "$*" 2>&1
}

# Apply config commands. OcNOS CLI is transaction based: changes need "commit".
cli_config() {
    local cmd="$1"
    if [ "$DRY_RUN" = "yes" ]; then
        log "DRY-RUN: would configure: '$cmd' + commit"
        return 0
    fi
    # VERIFY: how your cmlsh accepts multi-line input (here: one string per -e).
    "$CLI_BIN" "$CLI_OPT" "configure terminal" "$CLI_OPT" "$cmd" "$CLI_OPT" "commit" 2>&1 \
        | while IFS= read -r l; do log "cli: $l"; done
}

# Peer reachability: secondary signal only. -c 2 probes, -W 2 s timeout each.
peer_pings() {
    if [ -n "$PING_VRF" ]; then
        ip vrf exec "$PING_VRF" ping -c 2 -W 2 -q "$PEER_IP" >/dev/null 2>&1
    else
        ping -c 2 -W 2 -q "$PEER_IP" >/dev/null 2>&1
    fi
}

# Echo up|down|unknown from local CLI.
adjacency() {
    local out
    out="$(cli "$CMD_ADJ")" || { echo unknown; return; }
    if grep -Eqi "$RE_ADJ_UP" <<<"$out"; then echo up
    elif grep -Eqi "$RE_ADJ_DOWN" <<<"$out"; then echo down
    else echo unknown
    fi
}

# Echo active|standby (unknown treated as standby for safety of "do nothing if active").
local_state() {
    local out
    out="$(cli "$CMD_STATE")" || { echo unknown; return; }
    if grep -Eqi "$RE_ACTIVE" <<<"$out"; then echo active; else echo standby; fi
}

get_fails() { cat "$FAIL_FILE" 2>/dev/null || echo 0; }
set_fails() { echo "$1" > "$FAIL_FILE"; }

# ---------------------------------------------------------------- logic
check_once() {
    local adj state fails
    adj="$(adjacency)"

    if [ -f "$FAILOVER_FILE" ]; then
        # Recovery path.
        if [ "$adj" = "up" ] && peer_pings; then
            log "recovery: adjacency up and peer reachable, waiting ${RECOVERY_WAIT}s"
            sleep "$RECOVERY_WAIT"
            if [ "$(adjacency)" = "up" ] && peer_pings; then
                log "recovery: still healthy, re-enabling strict active-standby"
                cli_config "$CMD_STRICT_ON"
                [ "$DRY_RUN" = "yes" ] || rm -f "$FAILOVER_FILE"
                state="$(local_state)"
                if [ "$state" = "active" ]; then
                    if [ "$REVERTIVE" = "yes" ]; then
                        log "recovery: revertive switchover configured, role should move back by timer"
                    elif [ "$AUTO_RELOAD" = "yes" ]; then
                        log "recovery: non-revertive + AUTO_RELOAD=yes, reloading this node"
                        if [ "$DRY_RUN" = "yes" ]; then log "DRY-RUN: would run '$CMD_RELOAD'"
                        else cli "$CMD_RELOAD" | while IFS= read -r l; do log "cli: $l"; done; fi
                    else
                        log "recovery: non-revertive, this node is still ACTIVE - plan a manual CLI reload"
                    fi
                fi
            else
                log "recovery: recheck failed, staying in failover"
            fi
        fi
        return 0
    fi

    if [ "$adj" = "up" ]; then
        [ "$(get_fails)" = "0" ] || log "adjacency up again, counter reset"
        set_fails 0
        return 0
    fi

    if [ "$adj" = "unknown" ]; then
        log "WARN: cannot parse adjacency from '$CMD_ADJ' output, doing nothing"
        return 0
    fi

    # adjacency down
    state="$(local_state)"
    if [ "$state" = "active" ]; then
        # Planned CLI reload of master: standby already took over by itself.
        log "adjacency down, local node already ACTIVE - nothing to do"
        set_fails 0
        return 0
    fi

    if peer_pings; then
        log "adjacency down but peer $PEER_IP answers ping - link/IDP issue, staying silent"
        set_fails 0
        return 0
    fi

    fails=$(( $(get_fails) + 1 ))
    set_fails "$fails"
    log "adjacency down and peer $PEER_IP silent ($fails/$FAIL_THRESHOLD)"
    if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
        # Grace check: a planned CLI reload makes us active within seconds.
        if [ "$(local_state)" = "active" ]; then
            log "node became ACTIVE on its own (planned reload) - no action"
            set_fails 0
            return 0
        fi
        log "ACTION: peer considered dead, disabling strict active-standby"
        cli_config "$CMD_STRICT_OFF"
        [ "$DRY_RUN" = "yes" ] || date '+%s' > "$FAILOVER_FILE"
        set_fails 0
    fi
}

main() {
    mkdir -p "$STATE_DIR" || exit 1
    exec 9>"$LOCK_FILE" || exit 1
    if ! flock -n 9; then
        log "another instance is running, exit"
        exit 0
    fi
    case "${1:-}" in
        --daemon)
            log "started in daemon mode (interval ${CHECK_INTERVAL}s, dry-run=$DRY_RUN)"
            while true; do check_once; sleep "$CHECK_INTERVAL"; done ;;
        --dry-run)
            DRY_RUN=yes; check_once ;;
        ""|--once)
            check_once ;;
        *)
            echo "usage: $0 [--once|--daemon|--dry-run]" >&2; exit 2 ;;
    esac
}

main "$@"
