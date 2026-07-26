<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { LocateFixed, X } from "@lucide/vue";
import type { BookLevel, OwnOrder, Side } from "../types";

const props = withDefaults(defineProps<{
  bids: BookLevel[];
  asks: BookLevel[];
  ownOrders: OwnOrder[];
  centerRows?: number;
  locked?: boolean;
  interactionMode?: "armed" | "cancel-only" | "locked";
  lockReason?: string;
  cancelLocked?: boolean;
  cancellingOrderIds?: string[];
}>(), {
  centerRows: 30,
  locked: false,
  interactionMode: "locked",
  lockReason: "Order entry is locked.",
  cancelLocked: true,
  cancellingOrderIds: () => [],
});

const emit = defineEmits<{
  clickLevel: [payload: { side: Side; price: number }];
  cancelOrder: [orderId: string];
}>();
const body = ref<HTMLDivElement | null>(null);

type LadderRow = {
  key: string;
  price: number;
  bidQty: number;
  askQty: number;
  bidPct: number;
  askPct: number;
  own: OwnOrder[];
};

const rows = computed<LadderRow[]>(() => {
  const rawAsks = [...props.asks].sort((a, b) => a.price - b.price).slice(0, props.centerRows);
  const rawBids = [...props.bids].sort((a, b) => b.price - a.price).slice(0, props.centerRows);
  const localBestAsk = rawAsks[0]?.price ?? Number.POSITIVE_INFINITY;
  const localBestBid = rawBids[0]?.price ?? Number.NEGATIVE_INFINITY;
  const localMid = Number.isFinite(localBestAsk) && Number.isFinite(localBestBid)
    ? (localBestAsk + localBestBid) / 2
    : Number.isFinite(localBestAsk) ? localBestAsk : localBestBid;
  const ownByPrice = new Map<number, OwnOrder[]>();
  for (const order of props.ownOrders) {
    const existing = ownByPrice.get(Number(order.price)) || [];
    existing.push(order);
    ownByPrice.set(Number(order.price), existing);
  }
  const askMap = new Map(rawAsks.map((level) => [Number(level.price), level]));
  const bidMap = new Map(rawBids.map((level) => [Number(level.price), level]));
  for (const price of ownByPrice.keys()) {
    const target = price >= localMid ? askMap : bidMap;
    if (!target.has(price)) target.set(price, { price, qty: 0 });
  }
  const asks = [...askMap.values()].sort((a, b) => a.price - b.price).reverse();
  const bids = [...bidMap.values()].sort((a, b) => b.price - a.price);
  const maxQty = Math.max(0.0001, ...asks.map((row) => row.qty), ...bids.map((row) => row.qty));

  return [
    ...asks.map((level) => ({
      key: `ask-${level.price}`,
      price: level.price,
      bidQty: 0,
      askQty: level.qty,
      bidPct: 0,
      askPct: (level.qty / maxQty) * 100,
      own: ownByPrice.get(Number(level.price)) || [],
    })),
    ...bids.map((level) => ({
      key: `bid-${level.price}`,
      price: level.price,
      bidQty: level.qty,
      askQty: 0,
      bidPct: (level.qty / maxQty) * 100,
      askPct: 0,
      own: ownByPrice.get(Number(level.price)) || [],
    })),
  ];
});

const firstBidIndex = computed(() => rows.value.findIndex((row) => row.key.startsWith("bid-")));
const bestBid = computed(() => Math.max(...props.bids.map((row) => row.price), Number.NEGATIVE_INFINITY));
const bestAsk = computed(() => Math.min(...props.asks.map((row) => row.price), Number.POSITIVE_INFINITY));
const midPrice = computed(() => {
  if (Number.isFinite(bestBid.value) && Number.isFinite(bestAsk.value)) return (bestBid.value + bestAsk.value) / 2;
  return Number.isFinite(bestBid.value) ? bestBid.value : bestAsk.value;
});
const spread = computed(() =>
  Number.isFinite(bestBid.value) && Number.isFinite(bestAsk.value) ? bestAsk.value - bestBid.value : Number.NaN,
);
const interactionLabel = computed(() => {
  if (props.interactionMode === "armed") return "ARMED";
  if (props.interactionMode === "cancel-only") return "CANCEL ONLY";
  return "LOCKED";
});

