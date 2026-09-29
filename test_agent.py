import http.client
import importlib.util
import json
import os
import re
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": cls.temp.name}):
            spec = importlib.util.spec_from_file_location("pc_agent", ROOT / "agent.py")
            cls.agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.agent)
        cls.actions = cls.agent.actions
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.agent.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers or {})
        res = conn.getresponse()
        result = (res.status, json.loads(res.read()))
        conn.close()
        return result

    def action_headers(self):
        host = f"127.0.0.1:{self.server.server_port}"
        return {"Authorization": "Bearer " + self.agent.SECRET, "Origin": "http://" + host}

    def test_auth_and_origin_required_for_action(self):
        host = f"127.0.0.1:{self.server.server_port}"
        with patch.object(self.actions, "run") as cmd:
            self.assertEqual(self.request("POST", "/api/lock", {}, {"Origin": "http://" + host})[0], 403)
            self.assertEqual(self.request("POST", "/api/lock", {}, {"Authorization": "Bearer " + self.agent.SECRET, "Origin": "https://evil.example"})[0], 403)
            cmd.assert_not_called()

    def test_allowlist_and_volume_validation(self):
        headers = self.action_headers()
        with patch.object(self.actions, "run") as cmd:
            self.assertEqual(self.request("POST", "/api/run", {"command": "id"}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": "; id"}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": True}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": 101}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": 42}, headers)[0], 200)
            cmd.assert_called_once_with(["wpctl", "set-volume", "@DEFAULT_SINK@", "42%"])

    def test_ddc_monitor_must_be_discovered(self):
        with patch.object(self.actions, "monitors", return_value=[{"id": 1, "name": "Test"}]), patch.object(self.actions, "run") as cmd:
            with self.assertRaises(ValueError):
                self.agent.dispatch("monitor-standby", {"id": 2})
            cmd.assert_not_called()
            self.agent.dispatch("monitor-standby", {"id": 1})
            cmd.assert_called_once_with(["ddcutil", "setvcp", "d6", "04", "--display", "1"], 20)

    def test_actions_without_body_reject_arguments(self):
        headers = self.action_headers()
        with patch.object(self.actions, "run") as cmd:
            self.assertEqual(self.request("POST", "/api/lock", {"command": "id"}, headers)[0], 400)
            cmd.assert_not_called()
            self.assertEqual(self.request("POST", "/api/lock", {}, headers)[0], 200)
            cmd.assert_called_once_with(["loginctl", "lock-sessions"])

    def test_screen_actions_require_x11_display(self):
        with patch.dict(os.environ), patch.object(self.actions, "run") as cmd:
            os.environ.pop("DISPLAY", None)
            self.assertEqual(self.request("POST", "/api/screens-off", {}, self.action_headers())[0], 503)
            cmd.assert_not_called()

    def test_every_registered_action_dispatches(self):
        bodies = {"volume": {"value": 10}, "monitor-standby": {"id": 1}, "monitor-on": {"id": 1}}
        with patch.dict(os.environ, {"DISPLAY": ":0"}), \
                patch.object(self.actions, "monitors", return_value=[{"id": 1, "name": "Test"}]), \
                patch.object(self.actions, "run") as cmd:
            for name, entry in self.actions.ACTIONS.items():
                with self.subTest(action=name):
                    self.assertEqual(entry.needs_body, name in bodies, "give each body action a valid sample body")
                    cmd.reset_mock()
                    self.assertTrue(self.agent.dispatch(name, bodies.get(name, {}))["ok"])
                    cmd.assert_called()

    def test_status_reports_api_identity(self):
        self.assertEqual(self.request("GET", "/api/status")[0], 401)
        with patch.object(self.actions, "audio", return_value={"available": False}), \
                patch.object(self.actions, "monitors", return_value=[]):
            code, status = self.request("GET", "/api/status", headers={"Authorization": "Bearer " + self.agent.SECRET})
        self.assertEqual(code, 200)
        self.assertEqual(status["api"], "1")
        self.assertEqual(status["platform"], "linux")
        self.assertEqual(status["screens"], status["x11"])
        self.assertEqual(status["device"], socket.gethostname())
        self.assertEqual(status["actions"], list(self.actions.ACTIONS))
        self.assertLessEqual({"lock", "mute", "unmute", "volume", "screens-off", "screens-on",
                              "monitor-standby", "monitor-on", "leaving"}, set(status["actions"]))

    def test_install_copies_every_runtime_file(self):
        match = re.search(r"^files=\(([^)]*)\)$", (ROOT / "install.sh").read_text(), re.M)
        self.assertIsNotNone(match, "install.sh must declare files=(...)")
        runtime = {p.name for p in ROOT.glob("*.py") if not p.name.startswith("test_")} | {"index.html"}
        self.assertLessEqual(runtime, set(match.group(1).split()))


class WindowsActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("windows_actions", ROOT / "windows_actions.py")
        cls.win = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.win)

    def test_windows_actions_are_the_shared_set_without_monitors(self):
        self.assertEqual(set(self.win.ACTIONS),
                         {"lock", "mute", "unmute", "volume", "screens-off", "screens-on", "leaving"})
        self.assertEqual(self.win.monitors(), [])
        self.assertFalse(self.win.x11_available())
        self.assertFalse(self.win.screens_available())

    def test_volume_stays_a_fixed_script_argument(self):
        script = str(ROOT / "windows_audio.ps1")
        expected = ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
                    "-File", script, "-Action", "set", "-Value", "42"]
        with patch.object(self.win, "run") as cmd:
            self.assertEqual(self.win.set_volume({"value": 42}), None)
            cmd.assert_called_once_with(expected)
            cmd.reset_mock()
            with self.assertRaises(ValueError):
                self.win.set_volume({"value": "; id"})
            with self.assertRaises(ValueError):
                self.win.set_volume({"value": True})
            cmd.assert_not_called()
        text = (ROOT / "windows_audio.ps1").read_text()
        self.assertIn("ValidateSet('get', 'set', 'mute', 'unmute')", text)
        self.assertNotIn("Invoke-Expression", text)

    def test_leaving_mutes_locks_and_turns_screens_off(self):
        with patch.object(self.win, "run") as cmd, \
                patch.object(self.win, "lock_workstation") as lock, \
                patch.object(self.win, "set_screen_power") as screens:
            result = self.win.leaving()
        self.assertTrue(result["ok"])
        self.assertEqual(result["warnings"], [])
        cmd.assert_called_once()
        self.assertEqual(cmd.call_args.args[0][cmd.call_args.args[0].index("-Action") + 1], "mute")
        lock.assert_called_once_with()
        screens.assert_called_once_with("off")

    def test_windows_installer_copies_the_audio_script(self):
        text = (ROOT / "install.ps1").read_text()
        for name in ("agent.py", "windows_actions.py", "windows_audio.ps1", "index.html"):
            self.assertIn(name, text)
        self.assertIn("https://www.python.org/ftp/python/", text)
        self.assertIn("https://pkgs.tailscale.com/stable/", text)
        self.assertIn("Python Software Foundation", text)
        self.assertIn("127.0.0.1:8765", text)
        self.assertNotIn("invoke-expression", text.lower())
        self.assertNotIn("| iex", text.lower())
        self.assertNotIn("tailscale funnel", text.lower())
        self.assertIn("/#token=", text)
        self.assertIn("BackendState", text)
        self.assertIn("serve status", text)
        page = (ROOT / "index.html").read_text()
        self.assertIn("URLSearchParams", page)
        self.assertIn("replaceState", page)
        self.assertIn("localStorage", page)
        self.assertNotIn("sessionStorage.setItem", page)
        self.assertIn("status === 401", page)

    def test_public_installers_download_this_repo(self):
        linux = (ROOT / "site" / "install.sh").read_text()
        windows = (ROOT / "site" / "install.ps1").read_text()
        page = (ROOT / "site" / "index.html").read_text()
        self.assertIn("sauravsvt/pc-remote-ubuntu-mvp", linux)
        self.assertIn('bash "$src/install.sh"', linux)
        self.assertIn("sauravsvt/pc-remote-ubuntu-mvp", windows)
        self.assertIn("install.ps1", windows)
        self.assertIn("https://pcremote.voxonlabs.com/install.sh", page)
        self.assertIn("https://tailscale.com/download", page)
        self.assertIn("tailscale serve --bg http://127.0.0.1:8765", page)


if __name__ == "__main__":
    unittest.main()
