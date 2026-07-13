#!/usr/bin/env python3
"""Local SK hynix ADR premium calculator."""

import argparse
import json
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


NASDAQ_QUOTE_URL = "https://api.nasdaq.com/api/quote/SKHY/info?assetclass=stocks"
NAVER_STOCK_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/000660"
NAVER_FX_URL = (
    "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=1"
)
YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
DATA_ERRORS = (KeyError, IndexError, TypeError, ValueError, OSError)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class JsonHttpClient:
    """Small JSON HTTP client using only the Python standard library."""

    def __init__(self, timeout=8):
        self.timeout = timeout

    def get_json(self, url, headers=None):
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SKHY-Compare/1.0",
        }
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))


def calculate_comparison(
    adr_price_usd,
    korean_share_price_krw,
    krw_per_usd,
    adrs_per_korean_share=10,
):
    """Return the USD-equivalent values and ADR premium for positive inputs."""
    values = (
        adr_price_usd,
        korean_share_price_krw,
        krw_per_usd,
        adrs_per_korean_share,
    )
    if any(not isinstance(value, (int, float)) or value <= 0 for value in values):
        raise ValueError("All prices, the exchange rate, and the ADR ratio must be positive")

    korean_share_usd = korean_share_price_krw / krw_per_usd
    fair_adr_usd = korean_share_usd / adrs_per_korean_share
    price_difference_usd = adr_price_usd - fair_adr_usd
    premium_percent = (adr_price_usd / fair_adr_usd - 1) * 100
    return {
        "korean_share_usd": korean_share_usd,
        "fair_adr_usd": fair_adr_usd,
        "price_difference_usd": price_difference_usd,
        "premium_percent": premium_percent,
    }


def _parse_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError("Market value is not numeric")
    return float(value.replace("$", "").replace(",", "").strip())


def _fetch_adr_quote(client):
    try:
        payload = client.get_json(
            NASDAQ_QUOTE_URL,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        data = payload["data"]
        primary = data["primaryData"]
        return {
            "price": _parse_number(primary["lastSalePrice"]),
            "currency": "USD",
            "symbol": "SKHY",
            "source": "Nasdaq",
            "timestamp": primary.get("lastTradeTimestamp"),
            "marketStatus": data.get("marketStatus"),
            "isRealTime": bool(primary.get("isRealTime")),
        }
    except DATA_ERRORS:
        payload = client.get_json(
            YAHOO_CHART_URL.format(symbol="SKHY"),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        meta = payload["chart"]["result"][0]["meta"]
        timestamp = meta.get("regularMarketTime")
        if timestamp:
            timestamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        market_status = meta.get("marketState")
        return {
            "price": _parse_number(meta["regularMarketPrice"]),
            "currency": "USD",
            "symbol": "SKHY",
            "source": "Yahoo Finance (fallback)",
            "timestamp": timestamp,
            "marketStatus": market_status,
            "isRealTime": market_status == "REGULAR",
        }


def _fetch_korean_quote(client):
    try:
        payload = client.get_json(
            NAVER_STOCK_URL,
            headers={"Referer": "https://finance.naver.com/", "User-Agent": "Mozilla/5.0"},
        )
        data = payload["datas"][0]
        return {
            "price": _parse_number(data.get("closePriceRaw", data.get("closePrice"))),
            "currency": "KRW",
            "symbol": "000660",
            "source": "Naver Finance",
            "timestamp": data.get("localTradedAt"),
            "marketStatus": data.get("marketStatus"),
            "isRealTime": data.get("marketStatus") == "OPEN",
        }
    except DATA_ERRORS:
        meta = _fetch_yahoo_meta(client, "000660.KS")
        market_status = meta.get("marketState")
        return {
            "price": _parse_number(meta["regularMarketPrice"]),
            "currency": "KRW",
            "symbol": "000660",
            "source": "Yahoo Finance (fallback)",
            "timestamp": _yahoo_timestamp(meta),
            "marketStatus": market_status,
            "isRealTime": market_status == "REGULAR",
        }


def _fetch_fx_quote(client):
    try:
        payload = client.get_json(
            NAVER_FX_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = payload[0]
        return {
            "price": _parse_number(data["closePrice"]),
            "currency": "KRW per USD",
            "symbol": "USD/KRW",
            "source": "Naver Finance",
            "timestamp": data.get("localTradedAt"),
            "marketStatus": None,
            "isRealTime": False,
        }
    except DATA_ERRORS:
        meta = _fetch_yahoo_meta(client, "KRW=X")
        market_status = meta.get("marketState")
        return {
            "price": _parse_number(meta["regularMarketPrice"]),
            "currency": "KRW per USD",
            "symbol": "USD/KRW",
            "source": "Yahoo Finance (fallback)",
            "timestamp": _yahoo_timestamp(meta),
            "marketStatus": market_status,
            "isRealTime": market_status == "REGULAR",
        }


def _fetch_yahoo_meta(client, symbol):
    payload = client.get_json(
        YAHOO_CHART_URL.format(symbol=quote(symbol, safe=".")),
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return payload["chart"]["result"][0]["meta"]


def _yahoo_timestamp(meta):
    timestamp = meta.get("regularMarketTime")
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def fetch_market_snapshot(client=None):
    """Fetch all three market inputs and return a comparison snapshot."""
    client = client or JsonHttpClient()
    providers = {
        "adr": _fetch_adr_quote,
        "koreanShare": _fetch_korean_quote,
        "fx": _fetch_fx_quote,
    }
    quotes = {}
    errors = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = {executor.submit(provider, client): key for key, provider in providers.items()}
        for future in as_completed(pending):
            key = pending[future]
            try:
                quotes[key] = future.result()
            except DATA_ERRORS as error:
                errors.append({"field": key, "message": str(error)})

    comparison = None
    if len(quotes) == 3:
        comparison = calculate_comparison(
            quotes["adr"]["price"],
            quotes["koreanShare"]["price"],
            quotes["fx"]["price"],
        )

    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "ratio": 10,
        "quotes": quotes,
        "comparison": comparison,
        "errors": errors,
    }


def create_server(host="127.0.0.1", port=8787, client=None, static_dir=None):
    """Create the local dashboard server without starting its event loop."""
    market_client = client or JsonHttpClient()
    asset_directory = Path(static_dir or STATIC_DIR)

    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(asset_directory), **kwargs)

        def do_GET(self):
            if urlparse(self.path).path == "/api/snapshot":
                self._send_snapshot()
                return
            super().do_GET()

        def _send_snapshot(self):
            payload = fetch_market_snapshot(market_client)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            if urlparse(self.path).path == "/api/snapshot":
                return
            super().log_message(format, *args)

    return ThreadingHTTPServer((host, port), DashboardHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SK hynix ADR premium calculator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"SK hynix 价格速算已启动：{url}")
    print("关闭窗口或按 Control+C 即可停止。")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
