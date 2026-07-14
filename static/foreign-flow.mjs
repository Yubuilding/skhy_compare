const shares = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });

export function buildForeignFlowView(flow) {
  const values = [flow?.netShares, flow?.buyShares, flow?.sellShares].map(Number);
  if (!flow || values.some((value) => !Number.isFinite(value))) {
    return {
      available: false,
      directionLabel: "暂不可用",
      netText: "--",
      buyText: "--",
      sellText: "--",
      tone: "unavailable",
      freshnessLabel: "等待重新获取",
    };
  }

  const [netShares, buyShares, sellShares] = values;
  const tone = netShares > 0 ? "buy" : netShares < 0 ? "sell" : "flat";
  const directionLabel = netShares > 0 ? "净买入" : netShares < 0 ? "净卖出" : "基本持平";
  const sign = netShares > 0 ? "+" : netShares < 0 ? "−" : "";
  const delay = Number(flow.delayMinutes);
  const freshnessLabel = flow.isEstimate
    ? `盘中估算${Number.isFinite(delay) ? ` · 约 ${delay} 分钟延迟` : ""}`
    : "最新确认";

  return {
    available: true,
    directionLabel,
    netText: `${sign}${shares.format(Math.abs(netShares))} 股`,
    buyText: `${shares.format(Math.abs(buyShares))} 股`,
    sellText: `${shares.format(Math.abs(sellShares))} 股`,
    tone,
    freshnessLabel,
  };
}
