#!/usr/bin/env python3
"""Offline tests: no live mail, Docker, production config/state or network."""
import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load("qq_monitor")
v = load("verify")


def state():
    return {"phase": "online", "bad_count": 0, "good_count": 2, "pending": []}


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Tests(unittest.TestCase):
    def test_seven_offline_once_then_restore(self):
        s = state()
        for i in range(7):
            m.transition(s, "offline", "simulation", 10000 + i * 120)
        self.assertEqual([e["name"] for e in s["pending"]], ["QQ_LOGIN_LOST"])
        m.transition(s, "online", "simulation", 11000)
        self.assertEqual(s["phase"], "offline")
        m.transition(s, "online", "simulation", 11120)
        self.assertEqual([e["name"] for e in s["pending"]], ["QQ_LOGIN_LOST", "QQ_LOGIN_RESTORED"])

    def test_unknown_breaks_consecutive_samples(self):
        s = state()
        for result in ("offline", "offline", "unknown", "offline"):
            m.transition(s, result, "simulation", 10000)
        self.assertEqual(s["phase"], "online")
        self.assertFalse(s["pending"])
        self.assertEqual(s["bad_count"], 1)

    def test_cooldown_cancel(self):
        s = state()
        s["last_restored_at"] = 10000
        for i in range(3):
            m.transition(s, "offline", "simulation", 10100 + i)
        self.assertEqual(s["pending"][0]["not_before"], 11800)
        for i in range(2):
            m.transition(s, "online", "simulation", 10200 + i)
        self.assertEqual(s["phase"], "online")
        self.assertFalse(s["pending"])

    def test_initial_online_no_restore(self):
        s = {"phase": "unknown", "pending": []}
        for i in range(2):
            m.transition(s, "online", "simulation", i)
        self.assertEqual(s["phase"], "online")
        self.assertFalse(s["pending"])

    def test_failure_queue_persist_and_order(self):
        with tempfile.TemporaryDirectory() as folder:
            s = state()
            m.queue_event(s, "QQ_LOGIN_LOST", "simulation", 10000)
            m.queue_event(s, "QQ_LOGIN_RESTORED", "simulation", 10001)
            path = Path(folder) / "state.json"
            with patch.object(m, "STATE_PATH", path), patch.object(m, "send_event", side_effect=OSError("offline")):
                m.flush_events({}, s, 10002)
            self.assertEqual(s["pending"][0]["attempts"], 1)
            self.assertEqual(len(json.loads(path.read_text())["pending"]), 2)
            sent = []
            with patch.object(m, "STATE_PATH", path), patch.object(m, "send_event", side_effect=lambda c, e: sent.append(e["name"])):
                m.flush_events({}, s, 10300)
                self.assertEqual(len(s["pending"]), 1)
                m.flush_events({}, s, 10420)
            self.assertEqual(sent, ["QQ_LOGIN_LOST", "QQ_LOGIN_RESTORED"])
            self.assertFalse(s["pending"])

    def test_transport_and_test_no_state_write(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "key"
            key.write_text("fixture-value\n", encoding="ascii")
            config = {"resend_to": "test@example.invalid", "resend_from": "sender@example.invalid", "resend_api_key_file": str(key)}
            captured = []

            def capture(request, timeout):
                captured.append(request)
                return Response(b'{"id":"fixture-id"}')

            with patch.object(m.urllib.request, "urlopen", side_effect=capture), patch.object(m, "save_state", side_effect=AssertionError("must not write")):
                self.assertEqual(m.send_resend(config, None, test=True), "fixture-id")
                m.send_resend(config, {"name": "QQ_LOGIN_LOST", "reason": "模拟", "occurred_at": 1})
            for request in captured:
                self.assertEqual(request.full_url, "https://api.resend.com/emails")
                self.assertEqual(request.get_header("User-agent"), "NapCatMonitor/1.0")
                self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
                self.assertEqual(json.loads(request.data)["from"], config["resend_from"])
            self.assertIn("模拟", json.loads(captured[1].data)["text"])

    def test_probe_boundaries(self):
        config = {"qq_user_id": "123456", "active_user_probe": True}

        def api(c, action, body):
            return {"online": True, "good": True} if action == "get_status" else {"user_id": 123456}

        with patch.object(m, "scan_login_logs"), patch.object(m, "api", side_effect=api), patch.object(m, "onebot_connected", return_value=False):
            self.assertEqual(m.probe(config, {})[0], "online")  # historical diagnostic-only WS
            self.assertEqual(m.probe(config, {"kick_latched": True})[0], "offline")
            self.assertEqual(m.probe({**config, "qq_user_id": "654321"}, {})[0], "offline")
        with patch.object(m, "scan_login_logs", side_effect=OSError("fixture")):
            self.assertEqual(m.probe(config, {})[0], "unknown")
            self.assertEqual(m.probe(config, {"kick_latched": True})[0], "offline")

    def test_recovery_log_cursor(self):
        output = "2026-01-01T00:00:02Z OneBot11 适配器初始化完成\n2026-01-01T00:00:01Z 登录态已失效\n"
        s = {}
        with patch.object(m, "run", return_value=output):
            m.scan_login_logs({"napcat_container": "fixture"}, s)
        self.assertFalse(s["kick_latched"])
        self.assertEqual(s["log_cursor"], "2026-01-01T00:00:02Z")

    def test_port_bindings_reject_public_and_ws(self):
        info = {"HostConfig": {"PortBindings": {"6185/tcp": [{"HostIp": "127.0.0.1", "HostPort": "16185"}]}}}
        self.assertFalse(v.binding_result(info, {6185: 16185}, 6199))
        info["HostConfig"]["PortBindings"]["6199/tcp"] = [{"HostIp": "127.0.0.1", "HostPort": "16199"}]
        self.assertTrue(v.binding_result(info, {6185: 16185}, 6199))
        for address in ("0.0.0.0", "::", ""):
            info["HostConfig"]["PortBindings"] = {"6185/tcp": [{"HostIp": address, "HostPort": "16185"}]}
            self.assertTrue(v.binding_result(info, {6185: 16185}, 6199))

    def test_verifier_exit_codes_and_no_raw_output(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            config = {
                "http_url": "http://127.0.0.1:13000", "token_file": str(base / "http-token"),
                "resend_api_key_file": str(base / "mail-key"), "qq_user_id": "123456",
                "napcat_container": "fixture-n", "astrbot_container": "fixture-a",
                "onebot_ws_port": 6199, "resend_from": "sender@example.invalid",
                "resend_to": "test@example.invalid",
            }
            for name in ("http-token", "mail-key"):
                (base / name).write_text("private-fixture-value")
            cfg = base / "config.json"
            cfg.write_text(json.dumps(config))
            st = base / "state.json"
            import time
            st.write_text(json.dumps({"last_probe_at": time.time(), "pending": []}))
            argv = ["verify.py", "--napcat", "fixture-n", "--astrbot", "fixture-a",
                    "--napcat-webui-port", "16099", "--astrbot-webui-port", "16185",
                    "--onebot-http-port", "13000", "--onebot-ws-port", "6199",
                    "--monitor-config", str(cfg), "--monitor-state", str(st), "--monitor-unit", "fixture"]

            def command(*args):
                if args[:2] == ("docker", "inspect"):
                    nap = args[2] == "fixture-n"
                    ports = {"6099/tcp": [{"HostIp": "127.0.0.1", "HostPort": "16099"}],
                             "3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "13000"}]} if nap else {
                                 "6185/tcp": [{"HostIp": "127.0.0.1", "HostPort": "16185"}]}
                    mounts = ["/AstrBot/data", "/app/napcat/config", "/app/.config/QQ"] if nap else ["/AstrBot/data"]
                    return json.dumps([{"State": {"Running": True}, "HostConfig": {
                        "RestartPolicy": {"Name": "unless-stopped"}, "PortBindings": ports,
                        "LogConfig": {"Type": "json-file", "Config": {"max-size": "10m", "max-file": "3"}}},
                        "Mounts": [{"Type": "bind", "RW": True, "Destination": dst} for dst in mounts],
                        "Config": {"Env": ["DO_NOT_PRINT=private-fixture-value"]}}])
                if args[1] == "show":
                    return "Result=success\nExecMainStatus=0\n"
                return "active" if args[1] == "is-active" else "enabled"

            for probe_result, expected in (("online", 0), ("offline", 1), ("unknown", 2)):
                output = io.StringIO()
                with patch.object(sys, "argv", argv), patch.object(v, "run", side_effect=command), \
                     patch.object(v.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(b"")), \
                     patch.object(v.monitor, "probe", return_value=(probe_result, "private-fixture-value")), \
                     patch.object(v.monitor, "onebot_connected", return_value=True), \
                     patch.object(v.os, "name", "nt"), contextlib.redirect_stdout(output):
                    self.assertEqual(v.main(), expected)
                self.assertNotIn("private-fixture-value", output.getvalue())
            with patch.object(sys, "argv", argv[:-6]), patch.object(v, "run", side_effect=command), \
                 patch.object(v.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(b"")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(v.main(), 0)  # base scope does not require Resend

            def disabled(*args):
                if args[:2] == ("systemctl", "is-enabled"):
                    raise subprocess.CalledProcessError(1, args, output="disabled\n")
                return command(*args)

            with patch.object(sys, "argv", argv[:-6]), patch.object(v, "run", side_effect=disabled), \
                 patch.object(v.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(b"")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(v.main(), 1)  # explicit disabled != insufficient evidence


if __name__ == "__main__":
    unittest.main()
