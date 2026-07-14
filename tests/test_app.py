import json
import threading
import unittest
from urllib.request import urlopen

from app import calculate_comparison, create_server, fetch_market_snapshot


FOREIGN_FLOW_HTML = """
<em class="date">2026.07.14 13:19 <span>기준(KRX 장중)</span></em>
<h4><strong>거래원정보 <em>(<span>20</span>분 지연)</em></strong></h4>
<tr class="total">
  <td><span>외국계추정합</span></td>
  <td><span>613,794</span></td>
  <td><span>79,538</span></td>
  <td><span>693,332</span></td>
</tr>
<p>당일 종목별 매매상위 5개 회원사 정보를 이용한 추정치임</p>
"""


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

    def get_text(self, url, headers=None):
        if "finance.naver.com/item/frgn.naver" in url:
            return FOREIGN_FLOW_HTML
        raise AssertionError(f"Unexpected URL: {url}")

    def get_overnight_quote(self, symbol):
        return {
            "price": 152.10,
            "currency": "USD",
            "symbol": symbol,
            "source": "TradingView / BOATS",
            "timestamp": "2026-07-13T03:59:00-04:00",
            "marketStatus": "CLOSED",
            "isRealTime": True,
            "session": "OVERNIGHT",
        }


class ActiveOvernightClient(StubClient):
    def get_overnight_quote(self, symbol):
        quote = super().get_overnight_quote(symbol)
        quote.update(
            {
                "price": 156.80,
                "timestamp": "2026-07-13T22:15:30-04:00",
                "marketStatus": "OPEN",
            }
        )
        return quote


class FailedOvernightClient(StubClient):
    def get_overnight_quote(self, symbol):
        raise OSError("BOATS temporarily unavailable")


class FailedRegularActiveOvernightClient(ActiveOvernightClient):
    def get_json(self, url, headers=None):
        if "api.nasdaq.com" in url or (
            "finance.yahoo.com" in url and "SKHY" in url
        ):
            raise OSError("Regular quote temporarily unavailable")
        return super().get_json(url, headers)


class FailedRegularClosedOvernightClient(StubClient):
    def get_json(self, url, headers=None):
        if "api.nasdaq.com" in url or (
            "finance.yahoo.com" in url and "SKHY" in url
        ):
            raise OSError("Regular quote temporarily unavailable")
        return super().get_json(url, headers)


class MalformedForeignFlowClient(StubClient):
    def get_text(self, url, headers=None):
        return super().get_text(url, headers).replace("79,538", "88,888")


class YahooPostMarketClient(StubClient):
    def get_json(self, url, headers=None):
        if "api.nasdaq.com" in url:
            raise OSError("Nasdaq temporarily unavailable")
        if "finance.yahoo.com" in url and "SKHY" in url:
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 154.54,
                                "regularMarketTime": 1783951200,
                                "postMarketPrice": 155.61,
                                "postMarketTime": 1783970100,
                                "marketState": "POST",
                                "exchangeDataDelayedBy": 0,
                            }
                        }
                    ]
                }
            }
        return super().get_json(url, headers)


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
    def test_includes_todays_intraday_foreign_broker_flow_estimate(self):
        snapshot = fetch_market_snapshot(StubClient())

        flow = snapshot["foreignFlow"]
        self.assertEqual(flow["netShares"], 79_538)
        self.assertEqual(flow["buyShares"], 693_332)
        self.assertEqual(flow["sellShares"], 613_794)
        self.assertEqual(flow["direction"], "NET_BUY")
        self.assertEqual(flow["timestamp"], "2026-07-14T13:19:00+09:00")
        self.assertEqual(flow["delayMinutes"], 20)
        self.assertTrue(flow["isEstimate"])

    def test_rejects_inconsistent_flow_without_breaking_price_comparison(self):
        snapshot = fetch_market_snapshot(MalformedForeignFlowClient())

        self.assertIsNone(snapshot["foreignFlow"])
        self.assertIsNotNone(snapshot["comparison"])
        self.assertEqual(snapshot["errors"][0]["field"], "foreignFlow")
        self.assertIn("inconsistent", snapshot["errors"][0]["message"])

    def test_fetches_primary_quotes_and_calculates_comparison(self):
        snapshot = fetch_market_snapshot(StubClient())

        self.assertEqual(snapshot["quotes"]["adr"]["price"], 154.54)
        self.assertEqual(snapshot["quotes"]["adr"]["source"], "Nasdaq")
        self.assertEqual(snapshot["quotes"]["koreanShare"]["price"], 1_845_000)
        self.assertEqual(snapshot["quotes"]["fx"]["price"], 1_492.30)
        self.assertAlmostEqual(snapshot["comparison"]["premium_percent"], 25.0, delta=0.01)
        self.assertEqual(snapshot["errors"], [])

    def test_uses_live_overnight_price_when_boats_session_is_open(self):
        snapshot = fetch_market_snapshot(ActiveOvernightClient())

        adr = snapshot["quotes"]["adr"]
        self.assertEqual(adr["price"], 156.80)
        self.assertEqual(adr["session"], "OVERNIGHT")
        self.assertEqual(adr["source"], "TradingView / BOATS")
        self.assertEqual(adr["sessions"]["regular"]["price"], 154.54)
        self.assertEqual(adr["sessions"]["overnight"]["price"], 156.80)
        expected = calculate_comparison(156.80, 1_845_000, 1_492.30)
        self.assertAlmostEqual(
            snapshot["comparison"]["premium_percent"], expected["premium_percent"]
        )

    def test_falls_back_to_regular_price_when_overnight_feed_fails(self):
        snapshot = fetch_market_snapshot(FailedOvernightClient())

        adr = snapshot["quotes"]["adr"]
        self.assertEqual(adr["price"], 154.54)
        self.assertEqual(adr["session"], "REGULAR")
        self.assertIn("temporarily unavailable", adr["overnightError"])
        self.assertIsNone(adr["sessions"]["overnight"])
        self.assertEqual(snapshot["errors"], [])

    def test_live_overnight_price_survives_regular_feed_failure(self):
        snapshot = fetch_market_snapshot(FailedRegularActiveOvernightClient())

        adr = snapshot["quotes"]["adr"]
        self.assertEqual(adr["price"], 156.80)
        self.assertEqual(adr["session"], "OVERNIGHT")
        self.assertIsNone(adr["sessions"]["regular"])
        self.assertIn("temporarily unavailable", adr["regularError"])
        self.assertEqual(snapshot["errors"], [])

    def test_uses_last_overnight_trade_when_both_live_sessions_are_unavailable(self):
        snapshot = fetch_market_snapshot(FailedRegularClosedOvernightClient())

        adr = snapshot["quotes"]["adr"]
        self.assertEqual(adr["price"], 152.10)
        self.assertEqual(adr["session"], "OVERNIGHT")
        self.assertEqual(adr["marketStatus"], "CLOSED")
        self.assertIn("latest overnight", adr["fallbackReason"])
        self.assertEqual(snapshot["errors"], [])

    def test_uses_postmarket_price_instead_of_mislabeling_regular_close(self):
        snapshot = fetch_market_snapshot(YahooPostMarketClient())

        adr = snapshot["quotes"]["adr"]
        self.assertEqual(adr["price"], 155.61)
        self.assertEqual(adr["session"], "AFTER_HOURS")
        self.assertEqual(adr["marketStatus"], "POST")
        self.assertTrue(adr["isRealTime"])

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
