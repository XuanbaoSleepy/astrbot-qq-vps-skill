"""Offline acceptance fixtures; never contact QQ, Docker or Resend."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import qq_monitor as core
monitor = core


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Tests(unittest.TestCase):
    config = {"gateway_type": "snowluma", "qq_user_id": "123456", "gateway_container": "fixture-gateway"}

    def online_api(self, config, action, body):
        if action == "get_status":
            return {"online": True, "good": True}
        return {"user_id": 123456}

    def test_online_confirms_recovery_and_clears_old_closed_latch(self):
        state = {"session_closed": True}
        with patch.object(core, "run", return_value=""), patch.object(core, "api", side_effect=self.online_api), patch.object(core, "onebot_connected", return_value=True):
            self.assertEqual(monitor.probe(self.config, state)[0], "online")
        self.assertFalse(state["session_closed"])

    def test_closed_target_session_and_missing_http_is_offline(self):
        log = "2026-01-01T00:00:01Z [onebot] session closed: UIN=123456\n"
        with patch.object(core, "run", return_value=log), patch.object(core, "api", side_effect=urllib.error.URLError("fixture-private-detail")):
            self.assertEqual(monitor.probe(self.config, {})[0], "offline")

    def test_other_account_does_not_latch_target_closed(self):
        state = {}
        log = "2026-01-01T00:00:01Z session closed: UIN=1234567\n"
        with patch.object(core, "run", return_value=log), patch.object(core, "api", side_effect=urllib.error.URLError("fixture")):
            monitor.probe(self.config, state)
        self.assertFalse(state.get("session_closed", False))
        self.assertEqual(state.get("log_cursor"), "2026-01-01T00:00:01Z")

    def test_late_older_logs_do_not_reapply_a_closed_session(self):
        state = {"log_cursor": "2026-01-01T00:00:02Z", "session_closed": False}
        log = "2026-01-01T00:00:01Z session closed: UIN=123456\n"
        with patch.object(core, "run", return_value=log), patch.object(core, "api", side_effect=urllib.error.URLError("fixture")):
            monitor.probe(self.config, state)
        self.assertFalse(state["session_closed"])
        self.assertEqual(state["log_cursor"], "2026-01-01T00:00:02Z")

    def test_wrong_account_is_offline(self):
        def api(config, action, body):
            return {"online": True, "good": True} if action == "get_status" else {"user_id": 999999}
        with patch.object(core, "run", return_value=""), patch.object(core, "api", side_effect=api):
            self.assertEqual(monitor.probe(self.config, {})[0], "offline")

    def test_explicit_offline_status_is_offline(self):
        with patch.object(core, "run", return_value=""), patch.object(core, "api", return_value={"online": False, "good": False}):
            self.assertEqual(monitor.probe(self.config, {})[0], "offline")

    def test_unknown_status_schema_does_not_claim_offline(self):
        with patch.object(core, "run", return_value=""), patch.object(core, "api", return_value={}):
            result, reason = monitor.probe(self.config, {})
        self.assertEqual(result, "unknown")

    def test_http_failure_without_session_evidence_is_unknown(self):
        with patch.object(core, "run", return_value=""), patch.object(core, "api", side_effect=urllib.error.URLError("fixture-private-detail")):
            result, reason = monitor.probe(self.config, {})
        self.assertEqual(result, "unknown")
        self.assertNotIn("fixture-private-detail", reason)

    def test_log_failure_does_not_hide_healthy_http(self):
        with patch.object(core, "run", side_effect=OSError("fixture-private-detail")), patch.object(core, "api", side_effect=self.online_api), patch.object(core, "onebot_connected", return_value=False):
            self.assertEqual(monitor.probe(self.config, {})[0], "online")

    def test_confirmed_drop_deduplicates_and_recovery_needs_two_samples(self):
        state = {"phase": "online", "bad_count": 0, "good_count": 2, "pending": [], "session_closed": True}
        with patch.object(core, "run", return_value=""), patch.object(core, "api", side_effect=urllib.error.URLError("fixture")):
            for i in range(7):
                result, reason = monitor.probe(self.config, state)
                core.transition(state, result, reason, 10000 + i * 120)
        self.assertEqual([e["name"] for e in state["pending"]], ["QQ_LOGIN_LOST"])
        with patch.object(core, "run", return_value=""), patch.object(core, "api", side_effect=self.online_api), patch.object(core, "onebot_connected", return_value=True):
            for i in range(2):
                result, reason = monitor.probe(self.config, state)
                core.transition(state, result, reason, 12000 + i * 120)
        self.assertEqual([e["name"] for e in state["pending"]], ["QQ_LOGIN_LOST", "QQ_LOGIN_RESTORED"])

    def test_snowluma_mail_label_preserves_known_working_user_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "key"
            key.write_text("fixture-key")
            config = {"resend_to": "to@example.invalid", "resend_from": "from@example.invalid", "resend_api_key_file": str(key), "gateway_label": "SnowLuma"}
            captured = []
            def send(request, timeout):
                captured.append(request)
                return Response(b'{"id":"fixture-mail-id"}')
            with patch.object(core.urllib.request, "urlopen", side_effect=send):
                core.send_resend(config, None, test=True)
                core.send_resend(config, {"name": "QQ_LOGIN_LOST", "reason": "fixture", "occurred_at": 1})
            for request in captured:
                self.assertEqual(request.get_header("User-agent"), "NapCatMonitor/1.0")
                self.assertIn("SnowLuma", json.loads(request.data)["subject"])

    def test_unknown_gateway_is_rejected(self):
        with self.assertRaises(ValueError):
            monitor.probe({**self.config, "gateway_type": "unsupported"}, {})

    def test_conflicting_old_and_new_container_names_are_rejected(self):
        with self.assertRaises(ValueError):
            core.validate_probe_config({**self.config, "napcat_container": "different-gateway"})


if __name__ == "__main__":
    unittest.main()
