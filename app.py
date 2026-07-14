#!/usr/bin/env python3
"""Local SK hynix ADR premium calculator."""

import argparse
import json
import math
import re
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from tradingview import TradingViewOvernightClient


NASDAQ_QUOTE_URL = "https://api.nasdaq.com/api/quote/SKHY/info?assetclass=stocks"
NAVER_STOCK_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/000660"
NAVER_FOREIGN_FLOW_URL = "https://finance.naver.com/item/frgn.naver?code=000660&page=1"
NAVER_FX_URL = (
    "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=1"
)
YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
DATA_ERRORS = (KeyError, IndexError, TypeError, ValueError, OSError)
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_ADRS_PER_KOREAN_SHARE = 10
KOREA_TIMEZONE = timezone(timedelta(hours=9))


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        value = data.strip()
        if value:
            self.parts.append(value)


def _visible_text_parts(fragment):
    parser = _VisibleTextParser()
    parser.feed(fragment)
    parser.close()
    return parser.parts


class JsonHttpClient:
    """Small JSON HTTP client using only the Python standard library."""

    def __init__(self, timeout=8, overnight_client=None):
        self.timeout = timeout
        self.overnight_client = overnight_client or TradingViewOvernightClient(
            timeout=min(timeout, 7)
        )

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

    def get_text(self, url, headers=None):
        request_headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SKHY-Compare/1.0",
        }
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def get_overnight_quote(self, symbol):
        return self.overnight_client.get_quote(symbol)


def calculate_comparison(
    adr_price_usd,
    korean_share_price_krw,
    krw_per_usd,
    adrs_per_korean_share=DEFAULT_ADRS_PER_KOREAN_SHARE,
):
    """Return the USD-equivalent values and ADR premium for positive inputs."""
    values = (
        adr_price_usd,
        korean_share_price_krw,
        krw_per_usd,
        adrs_per_korean_share,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in values
    ):
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
        parsed = float(value)
    elif isinstance(value, str):
        parsed = float(value.replace("$", "").replace(",", "").strip())
    else:
        raise ValueError("Market value is not numeric")
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError("Market value must be a finite positive number")
    return parsed


def _parse_signed_integer(value):
    normalized = str(value).replace(",", "").replace("+", "").replace("−", "-").strip()
    if not re.fullmatch(r"-?\d+", normalized):
        raise ValueError("Market flow value is not an integer")
    return int(normalized)


