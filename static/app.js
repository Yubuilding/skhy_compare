import { isLiveQuote } from "./quote-status.mjs";
import { buildForeignFlowView } from "./foreign-flow.mjs";
import {
  renderForeignFlowChart,
  renderPremiumChart,
} from "./history-charts.mjs";
import { waitForNewPublishedSnapshot } from "./admin-refresh.mjs";

const elements = {
  adrPrice: document.querySelector("#adrPrice"),
  krPrice: document.querySelector("#krPrice"),
  fxRate: document.querySelector("#fxRate"),
  adrRatio: document.querySelector("#adrRatio"),
  premiumCard: document.querySelector("#premiumCard"),
  premiumValue: document.querySelector("#premiumValue"),
  premiumLabel: document.querySelector("#premiumLabel"),
  fairAdrHero: document.querySelector("#fairAdrHero"),
  priceGapHero: document.querySelector("#priceGapHero"),
  fairAdrResult: document.querySelector("#fairAdrResult"),
  krUsdResult: document.querySelector("#krUsdResult"),
  priceGapResult: document.querySelector("#priceGapResult"),
  pricingStateResult: document.querySelector("#pricingStateResult"),
  pricingStateNote: document.querySelector("#pricingStateNote"),
  refreshButton: document.querySelector("#refreshButton"),
  refreshButtonLabel: document.querySelector("#refreshButtonLabel"),
  refreshTime: document.querySelector("#refreshTime"),
  adminRefreshButton: document.querySelector("#adminRefreshButton"),
  adminRefreshStatus: document.querySelector("#adminRefreshStatus"),
  overallStatus: document.querySelector("#overallStatus"),
  errorBanner: document.querySelector("#errorBanner"),
  adrMeta: document.querySelector("#adrMeta"),
  overnightQuote: document.querySelector("#overnightQuote"),
  overnightPrice: document.querySelector("#overnightPrice"),
  overnightMeta: document.querySelector("#overnightMeta"),
  adrMarketTag: document.querySelector("#adrMarketTag"),
  krMeta: document.querySelector("#krMeta"),
  fxMeta: document.querySelector("#fxMeta"),
  adrMarketState: document.querySelector("#adrMarketState"),
  krMarketState: document.querySelector("#krMarketState"),
  foreignFlowPanel: document.querySelector("#foreignFlowPanel"),
  foreignFlowStatus: document.querySelector("#foreignFlowStatus"),
  foreignFlowDirection: document.querySelector("#foreignFlowDirection"),
  foreignNetShares: document.querySelector("#foreignNetShares"),
  foreignBuyShares: document.querySelector("#foreignBuyShares"),
  foreignSellShares: document.querySelector("#foreignSellShares"),
  foreignFlowMeta: document.querySelector("#foreignFlowMeta"),
  historyError: document.querySelector("#historyError"),
  foreignFlowChart: document.querySelector("#foreignFlowChart"),
  premiumHistoryChart: document.querySelector("#premiumHistoryChart"),
  foreignHistoryMeta: document.querySelector("#foreignHistoryMeta"),
  premiumHistoryMeta: document.querySelector("#premiumHistoryMeta"),
  premiumChartRatio: document.querySelector("#premiumChartRatio"),
  foreignHistoryTable: document.querySelector("#foreignHistoryTable"),
};

const marketInputs = [elements.adrPrice, elements.krPrice, elements.fxRate];
let hasManualMarketInput = false;
let hasManualRatio = false;
let marketInputRevision = 0;
let requestRevision = 0;
let historyData = null;
let lastPublishedSnapshotFetchedAt = null;
let adminRefreshPromise = null;
const dataMode = document.querySelector('meta[name="data-mode"]')?.content || "local";

if (dataMode === "static") {
  elements.refreshButtonLabel.textContent = "读取已发布数据";
  elements.adminRefreshButton.hidden = false;
  elements.adminRefreshStatus.hidden = false;
  elements.adminRefreshStatus.textContent = "管理员更新需在 GitHub 点击 Run workflow";
}

