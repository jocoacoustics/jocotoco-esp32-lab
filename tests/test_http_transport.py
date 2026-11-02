import unittest
import json
from unittest.mock import patch
from http_transport import parse_status, parse_scan, validate_host
from http_transport import Client


class HTTPTransportTest(unittest.TestCase):
    def test_status_rounding_and_missing_details(self):
        html = "<table><tr><td>SSID:</td><td>Jocotoco-Lab</td></tr><tr><td>Uplink:</td><td><strong>Connected (-69 dBm)</strong></td></tr><tr><td>STA IP:</td><td>192.168.1.50</td></tr><tr><td>AP Clients:</td><td>1</td></tr><tr><td>Bytes:</td><td>1023.0 KB sent / 3.8 MB received</td></tr></table>"
        status, tx, rx = parse_status(html)
        self.assertEqual(status["rssi"], -69)
        self.assertEqual(status["client_count"], 1)
        self.assertIsNone(status["channel"])
        self.assertEqual(status["clients"], [])
        self.assertEqual(tx, 1047552)
        self.assertEqual(rx, round(3.8 * 1024**2))

    def test_scan_unescapes_name_without_executing_html(self):
        rows, ok = parse_scan(
            "<table><tr><td>A &amp; B</td><td><span></span> -72 dBm</td><td>6</td><td>WPA2</td></tr></table>"
        )
        self.assertTrue(ok)
        self.assertEqual(rows[0]["ssid"], "A & B")
        self.assertEqual(rows[0]["rssi"], -72)
        self.assertFalse(parse_scan("Scanning...")[1])

    def test_only_local_ip_targets(self):
        self.assertEqual(validate_host("192.168.1.50"), "192.168.1.50")
        for host in ("8.8.8.8", "127.0.0.1", "169.254.1.1", "example.com", "192.168.1.50/path"):
            with self.assertRaises(ValueError):
                validate_host(host)

    def test_metrics_rejects_invalid_usage_and_inconsistent_heap(self):
        data = dict(
            schema=1,
            cpu=dict(valid=True, used_percent=25, core0_percent=40, core1_percent=10),
            heap=dict(free_bytes=100, used_bytes=50, total_bytes=150),
            flash={},
        )
        client = Client("192.168.1.50")
        with patch.object(client, "get", return_value=json.dumps(data)):
            self.assertEqual(client.metrics()["heap"]["free_bytes"], 100)
        data["cpu"]["used_percent"] = 120
        with patch.object(client, "get", return_value=json.dumps(data)):
            with self.assertRaises(ValueError):
                client.metrics()
        data["cpu"]["used_percent"] = 25
        data["heap"]["total_bytes"] = 200
        with patch.object(client, "get", return_value=json.dumps(data)):
            with self.assertRaises(ValueError):
                client.metrics()


if __name__ == "__main__":
    unittest.main()
