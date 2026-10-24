"""Exercise actual verifier scopes without Docker, Cloudflare or Resend."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("scope_verifier", Path(__file__).with_name("verify.py"))
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Tests(unittest.TestCase):
    def execute(self, kind, extra=()):
        commands, requests = [], []
        webui = 5099 if kind == "snowluma" else 6099

        def run(*args):
            commands.append(args)
            if args[:2] == ("docker", "inspect"):
                gateway = args[2] == "fixture-gateway"
                ports = {str(webui) + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(webui)}], "3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]} if gateway else {"6185/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6185"}]}
                mounts = (["/app/data", "/app/.config", "/app/.local/share"] if kind == "snowluma" else ["/AstrBot/data", "/app/napcat/config", "/app/.config/QQ"]) if gateway else ["/AstrBot/data"]
                return json.dumps([{"State": {"Running": True}, "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}, "PortBindings": ports, "ShmSize": 1073741824, "CapAdd": ["SYS_PTRACE"], "SecurityOpt": ["seccomp=unconfined"], "LogConfig": {"Type": "json-file", "Config": {"max-size": "10m", "max-file": "3"}}}, "Mounts": [{"Type": "bind", "RW": True, "Destination": p} for p in mounts]}])
            if args[1] == "show":
                return "Result=success\nExecMainStatus=0\n"
            return "active" if args[1] == "is-active" else "enabled"

        def request(url, **kwargs):
            requests.append(url)
            return Response(b"")

        argv = ["verify.py", "--gateway-type", kind, "--gateway", "fixture-gateway", "--astrbot", "fixture-astrbot", "--gateway-webui-port", str(webui), "--astrbot-webui-port", "6185", "--onebot-http-port", "3000", "--onebot-ws-port", "6199", *extra]
        with patch.object(sys, "argv", argv), patch.object(verify, "run", side_effect=run), patch.object(verify.urllib.request, "urlopen", side_effect=request), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                result = verify.main()
            except SystemExit as exc:
                result = exc.code
        return result, commands, requests

    def test_snowluma_base_requires_neither_domain_nor_mail_credentials(self):
        result, commands, requests = self.execute("snowluma")
        self.assertEqual(result, 0)
        self.assertEqual({c[-1] for c in commands if c[0] == "systemctl"}, {"docker"})
        self.assertTrue(all(url.startswith("http://127.0.0.1:") for url in requests))

    def test_napcat_new_aliases_work_without_optional_services(self):
        self.assertEqual(self.execute("napcat")[0], 0)

    def test_domain_only_adds_tunnel_checks_without_mail_config(self):
        result, commands, _ = self.execute("snowluma", ["--cloudflared-unit", "fixture-tunnel"])
        self.assertEqual(result, 0)
        self.assertEqual({c[-1] for c in commands if c[0] == "systemctl"}, {"docker", "fixture-tunnel"})

    def test_mail_only_does_not_require_cloudflare(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            config = {"gateway_type": "snowluma", "gateway_container": "fixture-gateway", "astrbot_container": "fixture-astrbot", "http_url": "http://127.0.0.1:3000", "token_file": str(base / "token"), "qq_user_id": "123456", "onebot_ws_port": 6199, "resend_api_key_file": str(base / "key"), "resend_from": "sender@example.invalid", "resend_to": "recipient@example.invalid"}
            cfg, state = base / "config.json", base / "state.json"
            cfg.write_text(json.dumps(config))
            state.write_text(json.dumps({"last_probe_at": time.time(), "pending": []}))
            with patch.object(verify.os, "name", "nt"), patch.object(verify.monitor, "probe", return_value=("online", "fixture")), patch.object(verify.monitor, "onebot_connected", return_value=True):
                result, commands, requests = self.execute("snowluma", ["--monitor-config", str(cfg), "--monitor-state", str(state), "--monitor-unit", "fixture-monitor"])
            self.assertEqual(result, 0)
            units = {c[-1] for c in commands if c[0] == "systemctl" and c[1] != "show"}
            self.assertEqual(units, {"docker", "fixture-monitor.timer"})
            self.assertTrue(all(url.startswith("http://127.0.0.1:") for url in requests))


if __name__ == "__main__":
    unittest.main()
