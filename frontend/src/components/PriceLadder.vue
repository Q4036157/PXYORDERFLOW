<script setup lang="ts">
import { computed } from "vue";
import type { BookLevel, OwnOrder, Side } from "../types";

const props = defineProps<{
  bids: BookLevel[];
  asks: BookLevel[];
  ownOrders: OwnOrder[];
  centerRows?: number;
}>();

const emit = defineEmits<{
  clickLevel: [payload: { side: Side; price: number }];
  cancelOrder: [orderId: string];
}>();

const rows = computed(() => {
  const n = props.centerRows ?? 40;
  const asks = [...props.asks].sort((a, b) => a.price - b.price).slice(0, n).reverse();
  const bids = [...props.bids].sort((a, b) => b.price - a.price).slice(0, n);
  const maxQty = Math.max(
    0.0001,
    ...asks.map((x) => x.qty),
    ...bids.map((x) => x.qty),
  );

  const ownByPrice = new Map<number, OwnOrder[]>();
  for (const o of props.ownOrders) {
    const key = Number(o.price);
    const list = ownByPrice.get(key) || [];
    list.push(o);
    ownByPrice.set(key, list);
  }

  type Row = {
    key: string;
    price: number;
    bidQty: number;
    askQty: number;
    bidPct: number;
    askPct: number;
    own: OwnOrder[];
  };

  const out: Row[] = [];
  for (const a of asks) {
    out.push({
      key: `a-${a.price}`,
      price: a.price,
      bidQty: 0,
      askQty: a.qty,
      bidPct: 0,
      askPct: (a.qty / maxQty) * 100,
      own: ownByPrice.get(a.price) || [],
    });
  }
  for (const b of bids) {
    out.push({
      key: `b-${b.price}`,
      price: b.price,
      bidQty: b.qty,
      askQty: 0,
      bidPct: (b.qty / maxQty) * 100,
      askPct: 0,
      own: ownByPrice.get(b.price) || [],
    });
  }
  return out;
});

function fmt(n: number, d = 2): string {
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(d);
}

function onBuy(price: number) {
  emit("clickLevel", { side: "buy", price });
}
function onSell(price: number) {
  emit("clickLevel", { side: "sell", price });
}
</script>

<template>
  <div class="ladder">
    <div class="head">
      <span>买量</span>
      <span>价格</span>
      <span>卖量</span>
      <span>挂单</span>
    </div>
    <div class="body">
      <div v-for="row in rows" :key="row.key" class="row">
        <button class="bid-cell" type="button" @click="onBuy(row.price)">
          <i class="bar bid" :style="{ width: row.bidPct + '%' }" />
          <span>{{ row.bidQty ? fmt(row.bidQty, 4) : "" }}</span>
        </button>
        <div class="px" :class="{ mid: row.bidQty && row.askQty }">{{ fmt(row.price, 2) }}</div>
        <button class="ask-cell" type="button" @click="onSell(row.price)">
          <i class="bar ask" :style="{ width: row.askPct + '%' }" />
          <span>{{ row.askQty ? fmt(row.askQty, 4) : "" }}</span>
        </button>
        <div class="own">
          <button
            v-for="o in row.own"
            :key="o.orderId"
            type="button"
            class="own-chip"
            :class="o.side"
            :title="`${o.side} ${o.qty} @ ${o.price}`"
            @click.stop="emit('cancelOrder', o.orderId)"
          >
            {{ o.side === "buy" ? "B" : "S" }}{{ o.qty }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ladder {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.head,
.row {
  display: grid;
  grid-template-columns: 1fr 88px 1fr 72px;
  gap: 4px;
  align-items: center;
}
.head {
  padding: 8px 10px;
  color: var(--muted);
  font-size: 12px;
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.body {
  overflow: auto;
  flex: 1;
  font-variant-numeric: tabular-nums;
}
.row {
  padding: 1px 6px;
  height: 22px;
}
.bid-cell,
.ask-cell {
  position: relative;
  height: 20px;
  border: 0;
  background: transparent;
  padding: 0 6px;
  overflow: hidden;
  border-radius: 2px;
}
.bid-cell {
  text-align: right;
  color: var(--bid);
}
.ask-cell {
  text-align: left;
  color: var(--ask);
}
.bid-cell:hover {
  background: rgba(22, 199, 132, 0.12);
}
.ask-cell:hover {
  background: rgba(234, 57, 67, 0.12);
}
.bar {
  position: absolute;
  top: 0;
  bottom: 0;
  opacity: 0.18;
  pointer-events: none;
}
.bar.bid {
  right: 0;
  background: var(--bid);
}
.bar.ask {
  left: 0;
  background: var(--ask);
}
.px {
  text-align: center;
  font-weight: 600;
  font-size: 12px;
}
.px.mid {
  color: var(--mid);
}
.own {
  display: flex;
  gap: 2px;
  justify-content: flex-end;
}
.own-chip {
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
  line-height: 16px;
}
.own-chip.buy {
  color: var(--bid);
  border-color: #1f5a40;
}
.own-chip.sell {
  color: var(--ask);
  border-color: #5a1f28;
}
</style>
