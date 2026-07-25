<script setup lang="ts">
import { computed, ref } from "vue";
import { X } from "@lucide/vue";
import type { OwnOrder, PositionRow, FillRow } from "../types";

const props = withDefaults(defineProps<{
  orders: OwnOrder[];
  positions?: PositionRow[];
  fills?: FillRow[];
  cancelLocked?: boolean;
  cancellingOrderIds?: string[];
}>(), {
  positions: () => [],
  fills: () => [],
  cancelLocked: true,
  cancellingOrderIds: () => [],
});

const emit = defineEmits<{ cancelOrder: [cancelId: string] }>();
const active = ref<"orders" | "positions" | "fills">("orders");
const count = computed(() => ({
  orders: props.orders.length,
  positions: props.positions.length,
  fills: props.fills.length,
}));

function number(value: number, digits = 4): string {
  return Number.isFinite(value) ? value.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "") : "-";
}
</script>

<template>
  <section class="orders-panel" aria-label="Orders positions and fills">
    <nav class="tabs" aria-label="Trading records">
      <button type="button" :class="{ active: active === 'orders' }" @click="active = 'orders'">WORKING ORDERS <span>{{ count.orders }}</span></button>
      <button type="button" :class="{ active: active === 'positions' }" @click="active = 'positions'">POSITIONS <span>{{ count.positions }}</span></button>
      <button type="button" :class="{ active: active === 'fills' }" @click="active = 'fills'">FILLS <span>{{ count.fills }}</span></button>
    </nav>

    <div v-if="active === 'orders'" class="table-wrap">
      <div class="table order-grid table-head"><span>SIDE</span><span>PRICE</span><span>QTY</span><span>FILLED</span><span>STATUS</span><span>CLIENT / EXCHANGE</span><span /></div>
      <div v-for="order in orders" :key="order.ofClientId || order.cancelId" class="table order-grid table-row">
        <span :class="order.side">{{ order.side.toUpperCase() }}</span>
        <span>{{ number(order.price, 8) }}</span>
        <span>{{ number(order.qty, 8) }}</span>
        <span>{{ number(order.filledQty || 0, 8) }}</span>
        <span>{{ order.status.toUpperCase() }}</span>
        <span class="identifier" :title="`${order.ofClientId || '-'} / ${order.orderId || '-'}`">{{ order.ofClientId || order.orderId || "-" }}</span>
        <button
          type="button"
          class="cancel"
          :title="order.cancelReason || 'Cancel this order'"
          :disabled="cancelLocked || !order.cancelId || order.cancellable === false || cancellingOrderIds.includes(order.cancelId)"
          @click="emit('cancelOrder', order.cancelId)"
        ><X :size="13" /></button>
      </div>
      <div v-if="!orders.length" class="empty">NO WORKING ORDERS</div>
    </div>

    <div v-else-if="active === 'positions'" class="table-wrap">
      <div class="table position-grid table-head"><span>SYMBOL</span><span>SIDE</span><span>QTY</span><span>ENTRY</span><span>MARK</span><span>UPNL</span></div>
      <div v-for="position in positions" :key="`${position.symbol}-${position.side}`" class="table position-grid table-row">
        <span>{{ position.symbol }}</span><span :class="position.side">{{ position.side.toUpperCase() }}</span><span>{{ number(position.qty, 8) }}</span><span>{{ number(position.entryPrice, 8) }}</span><span>{{ number(position.markPrice, 8) }}</span><span :class="position.unrealizedPnl >= 0 ? 'buy' : 'sell'">{{ number(position.unrealizedPnl, 4) }}</span>
      </div>
      <div v-if="!positions.length" class="empty">NO OPEN POSITIONS</div>
    </div>

    <div v-else class="table-wrap">
      <div class="table fill-grid table-head"><span>TIME</span><span>SIDE</span><span>PRICE</span><span>QTY</span><span>FEE</span><span>ORDER</span></div>
      <div v-for="fill in fills" :key="fill.id" class="table fill-grid table-row">
        <span>{{ new Date(fill.ts).toLocaleTimeString() }}</span><span :class="fill.side">{{ fill.side.toUpperCase() }}</span><span>{{ number(fill.price, 8) }}</span><span>{{ number(fill.qty, 8) }}</span><span>{{ number(fill.fee || 0, 8) }}</span><span class="identifier">{{ fill.orderId }}</span>
      </div>
      <div v-if="!fills.length" class="empty">NO FILLS IN THIS SESSION</div>
    </div>
  </section>
</template>

<style scoped>
.orders-panel { min-height: 0; display: grid; grid-template-rows: 31px minmax(0, 1fr); border: 1px solid var(--border); background: var(--panel-deep); overflow: hidden; }
.tabs { display: flex; border-bottom: 1px solid var(--border); }
.tabs button { height: 30px; padding: 0 12px; border: 0; border-right: 1px solid var(--border); border-radius: 0; background: transparent; color: var(--muted); font-size: 10px; }
.tabs button.active { color: var(--text); background: #18212b; box-shadow: inset 0 -2px var(--brand); }
.tabs span { margin-left: 5px; color: #738195; }
.table-wrap { min-height: 0; overflow: auto; font-size: 10px; font-variant-numeric: tabular-nums; }
.table { display: grid; align-items: center; min-width: 690px; }
.order-grid { grid-template-columns: 64px 105px 90px 90px 92px minmax(180px, 1fr) 34px; }
.position-grid { grid-template-columns: 1fr 75px 1fr 1fr 1fr 1fr; }
.fill-grid { grid-template-columns: 100px 70px 1fr 1fr 1fr minmax(150px, 1fr); }
.table-head { position: sticky; top: 0; z-index: 1; min-height: 25px; padding: 0 8px; color: var(--muted); background: #10161e; border-bottom: 1px solid var(--border); }
.table-row { min-height: 25px; padding: 0 8px; border-bottom: 1px solid rgba(39, 49, 61, 0.62); color: #c9d3de; }
.table-row:hover { background: rgba(72, 88, 106, 0.11); }
.buy { color: var(--bid); }
.sell { color: var(--ask); }
.identifier { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8d9bad; }
.cancel { width: 25px; height: 21px; display: grid; place-items: center; padding: 0; color: var(--ask); border-color: #53313a; }
.cancel:disabled { cursor: not-allowed; opacity: 0.4; }
.empty { min-height: 72px; display: grid; place-items: center; color: #657486; font-size: 10px; }
@media (max-width: 720px) {
  .tabs button { flex: 1; min-width: 0; padding: 0 5px; }
  .orders-panel { min-height: 440px; }
}
</style>
