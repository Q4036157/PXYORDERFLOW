<script setup lang="ts">
import { computed } from "vue";
import type { FootprintBar, FootprintBin } from "../types";

const props = defineProps<{
  bar: FootprintBar | null;
}>();

const rows = computed(() => {
  const bins: FootprintBin[] = props.bar?.bins ? [...props.bar.bins] : [];
  // 高价在上，贴近 DOM 阅读习惯
  bins.sort((a, b) => b.price - a.price);
  const maxVol = Math.max(
    0.0001,
    ...bins.map((b) => Math.max(b.buyVol || 0, b.sellVol || 0)),
  );
  return bins.map((b) => ({
    ...b,
    buyPct: ((b.buyVol || 0) / maxVol) * 100,
    sellPct: ((b.sellVol || 0) / maxVol) * 100,
  }));
});

const totalDelta = computed(() => props.bar?.totalDelta ?? 0);
const cvd = computed(() => props.bar?.cvd ?? 0);

function fmt(n: number, d = 2): string {
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(d);
}

function fmtSigned(n: number, d = 2): string {
  if (!Number.isFinite(n)) return "-";
  const s = n.toFixed(d);
  return n > 0 ? `+${s}` : s;
}
</script>

<template>
  <div class="fp">
    <div class="head">
      <div class="title">
        <span>Footprint</span>
        <span v-if="bar" class="sub">
          {{ bar.intervalMs / 1000 }}s · {{ bar.symbol }}
        </span>
      </div>
      <div class="stats">
        <span>
          Δ
          <b :class="totalDelta >= 0 ? 'pos' : 'neg'">{{ fmtSigned(totalDelta, 3) }}</b>
        </span>
        <span>
          CVD
          <b :class="cvd >= 0 ? 'pos' : 'neg'">{{ fmtSigned(cvd, 3) }}</b>
        </span>
      </div>
    </div>

    <div class="col-head">
      <span>买量</span>
      <span>价</span>
      <span>卖量</span>
      <span>笔</span>
      <span>Δ</span>
    </div>

    <div class="body">
      <div v-if="!rows.length" class="empty">等待成交聚合…</div>
      <div v-for="r in rows" :key="r.price" class="row">
        <div class="vol buy">
          <i class="bar" :style="{ width: r.buyPct + '%' }" />
          <span>{{ r.buyVol ? fmt(r.buyVol, 3) : "" }}</span>
        </div>
        <div class="px">{{ fmt(r.price, 2) }}</div>
        <div class="vol sell">
          <i class="bar" :style="{ width: r.sellPct + '%' }" />
          <span>{{ r.sellVol ? fmt(r.sellVol, 3) : "" }}</span>
        </div>
        <div class="cnt">{{ r.tradeCount || "" }}</div>
        <div class="delta" :class="r.delta >= 0 ? 'pos' : 'neg'">
          {{ r.delta ? fmtSigned(r.delta, 3) : "" }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fp {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.title {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}
.title .sub {
  text-transform: none;
  letter-spacing: 0;
  opacity: 0.85;
}
.stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.stats b {
  font-weight: 600;
  margin-left: 4px;
}
.pos {
  color: var(--bid);
}
.neg {
  color: var(--ask);
}
.col-head,
.row {
  display: grid;
  grid-template-columns: 1fr 64px 1fr 36px 56px;
  gap: 4px;
  align-items: center;
}
.col-head {
  padding: 4px 8px;
  font-size: 11px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.body {
  overflow: auto;
  flex: 1;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}
.empty {
  padding: 16px;
  text-align: center;
  color: var(--muted);
}
.row {
  padding: 0 6px;
  height: 18px;
}
.vol {
  position: relative;
  height: 16px;
  overflow: hidden;
  border-radius: 2px;
}
.vol span {
  position: relative;
  z-index: 1;
  padding: 0 4px;
  line-height: 16px;
}
.vol.buy {
  text-align: right;
  color: var(--bid);
}
.vol.sell {
  text-align: left;
  color: var(--ask);
}
.bar {
  position: absolute;
  top: 0;
  bottom: 0;
  opacity: 0.22;
  pointer-events: none;
}
.vol.buy .bar {
  right: 0;
  background: var(--bid);
}
.vol.sell .bar {
  left: 0;
  background: var(--ask);
}
.px {
  text-align: center;
  font-weight: 600;
  font-size: 11px;
}
.cnt {
  text-align: right;
  color: var(--muted);
}
.delta {
  text-align: right;
  font-weight: 600;
}
</style>
