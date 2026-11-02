import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from server import Handler


class StaticDashboardTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_page_references_served_assets(self):
        with self.client.open(self.base + "/") as response:
            html = response.read().decode()
        self.assertIn("/styles.css", html)
        self.assertIn("/main.js", html)
        for asset in ("main.js", "history.js", "network.js", "health.js", "styles.css"):
            with self.client.open(self.base + "/" + asset) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 100)

    def test_arbitrary_files_are_not_served(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.client.open(self.base + "/README.md")
        self.assertEqual(error.exception.code, 404)
