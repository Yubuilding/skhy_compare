import assert from "node:assert/strict";
import test from "node:test";

import { buildMarketFundsView } from "../static/market-funds.mjs";


test("builds newest-first deposit and margin-financing tables", () => {
  const view = buildMarketFundsView([
    {
      date: "2026-07-09",
      investorDeposits100mKrw: 1_055_757,
      investorDepositsChange100mKrw: -5_000,
      marginFinancing100mKrw: 355_740,
      marginFinancingChange100mKrw: 2_500,
    },
    {
      date: "2026-07-10",
      investorDeposits100mKrw: 1_090_115,
      investorDepositsChange100mKrw: 34_358,
      marginFinancing100mKrw: 347_886,
      marginFinancingChange100mKrw: -7_854,
    },
  ]);

  assert.equal(view.latestDate, "2026-07-10");
  assert.deepEqual(view.investorDeposits.latest, {
    balance: 1_090_115,
    change: 34_358,
    tone: "up",
  });
  assert.deepEqual(view.marginFinancing.latest, {
    balance: 347_886,
    change: -7_854,
    tone: "down",
  });
  assert.deepEqual(
    view.marginFinancing.rows.map((row) => row.date),
    ["2026-07-10", "2026-07-09"],
  );
});
