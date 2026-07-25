<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
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

const host = ref<HTMLDivElement | null>(null);
const chartHost = ref<HTMLDivElement | null>(null);
const overlay = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ bar: ChartBar; price?: number } | null>(null);
const visibleBars = ref(12);
let chartApi: IChartApi | null = null;
let candles: ISeriesApi<"Candlestick"> | null = null;
let cvd: ISeriesApi<"Line"> | null = null;
let observer: ResizeObserver | null = null;
let enforcingRange = false;
let drawFrame = 0;

const latest = computed(() => props.chart?.bars.at(-1));
const intervalLabel = computed(() => {
  const ms = props.chart?.intervalMs || 0;
  if (ms >= 60_000) return `${ms / 60_000}m`;
  return `${ms / 1_000}s`;
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
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (absolute >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  if (absolute >= 10) return value.toFixed(0);
  if (absolute >= 1) return value.toFixed(1);
  return value.toFixed(3).replace(/^0/, "");
}

function formatSigned(value: number): string {
  return `${value > 0 ? "+" : ""}${formatVolume(value)}`;
}

function barForTime(time: Time | undefined): ChartBar | undefined {
  if (time === undefined) return undefined;
  const seconds = Number(time);
  return props.chart?.bars.find((bar) => Number(timestamp(bar.startTs)) === seconds);
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
  const paneHeight = chartApi.panes()[0]?.getHeight() || Math.floor(canvas.clientHeight * 0.72);
  const timeScale = chartApi.timeScale();
  const visible = bars
    .map((bar) => {
      const coordinate = timeScale.timeToCoordinate(timestamp(bar.startTs));
      return coordinate === null ? null : { bar, x: Number(coordinate) };
    })
    .filter((item): item is { bar: ChartBar; x: number } => item !== null && item.x >= -120 && item.x <= canvas.clientWidth + 120);
  if (!visible.length) return;

  const gaps = visible.slice(1).map((item, index) => item.x - visible[index].x).filter((gap) => gap > 0);
  const gap = gaps.length ? Math.min(...gaps) : 72;
  const columnWidth = Math.max(12, Math.min(104, gap * 0.86));

  context.save();
  context.beginPath();
  context.rect(0, 0, canvas.clientWidth, paneHeight);
  context.clip();
  context.font = `${columnWidth >= 42 ? 9 : 7}px ui-monospace, SFMono-Regular, Consolas, monospace`;
  context.textBaseline = "middle";

  for (const { bar, x } of visible) {
    const bins = (bar.footprint?.bins || []).filter((bin) => Number.isFinite(bin.price));
    if (!bins.length) continue;
    const totals = bins.map((bin) => Math.max(0, bin.buyVol) + Math.max(0, bin.sellVol));
    const maxTotal = Math.max(0.0000001, ...totals);
    const pocIndex = totals.indexOf(maxTotal);
    const yRows = bins.map((bin) => binY(bin));
    const distances = yRows
      .slice(1)
      .map((value, index) => value === null || yRows[index] === null ? 0 : Math.abs(value - Number(yRows[index])))
      .filter((value) => value > 0.5);
    const rowHeight = Math.max(6, Math.min(18, distances.length ? Math.min(...distances) : 12));

    bins.forEach((bin, index) => {
      const y = yRows[index];
      if (y === null || y < 2 || y > paneHeight - 2) return;
      const total = totals[index];
      const intensity = Math.max(0.08, total / maxTotal);
      const delta = Number(bin.buyVol || 0) - Number(bin.sellVol || 0);
      context.fillStyle = delta >= 0
        ? `rgba(15, 151, 104, ${0.12 + intensity * 0.42})`
        : `rgba(211, 68, 78, ${0.12 + intensity * 0.42})`;
      context.fillRect(x - columnWidth / 2, y - rowHeight / 2, columnWidth, rowHeight);

      const buyImbalance = bin.buyVol > 0 && bin.buyVol >= Math.max(0.0000001, bin.sellVol) * 3;
      const sellImbalance = bin.sellVol > 0 && bin.sellVol >= Math.max(0.0000001, bin.buyVol) * 3;
      if (index === pocIndex || buyImbalance || sellImbalance) {
        context.strokeStyle = index === pocIndex ? "#f2c94c" : buyImbalance ? "#39d99a" : "#ff7180";
        context.lineWidth = index === pocIndex ? 1.2 : 0.8;
        context.strokeRect(x - columnWidth / 2 + 0.5, y - rowHeight / 2 + 0.5, columnWidth - 1, rowHeight - 1);
      }

      context.fillStyle = "rgba(232, 239, 246, 0.94)";
      context.textAlign = "center";
      const text = `${formatVolume(bin.sellVol)}x${formatVolume(bin.buyVol)}`;
      context.fillText(text, x, y, Math.max(10, columnWidth - 3));
    });

    const validY = yRows.filter((value): value is number => value !== null);
    if (validY.length) {
      const labelY = Math.min(paneHeight - 8, Math.max(10, Math.max(...validY) + 12));
      context.fillStyle = bar.delta >= 0 ? "#39d99a" : "#ff7180";
      context.textAlign = "center";
      context.font = "bold 8px ui-monospace, SFMono-Regular, Consolas, monospace";
      context.fillText(`D ${formatSigned(bar.delta)}`, x, labelY, columnWidth);
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
  hover.value = bar ? { bar, price: param.point ? candles?.coordinateToPrice(param.point.y) ?? undefined : undefined } : null;
}

function initialize(): void {
  if (!chartHost.value || chartApi) return;
  chartApi = createChart(chartHost.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: "#0b1016" },
      textColor: "#8794a5",
      panes: { separatorColor: "#28323e", separatorHoverColor: "#425164", enableResize: true },
    },
    grid: { vertLines: { color: "#17202a" }, horzLines: { color: "#17202a" } },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: "#8da0b5", width: 1, style: 3, labelBackgroundColor: "#2c3947" },
      horzLine: { color: "#8da0b5", width: 1, style: 3, labelBackgroundColor: "#2c3947" },
    },
    rightPriceScale: { borderColor: "#2b3744", minimumWidth: 66, scaleMargins: { top: 0.06, bottom: 0.09 } },
    timeScale: { borderColor: "#2b3744", timeVisible: true, secondsVisible: true, rightOffset: 1, barSpacing: 64, minBarSpacing: 12 },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
    handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
  });
  candles = chartApi.addSeries(CandlestickSeries, {
    upColor: "rgba(57, 217, 154, 0.18)",
    downColor: "rgba(255, 113, 128, 0.18)",
    borderUpColor: "#39d99a",
    borderDownColor: "#ff7180",
    wickUpColor: "#39d99a",
    wickDownColor: "#ff7180",
    priceLineVisible: true,
    lastValueVisible: true,
  });
  cvd = chartApi.addSeries(LineSeries, {
    color: "#4da3ff",
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
    title: "CVD",
  }, 1);
  const panes = chartApi.panes();
  panes[0]?.setStretchFactor(4);
  panes[1]?.setStretchFactor(1);
  chartApi.timeScale().subscribeVisibleLogicalRangeChange(enforceVisibleRange);
  chartApi.subscribeCrosshairMove(onCrosshair);
  observer = new ResizeObserver(scheduleDraw);
  observer.observe(chartHost.value);
}

