<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartBar, ChartPayload, FootprintBin } from "../types";

const props = defineProps<{ chart: ChartPayload | null }>();

interface AnalyzedBin {
  bin: FootprintBin;
  total: number;
  isPoc: boolean;
  buyImbalance: boolean;
  sellImbalance: boolean;
  stackedBuy: boolean;
  stackedSell: boolean;
}

interface HoverState {
  bar: ChartBar;
  bin?: AnalyzedBin;
  price?: number;
  x: number;
  y: number;
}

const chartHost = ref<HTMLDivElement | null>(null);
const overlay = ref<HTMLCanvasElement | null>(null);
const hover = ref<HoverState | null>(null);
const visibleBars = ref(12);
let chartApi: IChartApi | null = null;
let candles: ISeriesApi<"Candlestick"> | null = null;
let cvdSeries: ISeriesApi<"Line"> | null = null;
let deltaSeries: ISeriesApi<"Histogram"> | null = null;
let observer: ResizeObserver | null = null;
let enforcingRange = false;
let drawFrame = 0;
let loadedBarCount = 0;
let loadedLastTime: UTCTimestamp | null = null;

const latest = computed(() => props.chart?.bars.at(-1));
const intervalLabel = computed(() => {
  const ms = props.chart?.intervalMs || 0;
  if (ms >= 60_000 && ms % 60_000 === 0) return `${ms / 60_000}m`;
  if (ms >= 1_000) return `${ms / 1_000}s`;
  return `${ms}ms`;
});
const latestStats = computed(() => {
  const bar = latest.value;
  if (!bar) return null;
  const volume = Number(bar.volume) || Number(bar.buyVol) + Number(bar.sellVol);
  const buyRatio = volume > 0 ? (Number(bar.buyVol) / volume) * 100 : 0;
  const deltaRatio = volume > 0 ? (Number(bar.delta) / volume) * 100 : 0;
  const poc = analyzeBins(bar.footprint?.bins || []).find((cell) => cell.isPoc)?.bin.price;
  return { volume, buyRatio, deltaRatio, poc };
});

function timestamp(value: number): UTCTimestamp {
  return Math.floor(value > 10_000_000_000 ? value / 1000 : value) as UTCTimestamp;
}

function formatPrice(value: number): string {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return value.toFixed(8).replace(/0+$/, "").replace(/\.$/, "");
}