const usd = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const percent = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "always",
});

function numericValue(input) {
  const value = Number.parseFloat(input.value);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function formatMarketStatus(status, session) {
  if (session === "OVERNIGHT" && String(status).toUpperCase() === "OPEN") {
    return "夜盘交易中";
  }
  const labels = {
    OPEN: "交易中",
    Open: "交易中",
    REGULAR: "交易中",
    CLOSED: "已收盘",
    Closed: "已收盘",
    CLOSE: "已收盘",
    PRE: "盘前",
    POST: "盘后",
  };
  return labels[status] || status || "状态未知";
}

function formatTimestamp(value) {
  if (!value) return "时间未提供";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  return value;
}

function dataEndpoint(name) {
  const path = dataMode === "static" ? `./data/${name}.json` : `/api/${name}`;
  return `${path}?t=${Date.now()}`;
}

function resetResult() {
  [
    elements.premiumValue,
    elements.fairAdrHero,
    elements.priceGapHero,
    elements.fairAdrResult,
    elements.krUsdResult,
    elements.priceGapResult,
    elements.pricingStateResult,
  ].forEach((node) => { node.textContent = "--"; });
  elements.premiumLabel.textContent = "请填写三项正数行情与 ADR 比例";
  elements.pricingStateNote.textContent = "等待完整数据";
  elements.premiumCard.classList.remove("positive", "negative");
}

function calculate() {
  const adrPrice = numericValue(elements.adrPrice);
  const krPrice = numericValue(elements.krPrice);
  const fxRate = numericValue(elements.fxRate);
  const ratio = numericValue(elements.adrRatio);
  if (!adrPrice || !krPrice || !fxRate || !ratio) {
    resetResult();
    return;
  }

  const koreanShareUsd = krPrice / fxRate;
  const fairAdrUsd = koreanShareUsd / ratio;
  const priceGap = adrPrice - fairAdrUsd;
  const premiumRate = (adrPrice / fairAdrUsd - 1) * 100;
  const isPremium = premiumRate >= 0;
  const stateWord = isPremium ? "溢价" : "折价";

  elements.premiumValue.textContent = `${percent.format(premiumRate)}%`;
  elements.premiumLabel.textContent = `美股 ADR 当前${stateWord}`;
  elements.fairAdrHero.textContent = usd.format(fairAdrUsd);
  elements.priceGapHero.textContent = `${priceGap >= 0 ? "+" : "−"}${usd.format(Math.abs(priceGap))}`;
  elements.fairAdrResult.textContent = usd.format(fairAdrUsd);
  elements.krUsdResult.textContent = usd.format(koreanShareUsd);
  elements.priceGapResult.textContent = `${priceGap >= 0 ? "+" : "−"}${usd.format(Math.abs(priceGap))}`;
  elements.pricingStateResult.textContent = `${Math.abs(premiumRate).toFixed(2)}% ${stateWord}`;
  elements.pricingStateNote.textContent = `按 1 股韩股 = ${ratio} 份 ADR 计算`;
  elements.premiumCard.classList.toggle("positive", isPremium);
  elements.premiumCard.classList.toggle("negative", !isPremium);
}

function applyQuote(quote, input, meta, marketState) {
  if (!quote) {
    input.value = "";
    meta.textContent = "本次自动获取失败，请手动输入";
    if (marketState) marketState.textContent = "数据不可用";
    if (input === elements.adrPrice) {
      elements.adrMarketTag.textContent = "SKHY";
      elements.adrMarketTag.classList.remove("night");
    }
    return;
  }
  input.value = quote.price;
  const sessionLabels = {
    OVERNIGHT: "夜盘",
    REGULAR: "常规盘",
    PREMARKET: "盘前",
    AFTER_HOURS: "盘后",
    CLOSED: "最新收盘",
  };
  const isLive = isLiveQuote(quote);
  const freshness = isLive ? "实时" : "最新可得";
  const sessionLabel = sessionLabels[quote.session];
  meta.textContent = `${sessionLabel ? `${sessionLabel} · ` : ""}${freshness} · ${quote.source} · ${formatTimestamp(quote.timestamp)}`;
  if (marketState) {
    marketState.textContent = formatMarketStatus(quote.marketStatus, quote.session);
  }
  if (input === elements.adrPrice) {
    const isOvernight = quote.session === "OVERNIGHT";
    elements.adrMarketTag.textContent = isOvernight ? "BOATS" : "NASDAQ";
    elements.adrMarketTag.classList.toggle("night", isOvernight);
  }
}

function applyOvernightQuote(adrQuote) {
  const overnight = adrQuote?.sessions?.overnight;
  elements.overnightQuote.classList.toggle(
    "active",
    overnight?.marketStatus === "OPEN",
  );
  if (!overnight) {
    elements.overnightPrice.textContent = "--";
    elements.overnightMeta.textContent = adrQuote?.overnightError
      ? "夜盘获取失败，已回退常规行情"
      : "当前没有可用夜盘成交价";
    return;
  }
  elements.overnightPrice.textContent = usd.format(overnight.price);
  const status = overnight.marketStatus === "OPEN" && overnight.isRealTime
    ? "实时交易中"
    : overnight.marketStatus === "OPEN"
      ? "夜盘交易中 · 报价可能延迟"
      : "上一夜盘成交";
  elements.overnightMeta.textContent = `${status} · ${formatTimestamp(overnight.timestamp)}`;
}

function applyForeignFlow(flow) {
  const view = buildForeignFlowView(flow);
  elements.foreignFlowPanel.classList.remove("buy", "sell", "flat", "unavailable");
  elements.foreignFlowPanel.classList.add(view.tone);
  elements.foreignFlowStatus.textContent = view.available ? view.freshnessLabel : "数据不可用";
  elements.foreignFlowDirection.textContent = view.directionLabel;
  elements.foreignNetShares.textContent = view.netText;
  elements.foreignBuyShares.textContent = view.buyText;
  elements.foreignSellShares.textContent = view.sellText;
  elements.foreignFlowMeta.textContent = view.available
    ? `${flow.source} · 页面时间 ${formatTimestamp(flow.timestamp)} · 非最终结算值`
    : "本次自动获取失败，请稍后刷新";
}

function applySnapshotStatus(snapshot, manualInputPreserved = false) {
  const fetched = new Date(snapshot.fetchedAt);
  const timeLabel = dataMode === "static" ? "发布于" : "更新于";
  elements.refreshTime.textContent = `${timeLabel} ${fetched.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })}`;

  if (snapshot.errors.length) {
    const quoteErrors = snapshot.errors.filter((item) => item.field !== "foreignFlow");
    const missing = quoteErrors.map((item) => ({
      adr: "美股 ADR",
      koreanShare: "韩股",
      fx: "汇率",
    })[item.field] || item.field);
    const messages = [];
    if (missing.length) {
      messages.push(`${missing.join("、")}自动获取失败，可在对应卡片手动输入。`);
    }
    if (snapshot.errors.some((item) => item.field === "foreignFlow")) {
      messages.push("韩股外资流向获取失败，请稍后刷新。");
    }
    elements.errorBanner.textContent = messages.join(" ");
    elements.errorBanner.hidden = false;
    elements.overallStatus.className = "live-pill error";
    elements.overallStatus.innerHTML = "<i></i> 部分数据失败";
    return;
  }

  elements.overallStatus.className = "live-pill ready";
  if (dataMode === "static") {
    elements.overallStatus.innerHTML = manualInputPreserved
      ? "<i></i> 已读取发布数据 · 保留手动行情"
      : "<i></i> 已读取最新发布数据";
  } else {
    elements.overallStatus.innerHTML = manualInputPreserved
      ? "<i></i> 外资流向已更新 · 保留手动行情"
      : "<i></i> 最新数据已更新";
  }
}

function renderPremiumHistory() {
  if (!historyData) return;
  const ratio = numericValue(elements.adrRatio);
  const series = renderPremiumChart(
    elements.premiumHistoryChart,
    historyData.premiumInputs,
    ratio,
  );
  elements.premiumChartRatio.textContent = ratio ? `比例 1:${ratio}` : "比例无效";
  elements.premiumHistoryMeta.textContent = series.length
    ? `Nasdaq + Naver Finance · ${series.length} 个同日收盘点 · 随比例联动`
    : "暂无可对齐的 SKHY 历史收盘数据";
}

function renderForeignHistoryTable(rows) {
  const formatter = new Intl.NumberFormat("zh-CN");
  elements.foreignHistoryTable.replaceChildren();
  rows.slice().reverse().forEach((row) => {
    const tr = document.createElement("tr");
    const foreignDirection = row.netShares >= 0 ? "+" : "−";
    const institutionDirection = row.institutionNetShares >= 0 ? "+" : "−";
    const values = [
      row.date,
      `${foreignDirection}${formatter.format(Math.abs(row.netShares))}`,
      `${institutionDirection}${formatter.format(Math.abs(row.institutionNetShares))}`,
      `${Number(row.foreignHoldRatio).toFixed(2)}%`,
    ];
    values.forEach((value, index) => {
      const td = document.createElement("td");
      td.textContent = value;
      if (index === 1) td.className = row.netShares >= 0 ? "buy" : "sell";
      tr.append(td);
    });
    elements.foreignHistoryTable.append(tr);
  });
}

function applyHistory(history) {
  historyData = history;
  const flowRows = renderForeignFlowChart(elements.foreignFlowChart, history.foreignFlow);
  renderForeignHistoryTable(flowRows);
  elements.foreignHistoryMeta.textContent = flowRows.length
    ? `Naver Finance · 最近 ${flowRows.length} 个已确认交易日`
    : "Naver Finance · 暂无已确认历史数据";
  renderPremiumHistory();

  if (history.errors.length) {
    const labels = history.errors.map((item) => ({
      foreignFlow: "历史外资",
      premiumInputs: "历史溢价",
    })[item.field] || item.field);
    elements.historyError.textContent = `${labels.join("、")}数据暂时不可用，其他图表仍可查看。`;
    elements.historyError.hidden = false;
  } else {
    elements.historyError.hidden = true;
  }
}

async function loadHistory() {
  try {
    const response = await fetch(dataEndpoint("history"), { cache: "no-store" });
    if (!response.ok) throw new Error(`服务器返回 ${response.status}`);
    applyHistory(await response.json());
  } catch (error) {
    elements.historyError.textContent = `历史数据获取失败：${error.message}`;
    elements.historyError.hidden = false;
    elements.foreignFlowChart.textContent = "历史外资数据暂不可用";
    elements.premiumHistoryChart.textContent = "历史溢价数据暂不可用";
  }
}

function markManual(input) {
  hasManualMarketInput = true;
  marketInputRevision += 1;
  const metaMap = new Map([
    [elements.adrPrice, elements.adrMeta],
    [elements.krPrice, elements.krMeta],
    [elements.fxRate, elements.fxMeta],
  ]);
  metaMap.get(input).textContent = "手动输入 · 点击刷新恢复自动";
  calculate();
}

async function loadSnapshot({ manualRefresh = false } = {}) {
  const thisRequest = ++requestRevision;
  const inputRevisionAtStart = marketInputRevision;
  elements.refreshButton.disabled = true;
  elements.refreshButton.classList.add("loading");
  elements.overallStatus.className = "live-pill";
  elements.overallStatus.innerHTML = "<i></i> 正在更新";
  elements.errorBanner.hidden = true;

  try {
    const snapshot = await fetchPublishedSnapshot();
    lastPublishedSnapshotFetchedAt = snapshot.fetchedAt || lastPublishedSnapshotFetchedAt;

    if (thisRequest !== requestRevision) return;
    applyForeignFlow(snapshot.foreignFlow);
    const preserveManualMarketInput = (
      (!manualRefresh && hasManualMarketInput)
      || marketInputRevision !== inputRevisionAtStart
    );
    if (preserveManualMarketInput) {
      applySnapshotStatus(snapshot, true);
      return;
    }

    hasManualMarketInput = false;
    if (!hasManualRatio && Number(snapshot.ratio) > 0) {
      elements.adrRatio.value = snapshot.ratio;
    }
    applyQuote(snapshot.quotes.adr, elements.adrPrice, elements.adrMeta, elements.adrMarketState);
    applyOvernightQuote(snapshot.quotes.adr);
    applyQuote(snapshot.quotes.koreanShare, elements.krPrice, elements.krMeta, elements.krMarketState);
    applyQuote(snapshot.quotes.fx, elements.fxRate, elements.fxMeta);
    calculate();
    applySnapshotStatus(snapshot);
  } catch (error) {
    elements.errorBanner.textContent = `暂时无法获取行情：${error.message}。请检查网络，或手动填写三项数据。`;
    elements.errorBanner.hidden = false;
    elements.overallStatus.className = "live-pill error";
    elements.overallStatus.innerHTML = "<i></i> 连接失败";
    elements.refreshTime.textContent = "行情获取失败";
  } finally {
    elements.refreshButton.disabled = false;
    elements.refreshButton.classList.remove("loading");
  }
}

async function fetchPublishedSnapshot() {
  const response = await fetch(dataEndpoint("snapshot"), { cache: "no-store" });
  if (!response.ok) throw new Error(`服务器返回 ${response.status}`);
  return response.json();
}

function startAdminRefreshPolling() {
  if (dataMode !== "static" || adminRefreshPromise) return;

  elements.adminRefreshStatus.textContent = "请在 GitHub 点击 Run workflow；正在等待新版本…";
  const baselinePromise = lastPublishedSnapshotFetchedAt
    ? Promise.resolve(lastPublishedSnapshotFetchedAt)
    : fetchPublishedSnapshot().then((snapshot) => snapshot.fetchedAt);
  adminRefreshPromise = baselinePromise
    .then((baselineFetchedAt) => waitForNewPublishedSnapshot({
      baselineFetchedAt,
      loadSnapshot: fetchPublishedSnapshot,
      intervalMs: 5_000,
      maxAttempts: 36,
    }))
    .then(async (snapshot) => {
      lastPublishedSnapshotFetchedAt = snapshot.fetchedAt;
      await loadSnapshot({ manualRefresh: true });
      await loadHistory();
      const published = new Date(snapshot.fetchedAt);
      elements.adminRefreshStatus.textContent = `新数据已发布：${published.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      })}`;
    })
    .catch((error) => {
      elements.adminRefreshStatus.textContent = `${error.message}；可稍后点击“读取已发布数据”`;
    })
    .finally(() => {
      adminRefreshPromise = null;
    });
}

marketInputs.forEach((input) => {
  input.addEventListener("input", () => markManual(input));
});
elements.adrRatio.addEventListener("input", () => {
  hasManualRatio = true;
  calculate();
  renderPremiumHistory();
});
elements.refreshButton.addEventListener("click", () => {
  loadSnapshot({ manualRefresh: true });
  loadHistory();
});
elements.adminRefreshButton.addEventListener("click", startAdminRefreshPolling);

loadSnapshot();
loadHistory();
window.setInterval(() => {
  if (!document.hidden) loadSnapshot();
}, 60_000);
window.setInterval(() => {
  if (!document.hidden) loadHistory();
}, 5 * 60_000);
