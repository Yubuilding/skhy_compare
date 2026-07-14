import { isLiveQuote } from "./quote-status.mjs";

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
  refreshTime: document.querySelector("#refreshTime"),
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
};

const marketInputs = [elements.adrPrice, elements.krPrice, elements.fxRate];
let hasManualMarketInput = false;
let hasManualRatio = false;
let marketInputRevision = 0;
let requestRevision = 0;

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
  if (!manualRefresh && hasManualMarketInput) return;
  const thisRequest = ++requestRevision;
  const inputRevisionAtStart = marketInputRevision;
  elements.refreshButton.disabled = true;
  elements.refreshButton.classList.add("loading");
  elements.overallStatus.className = "live-pill";
  elements.overallStatus.innerHTML = "<i></i> 正在更新";
  elements.errorBanner.hidden = true;

  try {
    const response = await fetch(`/api/snapshot?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`服务器返回 ${response.status}`);
    const snapshot = await response.json();

    if (thisRequest !== requestRevision) return;
    if (marketInputRevision !== inputRevisionAtStart) {
      elements.overallStatus.className = "live-pill ready";
      elements.overallStatus.innerHTML = "<i></i> 已保留手动输入";
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

    const fetched = new Date(snapshot.fetchedAt);
    elements.refreshTime.textContent = `更新于 ${fetched.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })}`;

    if (snapshot.errors.length) {
      const missing = snapshot.errors.map((item) => ({
        adr: "美股 ADR",
        koreanShare: "韩股",
        fx: "汇率",
      })[item.field] || item.field);
      elements.errorBanner.textContent = `${missing.join("、")}自动获取失败。可直接在对应卡片手动输入后继续计算。`;
      elements.errorBanner.hidden = false;
      elements.overallStatus.className = "live-pill error";
      elements.overallStatus.innerHTML = "<i></i> 部分数据失败";
    } else {
      elements.overallStatus.className = "live-pill ready";
      elements.overallStatus.innerHTML = "<i></i> 最新数据已更新";
    }
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

marketInputs.forEach((input) => {
  input.addEventListener("input", () => markManual(input));
});
elements.adrRatio.addEventListener("input", () => {
  hasManualRatio = true;
  calculate();
});
elements.refreshButton.addEventListener("click", () => loadSnapshot({ manualRefresh: true }));

loadSnapshot();
window.setInterval(() => {
  if (!document.hidden) loadSnapshot();
}, 60_000);
