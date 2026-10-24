#!/usr/bin/env python3
"""Probe NapCat/SnowLuma OneBot HTTP and send optional Resend alerts."""

import json
import http.client
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path


CONFIG_PATH = None
STATE_PATH = None
RESEND_URL = "https://api.resend.com/emails"
KICK_RE = re.compile(
    r"KickedOffLine|账号状态变更为离线|登录态已失效|需要重新登录|快速登录错误：\s*登录需要手Q验证",
    re.I,
)
LOGIN_RE = re.compile(
    r"登录成功|账号状态变更为在线|LoginSuccess|OneBot11 适配器初始化完成",
    re.I,
)


def run(*args, timeout=15, merge_stderr=False):
    result = subprocess.run(
        args, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True, timeout=timeout, check=True,
    )
    return result.stdout


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def save_state(state):
    STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE_PATH)


def api(config, action, body):
    token = Path(config["token_file"]).read_text(encoding="utf-8").strip()
    request = urllib.request.Request(
        config["http_url"].rstrip("/") + "/" + action,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        result = json.load(response)
    if result.get("status") != "ok" or result.get("retcode") != 0:
        raise RuntimeError(f"{action}: status={result.get('status')} retcode={result.get('retcode')}")
    return result.get("data") or {}


def scan_login_logs(config, state):
    output = run("docker", "logs", "--since", "10m", "--tail", "500", "--timestamps", gateway_container(config), merge_stderr=True)
    cursor = state.get("log_cursor", "")
    newest = cursor
    # Docker stdout/stderr records may arrive out of order; use their timestamps.
    for line in sorted(output.splitlines(), key=lambda row: row.partition(" ")[0]):
        stamp, _, message = line.partition(" ")
        if not stamp or stamp <= cursor:
            continue
        newest = max(newest, stamp)
        if KICK_RE.search(message):
            state["kick_latched"] = True
        elif LOGIN_RE.search(message):
            state["kick_latched"] = False
    state["log_cursor"] = newest


def onebot_connected(config):
    try:
        pid = run("docker", "inspect", "--format", "{{.State.Pid}}", config["astrbot_container"]).strip()
        if not pid.isdigit() or pid == "0":
            return False
        sockets = run("nsenter", "-t", pid, "-n", "ss", "-Htn", "state", "established")
        return any(row.split()[2].endswith(":" + str(config["onebot_ws_port"])) for row in sockets.splitlines() if len(row.split()) >= 4)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def gateway_container(config):
    return config.get("gateway_container") or config.get("napcat_container")


def scan_session_logs(config, state):
    output = run("docker", "logs", "--since", "10m", "--tail", "500", "--timestamps", gateway_container(config), merge_stderr=True)
    cursor = state.get("log_cursor", "")
    newest = cursor
    closed = re.compile(r"\bsession closed:\s*UIN=" + re.escape(str(config["qq_user_id"])) + r"\b")
    for line in sorted(output.splitlines(), key=lambda row: row.partition(" ")[0]):
        stamp, _, message = line.partition(" ")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T", stamp) or stamp <= cursor:
            continue
        newest = max(newest, stamp)
        if closed.search(message):
            state["session_closed"] = True
    state["log_cursor"] = newest


def probe_snowluma(config, state):
    errors = (OSError, ValueError, KeyError, RuntimeError, http.client.HTTPException,
              subprocess.CalledProcessError, subprocess.TimeoutExpired)
    try:
        scan_session_logs(config, state)
    except errors:
        pass
    try:
        status = api(config, "get_status", {})
        if not all(isinstance(status.get(k), bool) for k in ("online", "good")):
            return "unknown", "unrecognized SnowLuma status schema"
        if not status["online"] or not status["good"]:
            return "offline", "SnowLuma reports unavailable QQ session"
        login = api(config, "get_login_info", {})
        if not login.get("user_id"):
            return "unknown", "SnowLuma login identity unavailable"
        if str(login["user_id"]) != str(config["qq_user_id"]):
            return "offline", "login account mismatch"
        state["session_closed"] = False
        if not onebot_connected(config):
            return "online", "QQ online; AstrBot OneBot connection unavailable"
        return "online", "QQ online and OneBot connected"
    except errors as exc:
        if state.get("session_closed"):
            return "offline", "SnowLuma reported target account session closed"
        return "unknown", "probe failed: " + type(exc).__name__


def probe_napcat(config, state):
    try:
        scan_login_logs(config, state)
        status = api(config, "get_status", {})
        login = api(config, "get_login_info", {})
        user_id = str(login.get("user_id", ""))
        if user_id != str(config["qq_user_id"]):
            return "offline", "login account mismatch"
        if state.get("kick_latched"):
            return "offline", "NapCat reported QQ kick or expired login"
        if status.get("online") is not True or status.get("good") is not True:
            return "offline", "get_status reports offline"
        if config.get("active_user_probe", True):
            api(config, "nc_get_user_status", {"user_id": int(config["qq_user_id"])})
        if not onebot_connected(config):
            return "online", "QQ online; AstrBot OneBot connection unavailable"
        return "online", "QQ online and OneBot connected"
    except (OSError, ValueError, KeyError, RuntimeError, urllib.error.URLError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if state.get("kick_latched"):
            return "offline", "NapCat reported QQ kick or expired login"
        return "unknown", "probe failed: " + type(exc).__name__


def probe(config, state):
    kind = config.get("gateway_type", "napcat")
    if kind == "snowluma":
        return probe_snowluma(config, state)
    if kind == "napcat":
        return probe_napcat(config, state)
    raise ValueError("unsupported gateway type")


def queue_event(state, name, reason, now, not_before=None, cooldown_hold=False):
    state.setdefault("pending", []).append({
        "name": name,
        "reason": reason,
        "occurred_at": int(now),
        "not_before": int(not_before or now),
        "cooldown_hold": cooldown_hold,
        "attempts": 0,
    })


def transition(state, result, reason, now):
    if result == "unknown":
        state["bad_count"] = 0
        state["good_count"] = 0
        return
    if result == "offline":
        state["bad_count"] = state.get("bad_count", 0) + 1
        state["good_count"] = 0
        if state["bad_count"] >= 3 and state.get("phase") != "offline":
            state["phase"] = "offline"
            hold_until = state["last_restored_at"] + 1800 if "last_restored_at" in state else 0
            queue_event(
                state, "QQ_LOGIN_LOST", reason, now,
                max(now, hold_until), cooldown_hold=hold_until > now,
            )
        return
    state["good_count"] = state.get("good_count", 0) + 1
    state["bad_count"] = 0
    if state["good_count"] >= 2 and state.get("phase") != "online":
        if state.get("phase") == "offline":
            held_loss = any(
                item["name"] == "QQ_LOGIN_LOST" and item.get("cooldown_hold")
                and item["not_before"] > now for item in state.get("pending", [])
            )
            if held_loss:
                state["pending"] = [
                    item for item in state["pending"]
                    if not (item["name"] == "QQ_LOGIN_LOST" and item.get("cooldown_hold")
                            and item["not_before"] > now)
                ]
            else:
                queue_event(state, "QQ_LOGIN_RESTORED", reason, now)
            state["last_restored_at"] = int(now)
        state["phase"] = "online"


def send_resend(config, event, test=False):
    label = config.get("gateway_label", "SnowLuma" if config.get("gateway_type") == "snowluma" else "NapCat")
    if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9 _-]{1,32}", label):
        raise ValueError("invalid gateway label")
    address = config["resend_to"]
    if not isinstance(address, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", address):
        raise ValueError("invalid Resend recipient")
    key = Path(config["resend_api_key_file"]).read_text(encoding="ascii").strip()
    if not key or "\n" in key or "\r" in key:
        raise ValueError("invalid Resend API key file")
    if test:
        subject = f"【{label} 测试】Resend 告警链路验证"
        body = "这是一封服务器端 Resend API 测试邮件。"
    else:
        lost = event["name"] == "QQ_LOGIN_LOST"
        if not lost and event["name"] != "QQ_LOGIN_RESTORED":
            raise ValueError("unexpected event name")
        subject = f"【{label} 告警】QQ Bot 已掉线" if lost else f"【{label} 通知】QQ Bot 已恢复"
        body = "\n".join((
            f"{label} 掉线告警" if lost else f"{label} 登录恢复通知",
            "状态：OFFLINE" if lost else "状态：ONLINE",
            "时间：" + time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(event["occurred_at"])),
            "主机：" + socket.gethostname(),
            "原因：" + event["reason"],
        ))
    payload = {"from": config["resend_from"], "to": [address], "subject": subject, "text": body}
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "NapCatMonitor/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Resend returned HTTP {response.status}")
        result = json.load(response)
    if not isinstance(result, dict) or not result.get("id"):
        raise RuntimeError("Resend response missing email id")
    return result["id"]


