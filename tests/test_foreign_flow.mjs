import assert from "node:assert/strict";
import test from "node:test";

import { buildForeignFlowView } from "../static/foreign-flow.mjs";

test("formats a positive intraday estimate as foreign net buying", () => {
  const view = buildForeignFlowView({
    netShares: 79_538,
    buyShares: 693_332,
    sellShares: 613_794,
    delayMinutes: 20,
    isEstimate: true,
  });

  assert.equal(view.available, true);
  assert.equal(view.directionLabel, "净买入");
  assert.equal(view.netText, "+79,538 股");
  assert.equal(view.buyText, "693,332 股");
  assert.equal(view.sellText, "613,794 股");
  assert.equal(view.tone, "buy");
  assert.equal(view.freshnessLabel, "盘中估算 · 约 20 分钟延迟");
});

test("formats a negative estimate as foreign net selling", () => {
  const view = buildForeignFlowView({
    netShares: -704_671,
    buyShares: 400_000,
    sellShares: 1_104_671,
    delayMinutes: 20,
    isEstimate: true,
  });

  assert.equal(view.directionLabel, "净卖出");
  assert.equal(view.netText, "−704,671 股");
  assert.equal(view.tone, "sell");
});

test("returns an unavailable view when flow data is missing", () => {
  assert.deepEqual(buildForeignFlowView(null), {
    available: false,
    directionLabel: "暂不可用",
    netText: "--",
    buyText: "--",
    sellText: "--",
    tone: "unavailable",
    freshnessLabel: "等待重新获取",
  });
});