function formatVolume(value: number): string {
  if (!Number.isFinite(value)) return "-";
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (absolute >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  if (absolute >= 100) return value.toFixed(0);
  if (absolute >= 10) return value.toFixed(1).replace(/\.0$/, "");
  if (absolute >= 1) return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return value.toFixed(4).replace(/^0/, "").replace(/0+$/, "").replace(/\.$/, "");
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${formatVolume(value)}`;
}

function formatPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function analyzeBins(source: FootprintBin[]): AnalyzedBin[] {
  const bins = source
    .filter((bin) => Number.isFinite(Number(bin.price)))
    .map((bin) => ({ ...bin, price: Number(bin.price), buyVol: Number(bin.buyVol) || 0, sellVol: Number(bin.sellVol) || 0 }))
    .sort((left, right) => left.price - right.price);
  if (!bins.length) return [];
  const totals = bins.map((bin) => Math.max(0, bin.buyVol) + Math.max(0, bin.sellVol));
  const pocIndex = totals.indexOf(Math.max(...totals));
  const raw = bins.map((bin, index) => {
    const lowerBid = index > 0 ? Math.max(0, bins[index - 1].sellVol) : 0;
    const upperAsk = index < bins.length - 1 ? Math.max(0, bins[index + 1].buyVol) : 0;
    const ask = Math.max(0, bin.buyVol);
    const bid = Math.max(0, bin.sellVol);
    return {
      bin,
      total: totals[index],
      isPoc: index === pocIndex,
      buyImbalance: ask > 0 && ask >= Math.max(0.0000001, lowerBid) * 3,
      sellImbalance: bid > 0 && bid >= Math.max(0.0000001, upperAsk) * 3,
      stackedBuy: false,
      stackedSell: false,
    };
  });
  for (const side of ["buy", "sell"] as const) {
    const key = side === "buy" ? "buyImbalance" : "sellImbalance";
    const stackKey = side === "buy" ? "stackedBuy" : "stackedSell";
    let runStart = 0;
    while (runStart < raw.length) {
      if (!raw[runStart][key]) {
        runStart += 1;
        continue;
      }
      let runEnd = runStart + 1;
      while (runEnd < raw.length && raw[runEnd][key]) runEnd += 1;
      if (runEnd - runStart >= 3) {
        for (let index = runStart; index < runEnd; index += 1) raw[index][stackKey] = true;
      }
      runStart = runEnd;
    }
  }
  return raw;
}

function barForTime(time: Time | undefined): ChartBar | undefined {
  if (time === undefined) return undefined;
  const seconds = Number(time);
  return props.chart?.bars.find((bar) => Number(timestamp(bar.startTs)) === seconds);
}

function nearestBin(bar: ChartBar, price: number | undefined): AnalyzedBin | undefined {
  if (price === undefined || !Number.isFinite(price)) return undefined;
  const cells = analyzeBins(bar.footprint?.bins || []);
  if (!cells.length) return undefined;
  const prices = cells.map((cell) => cell.bin.price);
  const gaps = prices.slice(1).map((value, index) => Math.abs(value - prices[index])).filter((value) => value > 0);
  const tolerance = gaps.length ? Math.min(...gaps) * 0.65 : Math.max(Math.abs(prices[0]) * 0.00001, 0.00000001);
  const closest = cells.reduce((best, cell) => Math.abs(cell.bin.price - price) < Math.abs(best.bin.price - price) ? cell : best);
  return Math.abs(closest.bin.price - price) <= tolerance ? closest : undefined;
}

function resizeOverlay(): CanvasRenderingContext2D | null {
  const canvas = overlay.value;
  const container = chartHost.value;
  if (!canvas || !container) return null;
  const width = Math.max(1, Math.floor(container.clientWidth));
  const height = Math.max(1, Math.floor(container.clientHeight));
  const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
  }
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  return context;
}

function binY(bin: FootprintBin): number | null {
  const coordinate = candles?.priceToCoordinate(Number(bin.price));
  return coordinate === null || !Number.isFinite(coordinate) ? null : Number(coordinate);
}

function drawFootprints(): void {
  drawFrame = 0;
  const context = resizeOverlay();
  const canvas = overlay.value;
  const bars = props.chart?.bars || [];
  if (!context || !canvas || !chartApi || !candles || !bars.length) return;
  const paneHeight = chartApi.panes()[0]?.getHeight() || Math.floor(canvas.clientHeight * 0.76);
  const timeScale = chartApi.timeScale();
  const visible = bars
    .map((bar, index) => {
      const coordinate = timeScale.timeToCoordinate(timestamp(bar.startTs));
      return coordinate === null ? null : { bar, index, x: Number(coordinate) };
    })
    .filter((item): item is { bar: ChartBar; index: number; x: number } => item !== null && item.x >= -120 && item.x <= canvas.clientWidth + 120);
  if (!visible.length) return;

  const gaps = visible.slice(1).map((item, index) => item.x - visible[index].x).filter((gap) => gap > 0);
  const gap = gaps.length ? Math.min(...gaps) : 72;
  const columnWidth = Math.max(14, Math.min(112, gap * 0.88));
  const halfWidth = columnWidth / 2;

  context.save();
  context.beginPath();
  context.rect(0, 0, canvas.clientWidth, paneHeight);
  context.clip();
  context.textBaseline = "middle";

  for (const { bar, index: barIndex, x } of visible) {
    const cells = analyzeBins(bar.footprint?.bins || []);
    if (!cells.length) continue;
    const maxBid = Math.max(0.0000001, ...cells.map((cell) => Math.max(0, cell.bin.sellVol)));
    const maxAsk = Math.max(0.0000001, ...cells.map((cell) => Math.max(0, cell.bin.buyVol)));
    const yRows = cells.map((cell) => binY(cell.bin));
    const distances = yRows
      .slice(1)
      .map((value, index) => value === null || yRows[index] === null ? 0 : Math.abs(value - Number(yRows[index])))
      .filter((value) => value > 0.5);
    const rowHeight = Math.max(6, Math.min(19, distances.length ? Math.min(...distances) * 0.92 : 12));
    const isLiveBar = barIndex === bars.length - 1;

    for (let cellIndex = 0; cellIndex < cells.length; cellIndex += 1) {
      const cell = cells[cellIndex];
      const y = yRows[cellIndex];
      if (y === null || y < 2 || y > paneHeight - 2) continue;
      const bidIntensity = Math.max(0.04, Math.max(0, cell.bin.sellVol) / maxBid);
      const askIntensity = Math.max(0.04, Math.max(0, cell.bin.buyVol) / maxAsk);

      context.fillStyle = `rgba(221, 74, 88, ${0.08 + bidIntensity * 0.43})`;
      context.fillRect(x - halfWidth, y - rowHeight / 2, halfWidth, rowHeight);
      context.fillStyle = `rgba(21, 174, 119, ${0.08 + askIntensity * 0.43})`;
      context.fillRect(x, y - rowHeight / 2, halfWidth, rowHeight);
      context.fillStyle = "rgba(6, 10, 15, 0.72)";
      context.fillRect(x - 0.5, y - rowHeight / 2, 1, rowHeight);

      if (cell.isPoc) {
        context.strokeStyle = "#f2c94c";
        context.lineWidth = 1.2;
        context.strokeRect(x - halfWidth + 0.5, y - rowHeight / 2 + 0.5, columnWidth - 1, rowHeight - 1);
      }
      if (cell.sellImbalance) {
        context.fillStyle = cell.stackedSell ? "#ff4258" : "#ff8190";
        context.fillRect(x - halfWidth, y - rowHeight / 2, cell.stackedSell ? 3 : 2, rowHeight);
      }
      if (cell.buyImbalance) {
        context.fillStyle = cell.stackedBuy ? "#1ff0a3" : "#6ee7b7";
        context.fillRect(x + halfWidth - (cell.stackedBuy ? 3 : 2), y - rowHeight / 2, cell.stackedBuy ? 3 : 2, rowHeight);
      }

      if (columnWidth >= 35 && rowHeight >= 8) {
        context.font = `${columnWidth >= 64 ? 9 : 8}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        context.fillStyle = "rgba(243, 246, 250, 0.96)";
        context.textAlign = "right";
        context.fillText(formatVolume(cell.bin.sellVol), x - 2.5, y, Math.max(10, halfWidth - 5));
        context.textAlign = "left";
        context.fillText(formatVolume(cell.bin.buyVol), x + 2.5, y, Math.max(10, halfWidth - 5));
      }
    }

    const validY = yRows.filter((value): value is number => value !== null);
    if (validY.length) {
      const labelY = Math.min(paneHeight - 8, Math.max(9, Math.max(...validY) + 12));
      context.fillStyle = bar.delta >= 0 ? "#39d99a" : "#ff7180";
      context.textAlign = "center";
      context.font = "bold 8px ui-monospace, SFMono-Regular, Consolas, monospace";
      context.fillText(`Δ ${formatSigned(bar.delta)}`, x, labelY, Math.max(12, columnWidth));
    }
    if (isLiveBar) {
      const top = validY.length ? Math.max(1, Math.min(...validY) - rowHeight / 2) : 1;
      const bottom = validY.length ? Math.min(paneHeight - 1, Math.max(...validY) + rowHeight / 2) : paneHeight - 1;
      context.strokeStyle = "rgba(77, 163, 255, 0.9)";
      context.lineWidth = 1;
      context.setLineDash([3, 2]);
      context.strokeRect(x - halfWidth - 1.5, top, columnWidth + 3, Math.max(2, bottom - top));
      context.setLineDash([]);
    }
  }
  context.restore();
}

