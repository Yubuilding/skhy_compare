import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBarChartModel,
  buildLineChartModel,
  calculatePremiumSeries,
} from "../static/history-charts.mjs";

test("calculates historical premium using the selected ADR ratio", () => {
  const inputs = [{
    date: "2026-07-10",
    adrPriceUsd: 168.01,
    koreanPriceKrw: 2_180_000,
    krwPerUsd: 1502,
  }];

  const ratio10 = calculatePremiumSeries(inputs, 10);
  const ratio11 = calculatePremiumSeries(inputs, 11);
  const expected10 = (168.01 / ((2_180_000 / 1502) / 10) - 1) * 100;

  assert.equal(ratio10.length, 1);
  assert.ok(Math.abs(ratio10[0].value - expected10) < 1e-9);
  assert.ok(ratio11[0].value > ratio10[0].value);
});

test("line chart model includes a zero reference and preserves endpoints", () => {
  const series = [
    { date: "2026-07-10", value: -5 },
    { date: "2026-07-13", value: 12 },
  ];

  const model = buildLineChartModel(series);

  assert.equal(model.points[0].date, "2026-07-10");
  assert.equal(model.points.at(-1).date, "2026-07-13");
  assert.ok(model.zeroY > model.plotTop);
  assert.ok(model.zeroY < model.plotBottom);
});

test("bar chart model places buys above and sells below the baseline", () => {
  const model = buildBarChartModel([
    { date: "2026-07-10", netShares: 100 },
    { date: "2026-07-13", netShares: -50 },
  ]);

  assert.equal(model.bars[0].tone, "buy");
  assert.ok(model.bars[0].y < model.baseline);
  assert.equal(model.bars[1].tone, "sell");
  assert.equal(model.bars[1].y, model.baseline);
});
