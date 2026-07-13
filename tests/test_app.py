import json
import threading
import unittest
from urllib.request import urlopen

from app import calculate_comparison, create_server, fetch_market_snapshot


class StubClient:
    def get_json(self, url, headers=None):
        if "api.nasdaq.com" in url:
            return {
                "data": {
                    "primaryData": {
                        "lastSalePrice": "$154.54",
                        "lastTradeTimestamp": "Jul 13, 2026 9:36 AM ET",
                        "isRealTime": True,
                    },
                    "marketStatus": "Open",
                }
            }
        if "polling.finance.naver.com" in url:
            return {
                "datas": [
                    {
                        "closePriceRaw": "1845000",
                        "marketStatus": "CLOSE",
                        "localTradedAt": "2026-07-13T15:30:00+09:00",
                    }
                ]
            }
        if "marketindex/exchange" in url:
            return [{"closePrice": "1,492.30", "localTradedAt": "2026-07-13"}]
        raise AssertionError(f"Unexpected URL: {url}")


class NasdaqFailureClient(StubClient):
    def get_json(self, url, headers=None):
        if "api.nasdaq.com" in url:
            raise OSError("Nasdaq temporarily unavailable")
        if "finance.yahoo.com" in url and "SKHY" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 153.21,
                                "regularMarketTime": 1783951200,
                                "marketState": "REGULAR",
                            }
                        }
                    ]
                }
            }
        return super().get_json(url, headers)


class NaverFailureClient(StubClient):
    def get_json(self, url, headers=None):
        if "polling.finance.naver.com" in url or "marketindex/exchange" in url:
            raise OSError("Naver temporarily unavailable")
        if "000660.KS" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 1_840_000,
                                "regularMarketTime": 1783917000,
                                "marketState": "CLOSED",
                            }
                        }
                    ]
                }
            }
        if "KRW%3DX" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 1490.5,
                                "regularMarketTime": 1783951200,
                                "marketState": "REGULAR",
                            }
                        }
                    ]
                }
            }
        return super().get_json(url, headers)


class ComparisonTests(unittest.TestCase):
    def test_calculates_adr_fair_value_and_premium(self):
        result = calculate_comparison(
            adr_price_usd=154.54,
            korean_share_price_krw=1_845_000,
            krw_per_usd=1_492.30,
            adrs_per_korean_share=10,
        )

        self.assertAlmostEqual(result["korean_share_usd"], 1236.346579, places=6)
        self.assertAlmostEqual(result["fair_adr_usd"], 123.634658, places=6)
        self.assertAlmostEqual(result["premium_percent"], 25.0, delta=0.01)
        self.assertAlmostEqual(result["price_difference_usd"], 30.905342, places=6)

    def test_supports_an_eleven_to_one_custom_ratio(self):
        result = calculate_comparison(
            adr_price_usd=154.54,
            korean_share_price_krw=1_845_000,
            krw_per_usd=1_492.30,
            adrs_per_korean_share=11,
        )

        self.assertAlmostEqual(result["fair_adr_usd"], 112.395144, places=6)

    def test_rejects_non_finite_values(self):
        for invalid_value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ValueError):
                    calculate_comparison(
                        adr_price_usd=invalid_value,
                        korean_share_price_krw=1_845_000,
                        krw_per_usd=1_492.30,
                    )


class MarketSnapshotTests(unittest.TestCase):
    def test_fetches_primary_quotes_and_calculates_comparison(self):
        snapshot = fetch_market_snapshot(StubClient())

        self.assertEqual(snapshot["quotes"]["adr"]["price"], 154.54)
        self.assertEqual(snapshot["quotes"]["adr"]["source"], "Nasdaq")
        self.assertEqual(snapshot["quotes"]["koreanShare"]["price"], 1_845_000)
        self.assertEqual(snapshot["quotes"]["fx"]["price"], 1_492.30)
        self.assertAlmostEqual(snapshot["comparison"]["premium_percent"], 25.0, delta=0.01)
        self.assertEqual(snapshot["errors"], [])

    def test_uses_fallback_when_nasdaq_is_unavailable(self):
        snapshot = fetch_market_snapshot(NasdaqFailureClient())

        self.assertEqual(snapshot["quotes"]["adr"]["price"], 153.21)
        self.assertEqual(snapshot["quotes"]["adr"]["source"], "Yahoo Finance (fallback)")
        self.assertEqual(snapshot["errors"], [])

    def test_uses_fallbacks_when_naver_is_unavailable(self):
        snapshot = fetch_market_snapshot(NaverFailureClient())

        self.assertEqual(snapshot["quotes"]["koreanShare"]["price"], 1_840_000)
        self.assertEqual(snapshot["quotes"]["fx"]["price"], 1490.5)
        self.assertEqual(
            snapshot["quotes"]["koreanShare"]["source"], "Yahoo Finance (fallback)"
        )
        self.assertEqual(snapshot["errors"], [])


class ApiTests(unittest.TestCase):
    def test_snapshot_endpoint_returns_market_data(self):
        server = create_server(port=0, client=StubClient())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            with urlopen(f"http://{host}:{port}/api/snapshot", timeout=2) as response:
                payload = json.load(response)

            self.assertEqual(response.status, 200)
            self.assertEqual(payload["quotes"]["adr"]["symbol"], "SKHY")
            self.assertIn("no-store", response.headers["Cache-Control"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

if __name__ == "__main__":
    unittest.main()