def _fetch_foreign_flow(client):
    html = client.get_text(
        NAVER_FOREIGN_FLOW_URL,
        headers={"Referer": "https://finance.naver.com/", "User-Agent": "Mozilla/5.0"},
    )
    total_row = None
    for match in re.finditer(
        r'<tr[^>]*class=["\'][^"\']*\btotal\b[^"\']*["\'][^>]*>(.*?)</tr>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if "외국계추정합" in match.group(1):
            total_row = match.group(1)
            break
    if total_row is None:
        raise ValueError("Naver foreign broker estimate row is missing")

    numeric_parts = [
        part
        for part in _visible_text_parts(total_row)
        if re.fullmatch(r"[+\-−]?\d[\d,]*", part)
    ]
    if len(numeric_parts) < 3:
        raise ValueError("Naver foreign broker estimate values are incomplete")
    sell_shares, net_shares, buy_shares = map(_parse_signed_integer, numeric_parts[:3])
    sell_shares = abs(sell_shares)
    buy_shares = abs(buy_shares)
    if buy_shares - sell_shares != net_shares:
        raise ValueError("Naver foreign broker estimate values are inconsistent")

    date_match = re.search(
        r'class=["\']date["\'][^>]*>(.*?)</em>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if date_match is None:
        raise ValueError("Naver foreign broker estimate timestamp is missing")
    date_text = " ".join(_visible_text_parts(date_match.group(1)))
    timestamp_match = re.search(
        r"(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})",
        date_text,
    )
    if timestamp_match is None:
        raise ValueError("Naver foreign broker estimate timestamp is invalid")
    timestamp = datetime(
        *map(int, timestamp_match.groups()),
        tzinfo=KOREA_TIMEZONE,
    ).isoformat()

    page_text = " ".join(_visible_text_parts(html))
    delay_match = re.search(r"(\d+)\s*분\s*지연", page_text)
    delay_minutes = int(delay_match.group(1)) if delay_match else 20
    direction = "NET_BUY" if net_shares > 0 else "NET_SELL" if net_shares < 0 else "FLAT"
    return {
        "symbol": "000660",
        "netShares": net_shares,
        "buyShares": buy_shares,
        "sellShares": sell_shares,
        "direction": direction,
        "timestamp": timestamp,
        "marketStatus": "OPEN" if "KRX 장중" in date_text else "CLOSED",
        "delayMinutes": delay_minutes,
        "isEstimate": True,
        "source": "Naver Finance",
        "method": "Top-5 foreign brokerage estimate",
    }


def _fetch_regular_adr_quote(client):
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
        meta = _fetch_yahoo_meta(client, "SKHY")
        return _yahoo_adr_quote(meta)


def _yahoo_adr_quote(meta):
    market_status = str(meta.get("marketState") or "CLOSED").upper()
    session = "CLOSED"
    price_field = "regularMarketPrice"
    time_field = "regularMarketTime"
    if market_status in {"PRE", "PREPRE"} and meta.get("preMarketPrice") is not None:
        session = "PREMARKET"
        price_field = "preMarketPrice"
        time_field = "preMarketTime"
    elif market_status in {"POST", "POSTPOST"} and meta.get("postMarketPrice") is not None:
        session = "AFTER_HOURS"
        price_field = "postMarketPrice"
        time_field = "postMarketTime"
    elif market_status == "REGULAR":
        session = "REGULAR"

    delay = meta.get("exchangeDataDelayedBy")
    is_realtime = delay == 0 if delay is not None else market_status == "REGULAR"
    return {
        "price": _parse_number(meta[price_field]),
        "currency": "USD",
        "symbol": "SKHY",
        "source": "Yahoo Finance (fallback)",
        "timestamp": _yahoo_timestamp(meta, time_field),
        "marketStatus": market_status,
        "isRealTime": is_realtime,
        "session": session,
    }


def _fetch_adr_quote(client):
    regular = None
    overnight = None
    regular_error = None
    overnight_error = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = {
            executor.submit(_fetch_regular_adr_quote, client): "regular",
            executor.submit(client.get_overnight_quote, "SKHY"): "overnight",
        }
        for future in as_completed(pending):
            quote_type = pending[future]
            try:
                quote = future.result()
                if quote_type == "regular":
                    regular = quote
                else:
                    overnight = quote
            except (AttributeError,) + DATA_ERRORS as error:
                if quote_type == "regular":
                    regular_error = str(error)
                else:
                    overnight_error = str(error)

    if regular is not None:
        regular.setdefault(
            "session",
            (
                "REGULAR"
                if str(regular.get("marketStatus", "")).upper() == "OPEN"
                else "CLOSED"
            ),
        )

    use_overnight = (
        overnight is not None
        and str(overnight.get("marketStatus", "")).upper() == "OPEN"
    )
    if use_overnight:
        selected = dict(overnight)
    elif regular is not None:
        selected = dict(regular)
    elif overnight is not None:
        selected = dict(overnight)
        selected["fallbackReason"] = (
            "Regular quote unavailable; using the latest overnight trade"
        )
    else:
        reasons = "; ".join(
            reason for reason in (regular_error, overnight_error) if reason
        )
        raise OSError(f"No usable SKHY quote ({reasons or 'unknown error'})")
    selected["sessions"] = {
        "regular": regular,
        "overnight": overnight,
    }
    if regular_error:
        selected["regularError"] = regular_error
    if overnight_error:
        selected["overnightError"] = overnight_error
    return selected


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


def _yahoo_timestamp(meta, field="regularMarketTime"):
    timestamp = meta.get(field)
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def fetch_market_snapshot(client=None):
    """Fetch market inputs and the latest foreign flow estimate."""
    client = client or JsonHttpClient()
    providers = {
        "adr": _fetch_adr_quote,
        "koreanShare": _fetch_korean_quote,
        "fx": _fetch_fx_quote,
        "foreignFlow": _fetch_foreign_flow,
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

    foreign_flow = quotes.pop("foreignFlow", None)
    comparison = None
    if all(field in quotes for field in ("adr", "koreanShare", "fx")):
        comparison = calculate_comparison(
            quotes["adr"]["price"],
            quotes["koreanShare"]["price"],
            quotes["fx"]["price"],
        )

    return {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "ratio": DEFAULT_ADRS_PER_KOREAN_SHARE,
        "quotes": quotes,
        "foreignFlow": foreign_flow,
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
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
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

    try:
        server = create_server(args.host, args.port)
    except OSError as error:
        if args.port == 0:
            raise
        print(f"端口 {args.port} 已被占用，将自动改用其他本机端口。 ({error})")
        server = create_server(args.host, 0)
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
