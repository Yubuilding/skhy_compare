function toneFor(change) {
  return change > 0 ? "up" : change < 0 ? "down" : "flat";
}

function buildSeries(rows, balanceKey, changeKey) {
  const mapped = rows.map((row) => ({
    date: row.date,
    balance: Number(row[balanceKey]),
    change: Number(row[changeKey]),
    tone: toneFor(Number(row[changeKey])),
  }));
  const first = mapped[0];
  return {
    latest: first
      ? { balance: first.balance, change: first.change, tone: first.tone }
      : null,
    rows: mapped,
  };
}

export function buildMarketFundsView(inputRows) {
  const rows = (Array.isArray(inputRows) ? inputRows : [])
    .filter((row) => (
      /^\d{4}-\d{2}-\d{2}$/.test(row?.date || "")
      && Number.isFinite(Number(row.investorDeposits100mKrw))
      && Number.isFinite(Number(row.investorDepositsChange100mKrw))
      && Number.isFinite(Number(row.marginFinancing100mKrw))
      && Number.isFinite(Number(row.marginFinancingChange100mKrw))
    ))
    .sort((left, right) => right.date.localeCompare(left.date))
    .slice(0, 20);

  return {
    latestDate: rows[0]?.date || null,
    investorDeposits: buildSeries(
      rows,
      "investorDeposits100mKrw",
      "investorDepositsChange100mKrw",
    ),
    marginFinancing: buildSeries(
      rows,
      "marginFinancing100mKrw",
      "marginFinancingChange100mKrw",
    ),
  };
}
