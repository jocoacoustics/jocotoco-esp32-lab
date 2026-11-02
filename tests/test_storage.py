"""Pruebas aisladas: datos ficticios solo en directorio temporal, nunca en la DB real."""

from pathlib import Path
import tempfile
import time
import unittest
import storage


class StorageTest(unittest.TestCase):
    def test_persistence_duplicate_networks_and_gaps(self):
        original = storage.DB
        try:
            with tempfile.TemporaryDirectory() as tmp:
                storage.DB = Path(tmp) / "test.sqlite3"
                storage.init()
                now = time.time()
                status = dict(rssi=-60, channel=6, client_count=1, uptime="00:01:00")
                storage.sample(now - 1, now, status, 1000, 2000, None, None)
                row = dict(ssid="TEST ONLY", channel=6, security="WPA2", rssi=-65)
                storage.scan(now - 1, now, [row, dict(row, rssi=-55)], True)
                storage.scan(now, now + 1, [], True)
                metrics = dict(
                    cpu=dict(valid=True, used_percent=25, core0_percent=40, core1_percent=10),
                    heap=dict(free_bytes=100, used_bytes=50, total_bytes=150),
                    flash=dict(active_image_bytes=1000, active_slot_bytes=1572864),
                )
                storage.metrics(now, metrics)
                h = storage.history(5)
                self.assertEqual(h["total_samples"], 1)
                self.assertEqual(h["total_scans"], 2)
                self.assertEqual(len(h["networks"][0]["points"]), 1)
                self.assertEqual(h["networks"][0]["last"], -55)
                self.assertEqual(h["networks"][0]["points"][0]["duplicates"], 2)
                self.assertEqual(len(h["scans"]), 2)
                self.assertEqual(h["device_metrics"][0]["cpu"], 25)
                self.assertEqual(h["device_metrics"][0]["heap_used"], 50)
                self.assertEqual(len(storage.export_json()["observations"]), 2)
                with storage.connect() as con:
                    self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 1)
        finally:
            storage.DB = original


if __name__ == "__main__":
    unittest.main()
