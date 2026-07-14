import json
import unittest

from tradingview import TradingViewOvernightClient


def framed_message(method, params):
    payload = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(payload)}~m~{payload}"


class FakeConnection:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []
        self.closed = False
        self.receive_timeouts = []

    def send_text(self, message):
        self.sent.append(message)

    def receive_text(self, timeout=None):
        self.receive_timeouts.append(timeout)
        return next(self.messages)

    def close(self):
        self.closed = True


class TradingViewOvernightClientTests(unittest.TestCase):
    def test_returns_normalized_live_boats_quote(self):
        quote_data = {
            "n": "BOATS:SKHY",
            "s": "ok",
            "v": {
                "lp": 156.82,
                "lp_time": 1783995330,
                "market_status": "open",
                "current_session": "market",
                "update_mode": "streaming",
            },
        }
        connection = FakeConnection(
            [
                '{"session_id":"server_session"}',
                framed_message("qsd", ["qs_test", quote_data]),
            ]
        )
        client = TradingViewOvernightClient(
            connection_factory=lambda timeout: connection,
            session_id_factory=lambda: "qs_test",
        )

        result = client.get_quote("SKHY")

        self.assertEqual(result["price"], 156.82)
        self.assertEqual(result["marketStatus"], "OPEN")
        self.assertEqual(result["session"], "OVERNIGHT")
        self.assertEqual(result["source"], "TradingView / BOATS")
        self.assertTrue(result["isRealTime"])
        self.assertEqual(result["timestamp"], "2026-07-14T02:15:30+00:00")
        self.assertTrue(connection.closed)
        self.assertTrue(any("quote_add_symbols" in message for message in connection.sent))

    def test_echoes_heartbeat_while_waiting_for_quote(self):
        quote_data = {
            "n": "BOATS:SKHY",
            "s": "ok",
            "v": {
                "lp": 156.82,
                "lp_time": 1783995330,
                "market_status": "open",
                "update_mode": "streaming",
            },
        }
        heartbeat = "~m~4~m~~h~1"
        connection = FakeConnection(
            [
                '{"session_id":"server_session"}',
                heartbeat,
                framed_message("qsd", ["qs_test", quote_data]),
            ]
        )
        client = TradingViewOvernightClient(
            connection_factory=lambda timeout: connection,
            session_id_factory=lambda: "qs_test",
        )

        client.get_quote("SKHY")

        self.assertIn(heartbeat, connection.sent)

    def test_does_not_claim_realtime_when_provider_omits_streaming_mode(self):
        quote_data = {
            "n": "BOATS:SKHY",
            "s": "ok",
            "v": {
                "lp": 156.82,
                "lp_time": 1783995330,
                "market_status": "closed",
            },
        }
        connection = FakeConnection(
            [
                '{"session_id":"server_session"}',
                framed_message("qsd", ["qs_test", quote_data]),
            ]
        )
        client = TradingViewOvernightClient(
            connection_factory=lambda timeout: connection,
            session_id_factory=lambda: "qs_test",
        )

        result = client.get_quote("SKHY")

        self.assertFalse(result["isRealTime"])

    def test_one_total_deadline_covers_greeting_and_quote_messages(self):
        clock_values = iter([0.0, 1.0, 8.0])
        connection = FakeConnection(['{"session_id":"server_session"}'])
        client = TradingViewOvernightClient(
            timeout=7,
            connection_factory=lambda timeout: connection,
            session_id_factory=lambda: "qs_test",
            clock=lambda: next(clock_values),
        )

        with self.assertRaises(TimeoutError):
            client.get_quote("SKHY")

        self.assertEqual(connection.receive_timeouts, [6.0])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
