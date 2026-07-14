"""Minimal TradingView quote client for the Blue Ocean overnight session.

The project intentionally uses only the Python standard library, so this file
contains the small subset of WebSocket framing needed for one quote snapshot.
"""

import base64
import hashlib
import json
import math
import os
import secrets
import socket
import ssl
import struct
import time
from datetime import datetime, timezone


_HOST = "data.tradingview.com"
_PATH = "/socket.io/websocket?from=symbols%2FBOATS-SKHY%2F"
_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_QUOTE_FIELDS = (
    "lp",
    "lp_time",
    "rtc",
    "rtc_time",
    "ch",
    "chp",
    "currency_code",
    "current_session",
    "market_status",
    "provider_id",
    "update_mode",
    "description",
    "exchange",
)


class TradingViewOvernightClient:
    """Fetch the latest BOATS overnight trade for a U.S. symbol."""

    def __init__(
        self,
        timeout=7,
        connection_factory=None,
        session_id_factory=None,
        clock=None,
    ):
        self.timeout = timeout
        self._connection_factory = connection_factory or _connect
        self._session_id_factory = session_id_factory or (
            lambda: f"qs_{secrets.token_hex(6)}"
        )
        self._clock = clock or time.monotonic

    def get_quote(self, symbol):
        tv_symbol = f"BOATS:{symbol}"
        session_id = self._session_id_factory()
        deadline = self._clock() + self.timeout
        connection = self._connection_factory(self.timeout)
        try:
            # TradingView starts each socket with a server-session greeting.
            # Reading it first avoids racing subscription commands against the
            # server's protocol initialization.
            self._receive_before_deadline(connection, deadline, tv_symbol)
            self._send_command(connection, "set_auth_token", ["unauthorized_user_token"])
            self._send_command(connection, "quote_create_session", [session_id])
            self._send_command(
                connection,
                "quote_set_fields",
                [session_id, *_QUOTE_FIELDS],
            )
            self._send_command(
                connection,
                "quote_add_symbols",
                [session_id, tv_symbol],
            )

            for _ in range(40):
                message = self._receive_before_deadline(connection, deadline, tv_symbol)
                for payload in _tradingview_payloads(message):
                    if payload.startswith("~h~"):
                        heartbeat = f"~m~{len(payload.encode('utf-8'))}~m~{payload}"
                        connection.send_text(heartbeat)
                        continue
                    if not payload.startswith("{"):
                        continue
                    parsed = json.loads(payload)
                    if parsed.get("m") == "critical_error":
                        details = ", ".join(str(item) for item in parsed.get("p", []))
                        raise OSError(f"TradingView protocol error: {details}")
                    if parsed.get("m") != "qsd":
                        continue
                    quote_data = parsed.get("p", [None, None])[1] or {}
                    if quote_data.get("n") != tv_symbol:
                        continue
                    if quote_data.get("s") != "ok":
                        raise OSError(f"TradingView quote unavailable for {tv_symbol}")
                    values = quote_data.get("v") or {}
                    if values.get("lp") is None:
                        continue
                    return _normalize_quote(symbol, values)
            raise TimeoutError(f"Timed out waiting for {tv_symbol} overnight quote")
        finally:
            connection.close()

    def _receive_before_deadline(self, connection, deadline, tv_symbol):
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for {tv_symbol} overnight quote")
        return connection.receive_text(timeout=remaining)

    @staticmethod
    def _send_command(connection, method, params):
        payload = json.dumps(
            {"m": method, "p": params},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        connection.send_text(f"~m~{len(payload.encode('utf-8'))}~m~{payload}")


def _normalize_quote(symbol, values):
    price = float(values["lp"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("TradingView returned an invalid overnight price")

    timestamp = values.get("lp_time")
    if timestamp is not None:
        timestamp = float(timestamp)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        timestamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()

    provider_status = str(values.get("market_status") or "").lower()
    current_session = str(values.get("current_session") or "").lower()
    is_open = provider_status in {"open", "opened", "trading"} or (
        not provider_status and current_session not in {"", "out_of_session"}
    )
    update_mode = str(values.get("update_mode") or "").lower()
    is_realtime = update_mode in {"streaming", "real_time", "realtime"}

    return {
        "price": price,
        "currency": "USD",
        "symbol": symbol,
        "source": "TradingView / BOATS",
        "timestamp": timestamp,
        "marketStatus": "OPEN" if is_open else "CLOSED",
        "isRealTime": is_realtime,
        "session": "OVERNIGHT",
    }


def _tradingview_payloads(message):
    parts = message.split("~m~")
    for index in range(1, len(parts) - 1, 2):
        if parts[index].isdigit():
            yield parts[index + 1]


def _connect(timeout):
    return _WebSocketConnection.connect(_HOST, _PATH, timeout)


class _WebSocketConnection:
    def __init__(self, sock, buffered=b""):
        self._socket = sock
        self._buffer = bytearray(buffered)
        self._fragment = bytearray()

    @classmethod
    def connect(cls, host, path, timeout):
        raw_socket = socket.create_connection((host, 443), timeout=timeout)
        wrapped = ssl.create_default_context().wrap_socket(
            raw_socket,
            server_hostname=host,
        )
        wrapped.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Origin: https://www.tradingview.com\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "User-Agent: Mozilla/5.0 SKHY-Compare/1.1\r\n"
            "\r\n"
        )
        wrapped.sendall(request.encode("ascii"))
        headers, buffered = _read_http_headers(wrapped)
        status_line = headers.split(b"\r\n", 1)[0]
        if b" 101 " not in status_line:
            wrapped.close()
            raise OSError(f"TradingView WebSocket handshake failed: {status_line!r}")

        expected = base64.b64encode(
            hashlib.sha1((key + _WEBSOCKET_GUID).encode("ascii")).digest()
        ).decode("ascii")
        header_text = headers.decode("iso-8859-1").lower()
        if f"sec-websocket-accept: {expected.lower()}" not in header_text:
            wrapped.close()
            raise OSError("TradingView WebSocket returned an invalid accept key")
        return cls(wrapped, buffered)

    def send_text(self, message):
        self._send_frame(0x1, message.encode("utf-8"))

    def receive_text(self, timeout=None):
        if timeout is not None:
            self._socket.settimeout(max(0.01, timeout))
        while True:
            first, second = self._read_exact(2)
            is_final = bool(first & 0x80)
            opcode = first & 0x0F
            is_masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if is_masked else None
            payload = bytearray(self._read_exact(length))
            if mask:
                for index in range(length):
                    payload[index] ^= mask[index % 4]

            if opcode == 0x8:
                raise OSError("TradingView closed the WebSocket connection")
            if opcode == 0x9:
                self._send_frame(0xA, bytes(payload))
                continue
            if opcode not in {0x0, 0x1}:
                continue
            self._fragment.extend(payload)
            if is_final:
                result = bytes(self._fragment).decode("utf-8")
                self._fragment.clear()
                return result

    def close(self):
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        finally:
            self._socket.close()

    def _send_frame(self, opcode, payload):
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._socket.sendall(bytes(header) + mask + masked)

    def _read_exact(self, length):
        while len(self._buffer) < length:
            chunk = self._socket.recv(max(4096, length - len(self._buffer)))
            if not chunk:
                raise OSError("TradingView WebSocket connection ended unexpectedly")
            self._buffer.extend(chunk)
        result = bytes(self._buffer[:length])
        del self._buffer[:length]
        return result


def _read_http_headers(sock):
    buffered = bytearray()
    marker = b"\r\n\r\n"
    while marker not in buffered:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError("TradingView ended the WebSocket handshake")
        buffered.extend(chunk)
        if len(buffered) > 64 * 1024:
            raise OSError("TradingView returned oversized WebSocket headers")
    header_end = buffered.index(marker) + len(marker)
    return bytes(buffered[:header_end]), bytes(buffered[header_end:])