function scheduleDraw(): void {
  if (drawFrame) cancelAnimationFrame(drawFrame);
  drawFrame = requestAnimationFrame(drawFootprints);
}

function enforceVisibleRange(): void {
  if (!chartApi || enforcingRange) return;
  const range = chartApi.timeScale().getVisibleLogicalRange();
  if (!range) return;
  const span = range.to - range.from;
  visibleBars.value = Math.max(1, Math.round(span));
  const target = span < 6 ? 6 : span > 40 ? 40 : 0;
  if (target) {
    const center = (range.from + range.to) / 2;
    enforcingRange = true;
    chartApi.timeScale().setVisibleLogicalRange({ from: center - target / 2, to: center + target / 2 });
    enforcingRange = false;
    visibleBars.value = target;
  }
  scheduleDraw();
}

function onCrosshair(param: MouseEventParams<Time>): void {
  const bar = barForTime(param.time);
  if (!bar || !param.point) {
    hover.value = null;
    return;
  }
  const priceValue = candles?.coordinateToPrice(param.point.y);
  const price = priceValue === null || priceValue === undefined ? undefined : Number(priceValue);
  hover.value = {
    bar,
    bin: nearestBin(bar, price),
    price,
    x: param.point.x,
    y: param.point.y,
  };
}

function initialize(): void {
  if (!chartHost.value || chartApi) return;
  chartApi = createChart(chartHost.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: "#0a0f15" },
      textColor: "#8794a5",
      fontFamily: "Inter, Segoe UI, sans-serif",
      panes: { separatorColor: "#28323e", separatorHoverColor: "#425164", enableResize: true },
    },
    localization: { priceFormatter: formatPrice },
    grid: { vertLines: { color: "#151e28" }, horzLines: { color: "#151e28" } },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: "#91a2b5", width: 1, style: 3, labelBackgroundColor: "#2c3947" },
      horzLine: { color: "#91a2b5", width: 1, style: 3, labelBackgroundColor: "#2c3947" },
    },
    rightPriceScale: { borderColor: "#2b3744", minimumWidth: 68, scaleMargins: { top: 0.06, bottom: 0.09 } },
    timeScale: { borderColor: "#2b3744", timeVisible: true, secondsVisible: true, rightOffset: 1.2, barSpacing: 68, minBarSpacing: 12 },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
  });
  candles = chartApi.addSeries(CandlestickSeries, {
    upColor: "rgba(33, 194, 132, 0.13)",
    downColor: "rgba(237, 78, 94, 0.13)",
    borderUpColor: "#39d99a",
    borderDownColor: "#ff7180",
    wickUpColor: "#39d99a",
    wickDownColor: "#ff7180",
    priceLineVisible: true,
    priceLineColor: "#4da3ff",
    lastValueVisible: true,
  });
  deltaSeries = chartApi.addSeries(HistogramSeries, {
    priceScaleId: "delta",
    priceLineVisible: false,
    lastValueVisible: false,
    base: 0,
  }, 1);
  cvdSeries = chartApi.addSeries(LineSeries, {
    color: "#7ab8ff",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
    title: "CVD",
    crosshairMarkerVisible: true,
    crosshairMarkerRadius: 3,
  }, 1);
  cvdSeries.createPriceLine({ price: 0, color: "#4a5663", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" });
  chartApi.priceScale("delta", 1).applyOptions({ visible: false, scaleMargins: { top: 0.58, bottom: 0.04 } });
  const panes = chartApi.panes();
  panes[0]?.setStretchFactor(5);
  panes[1]?.setStretchFactor(1.35);
  chartApi.timeScale().subscribeVisibleLogicalRangeChange(enforceVisibleRange);
  chartApi.subscribeCrosshairMove(onCrosshair);
  observer = new ResizeObserver(scheduleDraw);
  observer.observe(chartHost.value);
}

function setData(): void {
  if (!chartApi || !candles || !cvdSeries || !deltaSeries) return;
  const bars = props.chart?.bars || [];
  if (!bars.length) {
    candles.setData([]);
    cvdSeries.setData([]);
    deltaSeries.setData([]);
    loadedBarCount = 0;
    loadedLastTime = null;
    hover.value = null;
    scheduleDraw();
    return;
  }

  const nextLastTime = timestamp(bars.at(-1)!.startTs);
  const previousRange = chartApi.timeScale().getVisibleLogicalRange();
  const wasAtRealtime = !previousRange || previousRange.to >= loadedBarCount - 1.25;
  const canUpdateLatest = loadedBarCount > 0
    && (bars.length === loadedBarCount || bars.length === loadedBarCount + 1)
    && (nextLastTime === loadedLastTime || nextLastTime > Number(loadedLastTime));
  const candleData = (bar: ChartBar) => ({
    time: timestamp(bar.startTs),
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
  });
  const cvdData = (bar: ChartBar) => ({ time: timestamp(bar.startTs), value: Number(bar.cvd) });
  const deltaData = (bar: ChartBar) => ({
    time: timestamp(bar.startTs),
    value: Number(bar.delta),
    color: Number(bar.delta) >= 0 ? "rgba(57, 217, 154, 0.62)" : "rgba(255, 113, 128, 0.62)",
  });

  if (canUpdateLatest) {
    const bar = bars.at(-1)!;
    candles.update(candleData(bar));
    cvdSeries.update(cvdData(bar));
    deltaSeries.update(deltaData(bar));
  } else {
    candles.setData(bars.map(candleData));
    cvdSeries.setData(bars.map(cvdData));
    deltaSeries.setData(bars.map(deltaData));
  }

  if (loadedBarCount === 0) {
    const count = Math.min(12, Math.max(6, bars.length));
    chartApi.timeScale().setVisibleLogicalRange({ from: bars.length - count - 0.5, to: bars.length - 0.5 });
    visibleBars.value = count;
  } else if (bars.length > loadedBarCount && wasAtRealtime) {
    chartApi.timeScale().scrollToRealTime();
  }
  loadedBarCount = bars.length;
  loadedLastTime = nextLastTime;
  scheduleDraw();
}

onMounted(async () => {
  await nextTick();
  initialize();
  setData();
});

onUnmounted(() => {
  if (drawFrame) cancelAnimationFrame(drawFrame);
  observer?.disconnect();
  chartApi?.remove();
  chartApi = null;
});

watch(() => props.chart, setData, { deep: true });
</script>

<template>
  <section class="flow-chart" aria-label="Interactive multi-bar footprint and CVD chart">
    <header class="chart-header">
      <div class="identity">
        <strong>ORDER FLOW</strong>
        <span>{{ chart?.symbol || "MARKET" }}</span>
        <span>{{ intervalLabel }}</span>
        <i class="live-dot" :class="{ active: Boolean(latest) }" aria-hidden="true" />
        <span class="live-label">LIVE</span>
      </div>
      <div class="readout">
        <span>LAST <b :class="latest && latest.close >= latest.open ? 'buy' : 'sell'">{{ latest ? formatPrice(latest.close) : "-" }}</b></span>
        <span>VOL <b>{{ latestStats ? formatVolume(latestStats.volume) : "-" }}</b></span>
        <span>Δ <b :class="(latest?.delta || 0) >= 0 ? 'buy' : 'sell'">{{ latest ? formatSigned(latest.delta) : "-" }}</b></span>
        <span>CVD <b :class="(latest?.cvd || 0) >= 0 ? 'buy' : 'sell'">{{ latest ? formatSigned(latest.cvd) : "-" }}</b></span>
      </div>
    </header>
    <div class="chart-shell">
      <div ref="chartHost" class="chart-host" />
      <canvas ref="overlay" class="footprint-overlay" />
      <div class="pane-label footprint-label"><span>BID</span><b>×</b><span>ASK</span></div>
      <div class="pane-label cvd-label">
        <strong>CVD</strong>
        <span :class="(latest?.cvd || 0) >= 0 ? 'buy' : 'sell'">{{ latest ? formatSigned(latest.cvd) : "-" }}</span>
        <i>Δ {{ latest ? formatSigned(latest.delta) : "-" }}</i>
      </div>
      <div v-if="!chart?.bars.length" class="empty-chart">
        <strong>NO TRADE FLOW</strong>
        <span>Waiting for aggregated trades</span>
      </div>
      <div
        v-if="hover"
        class="hover-readout"
        :class="{ right: hover.x > 360 }"
      >
        <div class="hover-title">
          <b>{{ new Date(hover.bar.startTs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }}</b>
          <span>{{ hover.bin ? formatPrice(hover.bin.bin.price) : (hover.price === undefined ? "-" : formatPrice(hover.price)) }}</span>
        </div>
        <div class="hover-grid">
          <span>O <b>{{ formatPrice(hover.bar.open) }}</b></span>
          <span>H <b>{{ formatPrice(hover.bar.high) }}</b></span>
          <span>L <b>{{ formatPrice(hover.bar.low) }}</b></span>
          <span>C <b>{{ formatPrice(hover.bar.close) }}</b></span>
          <span>BID <b class="sell">{{ hover.bin ? formatVolume(hover.bin.bin.sellVol) : "-" }}</b></span>
          <span>ASK <b class="buy">{{ hover.bin ? formatVolume(hover.bin.bin.buyVol) : "-" }}</b></span>
          <span>TRADES <b>{{ hover.bin?.bin.tradeCount ?? hover.bar.tradeCount }}</b></span>
          <span>Δ <b :class="(hover.bin?.bin.delta ?? hover.bar.delta) >= 0 ? 'buy' : 'sell'">{{ formatSigned(hover.bin?.bin.delta ?? hover.bar.delta) }}</b></span>
        </div>
        <div v-if="hover.bin" class="hover-flags">
          <span v-if="hover.bin.isPoc" class="poc-flag">POC</span>
          <span v-if="hover.bin.buyImbalance" class="buy-flag">ASK IMBALANCE</span>
          <span v-if="hover.bin.sellImbalance" class="sell-flag">BID IMBALANCE</span>
        </div>
      </div>
    </div>
    <footer class="chart-footer">
      <span><i class="legend poc" /> POC</span>
      <span><i class="legend buy" /> ASK IMBALANCE</span>
      <span><i class="legend sell" /> BID IMBALANCE</span>
      <span v-if="latestStats">BUY {{ latestStats.buyRatio.toFixed(1) }}%</span>
      <span v-if="latestStats">Δ% <b :class="latestStats.deltaRatio >= 0 ? 'buy' : 'sell'">{{ formatPercent(latestStats.deltaRatio) }}</b></span>
      <span class="visible-count">{{ Math.min(40, Math.max(0, visibleBars)) }} BARS</span>
    </footer>
  </section>
</template>

<style scoped>
.flow-chart { height: 100%; min-height: 0; display: grid; grid-template-rows: 36px minmax(0, 1fr) 26px; overflow: hidden; border: 1px solid var(--border); background: #0a0f15; }
.chart-header, .chart-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 9px; background: var(--panel-deep); color: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.chart-header { border-bottom: 1px solid var(--border); }
.chart-footer { justify-content: flex-start; border-top: 1px solid var(--border); overflow: hidden; white-space: nowrap; }
.visible-count { margin-left: auto; }
.identity, .readout { display: flex; align-items: baseline; gap: 9px; min-width: 0; }
.identity strong { color: var(--text); font-size: 11px; }
.identity span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.live-dot { width: 5px; height: 5px; border-radius: 50%; background: #4a5663; }
.live-dot.active { background: #39d99a; box-shadow: 0 0 0 3px rgba(57, 217, 154, 0.12); }
.live-label { color: #39d99a; font-size: 8px; }
.readout b, .chart-footer b { margin-left: 3px; color: var(--text); }
.buy, .readout b.buy, .chart-footer b.buy { color: var(--bid); }
.sell, .readout b.sell, .chart-footer b.sell { color: var(--ask); }
.chart-shell { position: relative; min-height: 0; overflow: hidden; }
.chart-host { position: absolute; inset: 0; }
.footprint-overlay { position: absolute; inset: 0; pointer-events: none; z-index: 3; }
.pane-label { position: absolute; z-index: 4; display: flex; align-items: center; gap: 5px; color: #728093; font-size: 8px; font-variant-numeric: tabular-nums; pointer-events: none; }
.footprint-label { top: 6px; right: 77px; }
.footprint-label span:first-child { color: #ff7180; }
.footprint-label span:last-child { color: #39d99a; }
.cvd-label { bottom: 28px; left: 8px; padding: 2px 5px; background: rgba(10, 15, 21, 0.78); }
.cvd-label strong { color: #8fc3ff; }
.cvd-label i { color: #7e8b9b; font-style: normal; }
.hover-readout { position: absolute; top: 9px; left: 8px; z-index: 5; width: 218px; padding: 7px; border: 1px solid #3a4b5e; background: rgba(8, 13, 19, 0.96); box-shadow: 0 5px 16px rgba(0, 0, 0, 0.28); color: #9daab9; font-size: 9px; font-variant-numeric: tabular-nums; pointer-events: none; }
.hover-readout.right { left: auto; right: 76px; }
.hover-title { display: flex; justify-content: space-between; align-items: center; padding-bottom: 5px; margin-bottom: 5px; border-bottom: 1px solid #263240; }
.hover-title b { color: #dce5ee; }
.hover-title span { color: #f2c94c; font-weight: 700; }
.hover-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 9px; }
.hover-grid span { display: flex; justify-content: space-between; gap: 6px; }
.hover-grid b { color: #dce5ee; font-weight: 650; }
.hover-grid b.buy { color: var(--bid); }
.hover-grid b.sell { color: var(--ask); }
.hover-flags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.hover-flags span { padding: 2px 4px; border: 1px solid currentColor; font-size: 8px; }
.poc-flag { color: #f2c94c; }
.buy-flag { color: #39d99a; }
.sell-flag { color: #ff7180; }
.empty-chart { position: absolute; inset: 0; z-index: 5; display: grid; place-content: center; gap: 4px; color: var(--muted); text-align: center; font-size: 10px; pointer-events: none; }
.empty-chart strong { color: #a7b2bf; font-size: 11px; }
.legend { display: inline-block; width: 8px; height: 8px; margin-right: 3px; border: 1px solid currentColor; vertical-align: -1px; }
.legend.poc { color: #f2c94c; }
.legend.buy { color: #39d99a; border-right-width: 3px; }
.legend.sell { color: #ff7180; border-left-width: 3px; }
@media (max-width: 720px) {
  .flow-chart { grid-template-rows: 55px minmax(0, 1fr) 26px; }
  .chart-header { align-content: center; flex-wrap: wrap; gap: 1px 8px; padding: 4px 7px; }
  .identity, .readout { width: 100%; gap: 7px; }
  .readout { justify-content: space-between; font-size: 9px; }
  .chart-footer span:nth-child(2), .chart-footer span:nth-child(3), .chart-footer span:nth-child(4) { display: none; }
  .hover-readout, .hover-readout.right { top: 7px; left: 7px; right: auto; width: min(218px, calc(100% - 86px)); }
  .footprint-label { right: 72px; }
}
@media (max-width: 420px) {
  .identity { gap: 5px; }
  .live-label { display: none; }
  .readout span:nth-child(2) { display: none; }
  .hover-readout, .hover-readout.right { width: min(190px, calc(100% - 76px)); }
  .chart-footer { gap: 8px; padding: 0 6px; }
}
</style>
