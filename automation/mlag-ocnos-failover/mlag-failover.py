#!/usr/bin/env python3
"""External MLAG failover monitor for IP Infusion OcNOS.

Pings the master management IP and reads `show mcec` on the standby node via
Netmiko. If the master is dead (no ping) AND MCEC adjacency is down for
FAIL_THRESHOLD consecutive checks, strict active-standby is disabled on the
standby so it takes over forwarding. When the master is back and adjacency is
up, strict mode is restored and, if the standby is still active, the role is
handed back by reloading it (revertive setups).

All IPs/credentials are placeholders read from environment variables.
Verify command syntax and `show mcec` output format on your OcNOS version.
"""
import argparse
import logging
import os
import re
import subprocess
import sys
import time

from netmiko import ConnectHandler

MASTER_MGMT_IP = os.environ.get("MASTER_MGMT_IP", "192.0.2.1")
STANDBY_MGMT_IP = os.environ.get("STANDBY_MGMT_IP", "192.0.2.2")
OCNOS_USER = os.environ.get("OCNOS_USER", "CHANGE_ME")
OCNOS_PASSWORD = os.environ.get("OCNOS_PASSWORD", "CHANGE_ME")
OCNOS_SSH_PORT = int(os.environ.get("OCNOS_SSH_PORT", "22"))

FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "3"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
RECOVERY_WAIT = int(os.environ.get("RECOVERY_WAIT", "60"))

# Commands - verify on your OcNOS version.
CMD_SHOW = "show mcec"
CMD_DISABLE_STRICT = "mcec strict-active-standby disable"
CMD_ENABLE_STRICT = "no mcec strict-active-standby"

log = logging.getLogger("mlag-failover")

# Tolerant regexes. The exact `show mcec` output format differs between OcNOS
# releases and MUST be verified against real device output before production use.
RE_ADJ = re.compile(r"adjacenc\w*\s*[:=]?\s*(up|down)", re.I)
RE_STRICT = re.compile(r"strict[\w\s-]*?[:=]?\s*(enabled|disabled|enable|disable)", re.I)
RE_STATE = re.compile(r"(?:state|role|status)\s*[:=]?\s*(active|standby)", re.I)


def device():
    """Netmiko connection parameters for the standby node."""
    return {
        "device_type": "ipinfusion_ocnos",
        "host": STANDBY_MGMT_IP,
        "username": OCNOS_USER,
        "password": OCNOS_PASSWORD,
        "port": OCNOS_SSH_PORT,
        "timeout": 15,
    }


def ping(host, count=2, timeout=2):
    """Return True if host answers ICMP echo."""
    try:
        r = subprocess.run(["ping", "-c", str(count), "-W", str(timeout), host],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except OSError as exc:
        log.error("ping could not run: %s", exc)
        return False


def parse_mcec(output):
    """Extract adjacency/strict/state from `show mcec`; None for unknown fields."""
    def grab(rx):
        m = rx.search(output)
        return m.group(1).lower() if m else None
    strict = grab(RE_STRICT)
    if strict:
        strict = "enabled" if strict.startswith("enable") else "disabled"
    return {"adjacency": grab(RE_ADJ), "strict": strict, "state": grab(RE_STATE)}


def read_standby():
    """SSH to the standby and return parsed `show mcec`, or None on error."""
    try:
        with ConnectHandler(**device()) as conn:
            out = conn.send_command(CMD_SHOW)
    except Exception as exc:  # netmiko raises several exception types
        log.error("SSH to standby %s failed: %s", STANDBY_MGMT_IP, exc)
        return None
    info = parse_mcec(out)
    log.debug("show mcec parsed: %s", info)
    if info["adjacency"] is None:
        log.warning("could not parse adjacency, raw output:\n%s", out)
    return info


def run_config(cmds, dry_run):
    """Apply config commands on the standby (config mode) and save."""
    log.warning("config on standby %s: %s%s", STANDBY_MGMT_IP, cmds,
                " (dry-run)" if dry_run else "")
    if dry_run:
        return
    with ConnectHandler(**device()) as conn:
        log.info(conn.send_config_set(cmds))
        try:
            conn.save_config()
        except Exception as exc:
            log.warning("save_config failed: %s", exc)


def disable_strict(dry_run):
    run_config([CMD_DISABLE_STRICT], dry_run)


def enable_strict(dry_run):
    run_config([CMD_ENABLE_STRICT], dry_run)


def revert_role(dry_run):
    """Reload the currently active (former standby) node to hand the role back."""
    log.warning("reloading %s to revert MLAG role%s", STANDBY_MGMT_IP,
                " (dry-run)" if dry_run else "")
    if dry_run:
        return
    with ConnectHandler(**device()) as conn:
        out = conn.send_command_timing("reload")
        if re.search(r"(confirm|y/n|\[y)", out, re.I):
            conn.send_command_timing("y")


def main():
    ap = argparse.ArgumentParser(description="OcNOS MLAG external failover monitor")
    ap.add_argument("--dry-run", action="store_true", help="log actions, change nothing")
    ap.add_argument("--once", action="store_true", help="run a single check and exit")
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if "CHANGE_ME" in (OCNOS_USER, OCNOS_PASSWORD):
        log.warning("credentials are placeholders; set OCNOS_USER / OCNOS_PASSWORD")

    fails = 0
    in_failover = False
    while True:
        master_alive = ping(MASTER_MGMT_IP)
        info = read_standby()
        adjacency = info["adjacency"] if info else None
        log.info("master_alive=%s adjacency=%s strict=%s state=%s in_failover=%s",
                 master_alive, adjacency, info["strict"] if info else None,
                 info["state"] if info else None, in_failover)

        if not in_failover:
            # Node death = no ping AND adjacency down. Ping loss alone or
            # adjacency loss alone (e.g. IDP failure) must NOT trigger failover.
            if not master_alive and adjacency == "down":
                fails += 1
                log.warning("failure condition %d/%d", fails, FAIL_THRESHOLD)
                if fails >= FAIL_THRESHOLD:
                    disable_strict(args.dry_run)
                    in_failover = True
                    fails = 0
            else:
                fails = 0
        elif master_alive and adjacency == "up":
            log.info("master is back, waiting %ss before restoring strict mode", RECOVERY_WAIT)
            time.sleep(RECOVERY_WAIT)
            info = read_standby()
            if ping(MASTER_MGMT_IP) and info and info["adjacency"] == "up":
                enable_strict(args.dry_run)
                if info["state"] == "active":
                    revert_role(args.dry_run)
                in_failover = False
            else:
                log.warning("recovery recheck failed, staying in failover")

        if args.once:
            return 0
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