function format(value: number, digits = 2): string {
  return Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function recenter(): void {
  void nextTick(() => body.value?.querySelector(".mid-row")?.scrollIntoView({ block: "center" }));
}

watch(() => `${bestBid.value}:${bestAsk.value}`, (next, previous) => {
  if (!previous || previous === "-Infinity:Infinity") recenter();
});
watch(() => rows.value.length, recenter, { flush: "post" });
onMounted(recenter);
</script>

<template>
  <div class="ladder" :class="interactionMode" :title="locked ? lockReason : 'Click the buy or sell column to place a limit order.'">
    <div class="toolbar">
      <strong>DOM</strong>
      <span>{{ rows.length }} LEVELS</span>
      <span class="interaction" :class="interactionMode">{{ interactionLabel }}</span>
      <button type="button" title="Recenter depth ladder" @click="recenter"><LocateFixed :size="14" /></button>
    </div>
    <div class="head">
      <span>BUY</span>
      <span>PRICE</span>
      <span>SELL</span>
      <span>ORD</span>
    </div>
    <div ref="body" class="body">
      <template v-for="(row, index) in rows" :key="row.key">
        <div v-if="index === firstBidIndex" class="mid-row">
          <span>MID {{ format(midPrice, 2) }}</span>
          <span>SPREAD {{ format(spread, 2) }}</span>
        </div>
        <div class="row" :class="{ own: row.own.length }">
          <button class="bid-cell" type="button" :disabled="locked" :aria-label="`Buy at ${row.price}`" :title="locked ? lockReason : `Buy at ${row.price}`" @click="emit('clickLevel', { side: 'buy', price: row.price })">
            <i class="bar bid" :style="{ width: `${row.bidPct}%` }" />
            <span :class="{ action: !row.bidQty }">{{ row.bidQty ? format(row.bidQty, 4) : "B" }}</span>
          </button>
          <div class="px">{{ format(row.price, 2) }}</div>
          <button class="ask-cell" type="button" :disabled="locked" :aria-label="`Sell at ${row.price}`" :title="locked ? lockReason : `Sell at ${row.price}`" @click="emit('clickLevel', { side: 'sell', price: row.price })">
            <i class="bar ask" :style="{ width: `${row.askPct}%` }" />
            <span :class="{ action: !row.askQty }">{{ row.askQty ? format(row.askQty, 4) : "S" }}</span>
          </button>
          <div class="own">
            <button
              v-for="order in row.own"
              :key="order.ofClientId || order.cancelId"
              type="button"
              class="own-chip"
              :class="order.side"
              :disabled="cancelLocked || !order.cancelId || order.cancellable === false || cancellingOrderIds.includes(order.cancelId)"
              :title="order.cancelReason || `${order.side} ${order.qty} @ ${order.price}`"
              @click.stop="emit('cancelOrder', order.cancelId)"
            >
              <span>{{ order.side === "buy" ? "B" : "S" }}{{ order.qty }}</span>
              <X v-if="!cancellingOrderIds.includes(order.cancelId)" :size="9" />
              <span v-else>...</span>
            </button>
          </div>
        </div>
      </template>
      <div v-if="!rows.length" class="empty">Waiting for depth</div>
    </div>
    <div class="ladder-footer"><span>CLICK BUY TO BID</span><span>CLICK SELL TO OFFER</span></div>
  </div>
</template>

<style scoped>
.ladder { display: flex; flex-direction: column; height: 100%; min-height: 0; background: var(--panel-deep); border: 1px solid var(--border); overflow: hidden; }
.toolbar { min-height: 31px; display: flex; align-items: center; gap: 8px; padding: 0 7px; border-bottom: 1px solid var(--border); color: var(--muted); font-size: 9px; }
.toolbar strong { color: var(--text); font-size: 11px; }
.toolbar button { width: 26px; height: 24px; display: grid; place-items: center; padding: 0; }
.interaction { margin-left: auto; padding: 2px 4px; border: 1px solid var(--border); color: var(--mid); font-size: 9px; font-weight: 700; }
.interaction.armed { color: var(--bid); border-color: #216e4e; background: #11291f; }
.interaction.cancel-only { color: var(--mid); border-color: #67501f; background: #27200f; }
.interaction.locked { color: var(--muted); }
.head, .row { display: grid; grid-template-columns: minmax(64px, 1fr) 78px minmax(64px, 1fr) 52px; gap: 3px; align-items: center; }
.head { min-height: 31px; padding: 0 6px; color: var(--muted); font-size: 10px; border-bottom: 1px solid var(--border); letter-spacing: 0.05em; }
.body { overflow: auto; flex: 1; font-variant-numeric: tabular-nums; }
.row { padding: 0 4px; height: 20px; }
.bid-cell, .ask-cell { position: relative; height: 20px; border: 0; background: transparent; padding: 0 4px; overflow: hidden; border-radius: 0; font-size: 11px; }
.bid-cell { text-align: right; color: var(--bid); }
.ask-cell { text-align: left; color: var(--ask); }
.ladder.armed .bid-cell:not(:disabled):hover { background: rgba(20, 199, 132, 0.18); box-shadow: inset 2px 0 var(--bid); }
.ladder.armed .ask-cell:not(:disabled):hover { background: rgba(239, 82, 93, 0.18); box-shadow: inset -2px 0 var(--ask); }
.bid-cell:not(:disabled):active, .ask-cell:not(:disabled):active { transform: translateY(1px); filter: brightness(1.2); }
.action { opacity: 0.58; font-size: 9px; font-weight: 700; }
.bar { position: absolute; top: 0; bottom: 0; opacity: 0.22; pointer-events: none; }
.bar.bid { right: 0; background: var(--bid); }
.bar.ask { left: 0; background: var(--ask); }
.bid-cell span, .ask-cell span { position: relative; z-index: 1; }
.px { text-align: center; font-weight: 650; font-size: 11px; color: #dbe4ed; }
.own { display: flex; gap: 1px; justify-content: flex-end; overflow: hidden; }
.own-chip { max-width: 50px; overflow: hidden; text-overflow: ellipsis; font-size: 9px; padding: 0 3px; height: 17px; line-height: 15px; border-radius: 0; display: inline-flex; align-items: center; gap: 2px; }
.own-chip.buy { color: var(--bid); border-color: #1f5a40; }
.own-chip.sell { color: var(--ask); border-color: #5a1f28; }
.mid-row { height: 23px; padding: 0 7px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #344556; border-bottom: 1px solid #344556; color: var(--mid); font-size: 10px; font-variant-numeric: tabular-nums; background: #161e28; }
.empty { padding: 18px 8px; color: var(--muted); text-align: center; font-size: 11px; }
.ladder-footer { min-height: 26px; padding: 0 7px; border-top: 1px solid var(--border); color: var(--muted); font-size: 9px; display: flex; align-items: center; justify-content: space-between; }
.ladder.cancel-only .ladder-footer { color: var(--mid); }
button:disabled { cursor: not-allowed; opacity: 0.5; }
</style>