def send_event(config, event):
    return send_resend(config, event)


def flush_events(config, state, now):
    pending = state.setdefault("pending", [])
    # Bound work per timer tick; retain queue order and retry semantics.
    for _ in range(1):
        if not pending:
            break
        event = pending[0]
        if event["not_before"] > now:
            break
        try:
            send_event(config, event)
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            event["attempts"] += 1
            event["not_before"] = int(now + min(1800, 120 * event["attempts"]))
            save_state(state)
            print("event upload failed:", type(exc).__name__, file=sys.stderr)
            break
        pending.pop(0)
        state.setdefault("reported_history", []).append({
            "name": event["name"],
            "occurred_at": event["occurred_at"],
            "reported_at": int(now),
            "attempts": event["attempts"] + 1,
        })
        state["reported_history"] = state["reported_history"][-100:]
        save_state(state)
        print("reported", event["name"])


def validate_probe_config(config):
    if not isinstance(config, dict):
        raise ValueError("invalid probe config")
    config = dict(config)
    if config.get("gateway_type", "napcat") not in ("napcat", "snowluma"):
        raise ValueError("unsupported gateway type")
    if config.get("gateway_container") and config.get("napcat_container") and config["gateway_container"] != config["napcat_container"]:
        raise ValueError("conflicting gateway container settings")
    config["gateway_container"] = gateway_container(config)
    config.setdefault("gateway_type", "napcat")
    required = ("http_url", "token_file", "qq_user_id", "gateway_container",
                "astrbot_container", "onebot_ws_port")
    if not isinstance(config, dict) or any(not config.get(k) for k in required):
        raise ValueError("missing monitor settings")
    if any("REPLACE_" in str(config[k]) for k in required):
        raise ValueError("unfilled monitor settings")
    parsed = urlsplit(config["http_url"])
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1", "localhost")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not parsed.port):
        raise ValueError("OneBot HTTP must be a loopback URL")
    if not 1 <= int(config["onebot_ws_port"]) <= 65535:
        raise ValueError("invalid WS port")
    if not re.fullmatch(r"[0-9]{5,15}", str(config["qq_user_id"])):
        raise ValueError("invalid target account")
    for key in ("gateway_container", "astrbot_container"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", config[key]):
            raise ValueError("invalid container name")
    for key in ("token_file",):
        if not Path(config[key]).is_absolute():
            raise ValueError("secret path must be absolute")
    if any("\n" in str(config[k]) or "\r" in str(config[k]) for k in required):
        raise ValueError("invalid multiline setting")
    return config


def validate_config(config):
    config = validate_probe_config(config)
    for key in ("resend_api_key_file", "resend_from", "resend_to"):
        if not isinstance(config.get(key), str) or not config[key] or "REPLACE_" in config[key]:
            raise ValueError("missing mail settings")
        if "\n" in config[key] or "\r" in config[key]:
            raise ValueError("invalid mail setting")
    if not Path(config["resend_api_key_file"]).is_absolute():
        raise ValueError("key path must be absolute")
    return config


def main():
    global CONFIG_PATH, STATE_PATH
    config_path = os.environ.get("QQBOT_MONITOR_CONFIG")
    state_path = os.environ.get("QQBOT_MONITOR_STATE")
    if not config_path or not state_path:
        raise SystemExit("set QQBOT_MONITOR_CONFIG and QQBOT_MONITOR_STATE paths")
    CONFIG_PATH, STATE_PATH = Path(config_path), Path(state_path)
    if not CONFIG_PATH.is_absolute() or not STATE_PATH.is_absolute() or CONFIG_PATH == STATE_PATH:
        raise SystemExit("config/state must be separate absolute paths")
    config = load_json(CONFIG_PATH, None)
    if not config:
        raise SystemExit("monitor config missing")
    config = validate_config(config)
    if sys.argv[1:] == ["--test-resend"]:
        email_id = send_resend(config, None, test=True)
        print("Resend accepted test email id=" + email_id)
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: qq_monitor.py [--test-resend]")
    state = load_json(STATE_PATH, {"phase": "unknown", "bad_count": 0, "good_count": 0, "pending": []})
    now = time.time()
    result, reason = probe(config, state)
    transition(state, result, reason, now)
    state["last_probe_at"] = int(now)
    state["last_result"] = result
    state["last_reason"] = reason
    save_state(state)
    flush_events(config, state, now)
    save_state(state)
    print(
        f"qq={result} phase={state['phase']} "
        f"bad={state['bad_count']} good={state['good_count']} reason={reason}"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise SystemExit("monitor failed: " + type(exc).__name__) from None
