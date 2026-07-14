import assert from "node:assert/strict";
import test from "node:test";

import { isLiveQuote } from "../static/quote-status.mjs";

test("recognizes active Nasdaq and Yahoo sessions regardless of status casing", () => {
  for (const quote of [
    { isRealTime: true, marketStatus: "Open", session: "REGULAR" },
    { isRealTime: true, marketStatus: "REGULAR", session: "REGULAR" },
    { isRealTime: true, marketStatus: "PRE", session: "PREMARKET" },
    { isRealTime: true, marketStatus: "POST", session: "AFTER_HOURS" },
    { isRealTime: true, marketStatus: "OPEN", session: "OVERNIGHT" },
  ]) {
    assert.equal(isLiveQuote(quote), true);
  }
});

test("does not label closed, stale, or missing quotes as live", () => {
  for (const quote of [
    null,
    { isRealTime: false, marketStatus: "OPEN", session: "OVERNIGHT" },
    { isRealTime: true, marketStatus: "CLOSED", session: "CLOSED" },
    { isRealTime: true, marketStatus: "CLOSE", session: "REGULAR" },
  ]) {
    assert.equal(isLiveQuote(quote), false);
  }
});
