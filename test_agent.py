import http.client
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": cls.temp.name}):
            spec = importlib.util.spec_from_file_location("pc_agent", Path(__file__).with_name("agent.py"))
            cls.agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.agent)
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

    def test_auth_and_origin_required_for_action(self):
        host = f"127.0.0.1:{self.server.server_port}"
        with patch.object(self.agent, "run") as cmd:
            self.assertEqual(self.request("POST", "/api/lock", {}, {"Origin": "http://" + host})[0], 403)
            self.assertEqual(self.request("POST", "/api/lock", {}, {"Authorization": "Bearer " + self.agent.SECRET, "Origin": "https://evil.example"})[0], 403)
            cmd.assert_not_called()

    def test_allowlist_and_volume_validation(self):
        host = f"127.0.0.1:{self.server.server_port}"
        headers = {"Authorization": "Bearer " + self.agent.SECRET, "Origin": "http://" + host}
        with patch.object(self.agent, "run") as cmd:
            self.assertEqual(self.request("POST", "/api/run", {"command": "id"}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": "; id"}, headers)[0], 400)
            self.assertEqual(self.request("POST", "/api/volume", {"value": 42}, headers)[0], 200)
            cmd.assert_called_once_with(["wpctl", "set-volume", "@DEFAULT_SINK@", "42%"])

    def test_ddc_monitor_must_be_discovered(self):
        with patch.object(self.agent, "monitors", return_value=[{"id": 1, "name": "Test"}]), patch.object(self.agent, "run") as cmd:
            with self.assertRaises(ValueError):
                self.agent.action("monitor-standby", {"id": 2})
            cmd.assert_not_called()
            self.agent.action("monitor-standby", {"id": 1})
            cmd.assert_called_once_with(["ddcutil", "setvcp", "d6", "04", "--display", "1"], 20)


if __name__ == "__main__":
    unittest.main()
