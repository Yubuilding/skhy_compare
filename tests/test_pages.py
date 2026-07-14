import json
import tempfile
import unittest
from pathlib import Path

from build_pages import build_pages
from tests.test_app import HistoryStubClient


class PagesBuildTests(unittest.TestCase):
    def test_builds_static_site_with_snapshot_and_history_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_pages(output, client=HistoryStubClient())

            index = (output / "index.html").read_text(encoding="utf-8")
            snapshot = json.loads((output / "data" / "snapshot.json").read_text())
            history = json.loads((output / "data" / "history.json").read_text())

            self.assertIn('name="data-mode" content="static"', index)
            self.assertTrue((output / "app.js").is_file())
            self.assertTrue((output / "history-charts.mjs").is_file())
            self.assertEqual(snapshot["quotes"]["adr"]["symbol"], "SKHY")
            self.assertEqual(history["foreignFlow"][-1]["netShares"], -704_671)
            self.assertEqual(len(history["premiumInputs"]), 2)


if __name__ == "__main__":
    unittest.main()
