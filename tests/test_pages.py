import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            self.assertIn('id="adminRefreshButton"', index)
            self.assertIn(
                "https://github.com/Yubuilding/skhy_compare/actions/workflows/deploy-pages.yml",
                index,
            )
            self.assertTrue((output / "app.js").is_file())
            self.assertTrue((output / "admin-refresh.mjs").is_file())
            self.assertTrue((output / "history-charts.mjs").is_file())
            self.assertTrue((output / "market-funds.mjs").is_file())
            self.assertEqual(snapshot["quotes"]["adr"]["symbol"], "SKHY")
            self.assertEqual(history["foreignFlow"][-1]["netShares"], -704_671)
            self.assertEqual(len(history["premiumInputs"]), 2)
            self.assertEqual(history["marketFunds"][-1]["date"], "2026-07-10")

    def test_rejects_incomplete_snapshot_without_replacing_last_good_build(self):
        incomplete_snapshot = {
            "fetchedAt": "2026-07-14T00:00:00+00:00",
            "ratio": 11,
            "quotes": {},
            "foreignFlow": None,
            "comparison": None,
            "errors": [{"field": "adr", "message": "provider unavailable"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            output.mkdir()
            sentinel = output / "last-good.txt"
            sentinel.write_text("keep me", encoding="utf-8")

            with patch("build_pages.fetch_market_snapshot", return_value=incomplete_snapshot):
                with self.assertRaisesRegex(RuntimeError, "critical market data"):
                    build_pages(output, client=HistoryStubClient())

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me")


if __name__ == "__main__":
    unittest.main()