function setData(): void {
  if (!chartApi || !candles || !cvd) return;
  const bars = props.chart?.bars || [];
  candles.setData(bars.map((bar) => ({
    time: timestamp(bar.startTs),
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
  })));
  cvd.setData(bars.map((bar) => ({ time: timestamp(bar.startTs), value: Number(bar.cvd) })));
  if (bars.length) {
    const count = Math.min(12, Math.max(6, bars.length));
    chartApi.timeScale().setVisibleLogicalRange({ from: bars.length - count - 0.5, to: bars.length - 0.5 });
    visibleBars.value = count;
  }
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
  <section ref="host" class="flow-chart" aria-label="Interactive multi-bar footprint and CVD chart">
    <header class="chart-header">
      <div class="identity">
        <strong>FOOTPRINT</strong>
        <span>{{ chart?.symbol || "MARKET" }}</span>
        <span>{{ intervalLabel }}</span>
      </div>
      <div class="readout">
        <span>LAST <b :class="latest && latest.close >= latest.open ? 'buy' : 'sell'">{{ latest ? formatPrice(latest.close) : "-" }}</b></span>
        <span>DELTA <b :class="(latest?.delta || 0) >= 0 ? 'buy' : 'sell'">{{ latest ? formatSigned(latest.delta) : "-" }}</b></span>
        <span>CVD <b>{{ latest ? formatSigned(latest.cvd) : "-" }}</b></span>
      </div>
    </header>
    <div class="chart-shell">
      <div ref="chartHost" class="chart-host" />
      <canvas ref="overlay" class="footprint-overlay" />
      <div v-if="!chart?.bars.length" class="empty-chart">Waiting for aggregated trades</div>
      <div v-if="hover" class="hover-readout">
        <b>{{ new Date(hover.bar.startTs).toLocaleTimeString() }}</b>
        <span>O {{ formatPrice(hover.bar.open) }}</span>
        <span>H {{ formatPrice(hover.bar.high) }}</span>
        <span>L {{ formatPrice(hover.bar.low) }}</span>
        <span>C {{ formatPrice(hover.bar.close) }}</span>
        <span>D {{ formatSigned(hover.bar.delta) }}</span>
        <span v-if="hover.price">P {{ formatPrice(hover.price) }}</span>
      </div>
    </div>
    <footer class="chart-footer">
      <span><i class="legend poc" /> POC</span>
      <span><i class="legend buy" /> BUY IMBALANCE</span>
      <span><i class="legend sell" /> SELL IMBALANCE</span>
      <span>{{ Math.min(40, Math.max(0, visibleBars)) }} VISIBLE / 6-40</span>
    </footer>
  </section>
</template>

<style scoped>
.flow-chart { height: 100%; min-height: 0; display: grid; grid-template-rows: 34px minmax(0, 1fr) 25px; overflow: hidden; border: 1px solid var(--border); background: #0b1016; }
.chart-header, .chart-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 9px; background: var(--panel-deep); color: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.chart-header { border-bottom: 1px solid var(--border); }
.chart-footer { justify-content: flex-start; border-top: 1px solid var(--border); overflow: hidden; white-space: nowrap; }
.chart-footer span:last-child { margin-left: auto; }
.identity, .readout { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.identity strong { color: var(--text); font-size: 11px; }
.identity span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.readout b { margin-left: 3px; color: var(--text); }
.readout b.buy { color: var(--bid); }
.readout b.sell { color: var(--ask); }
.chart-shell { position: relative; min-height: 0; overflow: hidden; }
.chart-host { position: absolute; inset: 0; }
.footprint-overlay { position: absolute; inset: 0; pointer-events: none; z-index: 3; }
.hover-readout { position: absolute; top: 7px; left: 8px; z-index: 4; display: flex; gap: 8px; padding: 4px 6px; border: 1px solid #344353; background: rgba(10, 16, 23, 0.9); color: #aab6c4; font-size: 9px; font-variant-numeric: tabular-nums; pointer-events: none; }
.hover-readout b { color: var(--text); }
.empty-chart { position: absolute; inset: 0; z-index: 5; display: grid; place-items: center; color: var(--muted); font-size: 11px; pointer-events: none; }
.legend { display: inline-block; width: 8px; height: 8px; margin-right: 3px; border: 1px solid currentColor; vertical-align: -1px; }
.legend.poc { color: #f2c94c; }
.legend.buy { color: #39d99a; }
.legend.sell { color: #ff7180; }
@media (max-width: 720px) {
  .flow-chart { grid-template-rows: 53px minmax(0, 1fr) 25px; }
  .chart-header { align-content: center; flex-wrap: wrap; gap: 1px 8px; padding: 4px 7px; }
  .identity, .readout { width: 100%; gap: 7px; }
  .readout { font-size: 9px; }
  .chart-footer span:nth-child(2), .chart-footer span:nth-child(3) { display: none; }
  .hover-readout { max-width: calc(100% - 16px); flex-wrap: wrap; gap: 2px 7px; }
}
</style>
