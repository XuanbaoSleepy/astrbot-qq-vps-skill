#!/usr/bin/env python3
"""Read-only target checks. Exit 0 covered checks pass, 1 fail, 2 incomplete."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("qq_monitor", Path(__file__).with_name("qq_monitor.py"))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def binding_result(info, expected, ws_port=None):
    """Docker NAT bindings matter even without a docker-proxy listener."""
    bindings = info.get("HostConfig", {}).get("PortBindings") or {}
    errors = []
    for key, values in bindings.items():
        for value in values or []:
            if value.get("HostIp") not in ("127.0.0.1", "::1"):
                errors.append("non-loopback published port")
        if ws_port and key == str(ws_port) + "/tcp" and values:
            errors.append("WS port published on host")
    for container_port, host_port in expected.items():
        values = bindings.get(str(container_port) + "/tcp") or []
        if not any(v.get("HostIp") in ("127.0.0.1", "::1") and v.get("HostPort") == str(host_port) for v in values):
            errors.append("required loopback mapping missing")
    return errors


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=20).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-type", choices=("napcat", "snowluma"), default="napcat")
    parser.add_argument("--gateway", "--napcat", dest="gateway", required=True)
    parser.add_argument("--astrbot", required=True)
    parser.add_argument("--gateway-webui-port", "--napcat-webui-port", dest="gateway_webui_port", type=int, required=True)
    parser.add_argument("--novnc-port", type=int, help="optional SnowLuma noVNC host mapping to check")
    parser.add_argument("--astrbot-webui-port", type=int, required=True)
    parser.add_argument("--onebot-http-port", type=int, required=True)
    parser.add_argument("--onebot-ws-port", type=int, required=True)
    parser.add_argument("--qq-probe-config", type=Path, help="private probe-only config; no mail settings needed")
    parser.add_argument("--monitor-config", type=Path, help="mail monitoring checks require config/state/unit together")
    parser.add_argument("--monitor-state", type=Path)
    parser.add_argument("--monitor-unit", help="base unit name without .timer")
    parser.add_argument("--cloudflared-unit", help="check only when enabled in intended scope")
    parser.add_argument("--max-probe-age", type=int, default=360)
    args = parser.parse_args()
    selected = (args.monitor_config, args.monitor_state, args.monitor_unit)
    if any(selected) and not all(selected):
        parser.error("monitor-config/state/unit must be supplied together")
    for port in (args.gateway_webui_port, args.astrbot_webui_port, args.onebot_http_port, args.onebot_ws_port, *([args.novnc_port] if args.novnc_port is not None else [])):
        if not 1 <= port <= 65535:
            parser.error("ports must be 1..65535")
    findings = []

    def record(label, result, detail=""):
        findings.append((label, result))
        print(f"{result}: {label}" + (f" ({detail})" if detail else ""))

    gateway_webui = 5099 if args.gateway_type == "snowluma" else 6099
    gateway_ports = {gateway_webui: args.gateway_webui_port, 3000: args.onebot_http_port}
    if args.novnc_port:
        gateway_ports[6081] = args.novnc_port
    for name, mappings, ws in (
        (args.gateway, gateway_ports, 3001 if args.gateway_type == "snowluma" else None),
        (args.astrbot, {6185: args.astrbot_webui_port}, args.onebot_ws_port),
    ):
        try:
            info = json.loads(run("docker", "inspect", name))[0]
            state = info["State"]
            record(name + " running", "PASS" if state.get("Running") and not state.get("OOMKilled") else "FAIL")
            record(name + " restart-policy", "PASS" if info["HostConfig"]["RestartPolicy"]["Name"] in ("always", "unless-stopped") else "FAIL")
            errors = binding_result(info, mappings, ws)
            record(name + " port-bindings", "FAIL" if errors else "PASS", "; ".join(errors))
            is_gateway = name == args.gateway
            required = ({"/app/data", "/app/.config", "/app/.local/share"} if args.gateway_type == "snowluma" else {"/AstrBot/data", "/app/napcat/config", "/app/.config/QQ"}) if is_gateway else {"/AstrBot/data"}
            mounted = {m["Destination"] for m in info.get("Mounts", []) if m.get("Type") in ("bind", "volume") and m.get("RW")}
            record(name + " writable-persistent-mounts", "PASS" if required <= mounted else "FAIL")
            if is_gateway and args.gateway_type == "snowluma":
                host = info["HostConfig"]
                ptrace = "SYS_PTRACE" in (host.get("CapAdd") or [])
                seccomp = any(x in ("seccomp=unconfined", "seccomp:unconfined") for x in host.get("SecurityOpt") or [])
                record(name + " hook-container-permissions", "PASS" if ptrace and seccomp else "FAIL")
                record(name + " shared-memory", "PASS" if host.get("ShmSize", 0) >= 1073741824 else "FAIL")
            logs = info["HostConfig"].get("LogConfig", {})
            record(name + " bounded-logs", "PASS" if logs.get("Type") == "json-file" and all(logs.get("Config", {}).get(k) for k in ("max-size", "max-file")) else "UNVERIFIED")
            record(name + " restart-count", "INFO", str(info.get("RestartCount", 0)))
        except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError) as exc:
            record(name + " inspect", "UNVERIFIED", type(exc).__name__)
    for port in (args.gateway_webui_port, args.astrbot_webui_port):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=8) as response:
                record("local webui " + str(port), "PASS" if 200 <= response.status < 400 else "FAIL")
        except OSError as exc:
            record("local webui " + str(port), "FAIL", type(exc).__name__)
    probe_path = args.qq_probe_config or args.monitor_config
    try:
        if probe_path:
            config = monitor.validate_probe_config(json.loads(probe_path.read_text(encoding="utf-8-sig")))
        else:
            config = None
        if config is not None:
            compatible = (config["gateway_container"] == args.gateway and config["gateway_type"] == args.gateway_type and config["astrbot_container"] == args.astrbot
                          and int(config["onebot_ws_port"]) == args.onebot_ws_port
                          and monitor.urlsplit(config["http_url"]).port == args.onebot_http_port)
            if not compatible:
                raise ValueError("config differs from target")
            state = json.loads(args.monitor_state.read_text(encoding="utf-8")) if args.monitor_state else {}
            result, _reason = monitor.probe(config, dict(state))
            record("live QQ probe", {"online": "PASS", "offline": "FAIL", "unknown": "UNVERIFIED"}[result])
            record("live OneBot WS", "PASS" if monitor.onebot_connected(config) else "FAIL")
        else:
            record("QQ/WS probe not selected", "INFO", "requires manual acceptance or --qq-probe-config")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record("QQ/WS probe", "UNVERIFIED", type(exc).__name__)
    if args.monitor_config:
        try:
            config = monitor.validate_config(json.loads(args.monitor_config.read_text(encoding="utf-8-sig")))
            compatible = (config["gateway_container"] == args.gateway and config["gateway_type"] == args.gateway_type and config["astrbot_container"] == args.astrbot
                          and int(config["onebot_ws_port"]) == args.onebot_ws_port
                          and monitor.urlsplit(config["http_url"]).port == args.onebot_http_port)
            if not compatible:
                raise ValueError("config differs from target")
            state = json.loads(args.monitor_state.read_text(encoding="utf-8"))
            age = time.time() - state.get("last_probe_at", 0)
            record("monitor freshness", "PASS" if 0 <= age <= args.max_probe_age else "FAIL")
            record("pending mail queue", "PASS" if not state.get("pending") else "FAIL")
            if os.name == "posix":
                paths = (args.monitor_config, args.monitor_state, Path(config["token_file"]), Path(config["resend_api_key_file"]))
                for path in paths:
                    stat = path.stat()
                    record("private monitor file", "PASS" if stat.st_uid == 0 and stat.st_mode & 0o777 == 0o600 else "FAIL")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            record("monitor live/state/config checks", "UNVERIFIED", type(exc).__name__)
    units = ["docker"]
    if args.monitor_unit:
        units.append(args.monitor_unit + ".timer")
    if args.cloudflared_unit:
        units.append(args.cloudflared_unit)
    for unit in units:
        for verb in ("is-active", "is-enabled"):
            try:
                value = run("systemctl", verb, unit).strip()
                record(unit + " " + verb, "PASS" if value in ("active", "enabled") else "FAIL")
            except subprocess.CalledProcessError:
                record(unit + " " + verb, "FAIL", "inactive/disabled/missing required unit")
            except (OSError, subprocess.SubprocessError) as exc:
                record(unit + " " + verb, "UNVERIFIED", type(exc).__name__)
    if args.monitor_unit:
        try:
            status = run("systemctl", "show", args.monitor_unit + ".service", "-p", "Result", "-p", "ExecMainStatus")
            record("last monitor execution", "PASS" if "Result=success" in status and "ExecMainStatus=0" in status else "FAIL")
        except (OSError, subprocess.SubprocessError) as exc:
            record("last monitor execution", "UNVERIFIED", type(exc).__name__)
    manual = ["cloud firewall/IPv6 external probes", "/help reply", "reboot/restore only if requested"]
    if args.cloudflared_unit:
        manual.append("Access anonymous/authenticated UI")
    if args.monitor_config:
        manual.append("email receipt")
    print("MANUAL: " + ", ".join(manual) + ".")
    values = [value for _, value in findings]
    return 1 if "FAIL" in values else 2 if "UNVERIFIED" in values else 0


if __name__ == "__main__":
    raise SystemExit(main())
