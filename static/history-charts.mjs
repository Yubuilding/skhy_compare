const SVG_NS = "http://www.w3.org/2000/svg";
const WIDTH = 720;
const HEIGHT = 240;
const PLOT_LEFT = 48;
const PLOT_RIGHT = 704;
const PLOT_TOP = 20;
const PLOT_BOTTOM = 202;

function validNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function shortDate(value) {
  const parts = String(value).split("-");
  return parts.length === 3 ? `${parts[1]}/${parts[2]}` : String(value);
}

function svgElement(name, attributes = {}, text = null) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== null) node.textContent = text;
  return node;
}

export function calculatePremiumSeries(inputs, ratio) {
  const parsedRatio = validNumber(ratio);
  if (!parsedRatio || parsedRatio <= 0 || !Array.isArray(inputs)) return [];
  return inputs.flatMap((row) => {
    const adrPriceUsd = validNumber(row.adrPriceUsd);
    const koreanPriceKrw = validNumber(row.koreanPriceKrw);
    const krwPerUsd = validNumber(row.krwPerUsd);
    if (!adrPriceUsd || !koreanPriceKrw || !krwPerUsd) return [];
    const fairAdrUsd = (koreanPriceKrw / krwPerUsd) / parsedRatio;
    return [{
      date: row.date,
      value: (adrPriceUsd / fairAdrUsd - 1) * 100,
      adrPriceUsd,
      fairAdrUsd,
    }];
  });
}

export function buildLineChartModel(series) {
  const values = series.map((point) => point.value);
  let minValue = Math.min(0, ...values);
  let maxValue = Math.max(0, ...values);
  if (minValue === maxValue) {
    minValue -= 1;
    maxValue += 1;
  }
  const xStep = series.length > 1 ? (PLOT_RIGHT - PLOT_LEFT) / (series.length - 1) : 0;
  const yFor = (value) => PLOT_TOP
    + ((maxValue - value) / (maxValue - minValue)) * (PLOT_BOTTOM - PLOT_TOP);
  const points = series.map((point, index) => ({
    ...point,
    x: series.length > 1 ? PLOT_LEFT + index * xStep : (PLOT_LEFT + PLOT_RIGHT) / 2,
    y: yFor(point.value),
  }));
  return {
    width: WIDTH,
    height: HEIGHT,
    plotTop: PLOT_TOP,
    plotBottom: PLOT_BOTTOM,
    minValue,
    maxValue,
    zeroY: yFor(0),
    points,
    path: points.map((point) => `${point.x},${point.y}`).join(" "),
  };
}

export function buildBarChartModel(rows) {
  const maxAbsolute = Math.max(1, ...rows.map((row) => Math.abs(Number(row.netShares) || 0)));
  const baseline = (PLOT_TOP + PLOT_BOTTOM) / 2;
  const halfHeight = (PLOT_BOTTOM - PLOT_TOP) / 2;
  const slot = (PLOT_RIGHT - PLOT_LEFT) / Math.max(rows.length, 1);
  const barWidth = Math.min(28, Math.max(6, slot * 0.62));
  const bars = rows.map((row, index) => {
    const value = Number(row.netShares) || 0;
    const barHeight = (Math.abs(value) / maxAbsolute) * halfHeight;
    return {
      ...row,
      value,
      tone: value > 0 ? "buy" : value < 0 ? "sell" : "flat",
      x: PLOT_LEFT + index * slot + (slot - barWidth) / 2,
      y: value >= 0 ? baseline - barHeight : baseline,
      width: barWidth,
      height: barHeight,
    };
  });
  return {
    width: WIDTH,
    height: HEIGHT,
    plotTop: PLOT_TOP,
    plotBottom: PLOT_BOTTOM,
    baseline,
    bars,
  };
}

function appendAxisLabels(svg, firstDate, lastDate) {
  svg.append(
    svgElement("text", { x: PLOT_LEFT, y: 228, class: "chart-axis-label" }, shortDate(firstDate)),
    svgElement("text", { x: PLOT_RIGHT, y: 228, class: "chart-axis-label", "text-anchor": "end" }, shortDate(lastDate)),
  );
}

export function renderPremiumChart(container, inputs, ratio) {
  const series = calculatePremiumSeries(inputs, ratio);
  container.replaceChildren();
  if (!series.length) {
    container.textContent = "暂无可对齐的历史收盘数据";
    container.classList.add("empty");
    return series;
  }
  container.classList.remove("empty");
  const model = buildLineChartModel(series);
  const svg = svgElement("svg", {
    viewBox: `0 0 ${model.width} ${model.height}`,
    role: "img",
    "aria-label": "SK 海力士 ADR 历史溢价率折线图",
  });
  svg.append(
    svgElement("line", { x1: PLOT_LEFT, x2: PLOT_RIGHT, y1: model.zeroY, y2: model.zeroY, class: "chart-zero" }),
    svgElement("polyline", { points: model.path, class: "premium-line" }),
    svgElement("text", { x: 6, y: PLOT_TOP + 5, class: "chart-axis-label" }, `${model.maxValue.toFixed(1)}%`),
    svgElement("text", { x: 6, y: PLOT_BOTTOM, class: "chart-axis-label" }, `${model.minValue.toFixed(1)}%`),
  );
  model.points.forEach((point) => {
    const circle = svgElement("circle", { cx: point.x, cy: point.y, r: 4, class: "premium-point" });
    circle.append(svgElement("title", {}, `${point.date} · ${point.value.toFixed(2)}%`));
    svg.append(circle);
  });
  appendAxisLabels(svg, series[0].date, series.at(-1).date);
  container.append(svg);
  return series;
}

export function renderForeignFlowChart(container, rows) {
  const chartRows = Array.isArray(rows) ? rows.slice(-20) : [];
  container.replaceChildren();
  if (!chartRows.length) {
    container.textContent = "暂无外资确认数据";
    container.classList.add("empty");
    return chartRows;
  }
  container.classList.remove("empty");
  const model = buildBarChartModel(chartRows);
  const formatter = new Intl.NumberFormat("zh-CN");
  const svg = svgElement("svg", {
    viewBox: `0 0 ${model.width} ${model.height}`,
    role: "img",
    "aria-label": "SK 海力士历史外资净买卖柱状图",
  });
  svg.append(svgElement("line", {
    x1: PLOT_LEFT,
    x2: PLOT_RIGHT,
    y1: model.baseline,
    y2: model.baseline,
    class: "chart-zero",
  }));
  model.bars.forEach((bar) => {
    const rect = svgElement("rect", {
      x: bar.x,
      y: bar.y,
      width: bar.width,
      height: Math.max(bar.height, 1),
      rx: 2,
      class: `flow-bar ${bar.tone}`,
    });
    const direction = bar.value >= 0 ? "+" : "−";
    rect.append(svgElement("title", {}, `${bar.date} · ${direction}${formatter.format(Math.abs(bar.value))} 股`));
    svg.append(rect);
  });
  appendAxisLabels(svg, chartRows[0].date, chartRows.at(-1).date);
  container.append(svg);
  return chartRows;
}
