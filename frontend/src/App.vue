<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import PriceLadder from "./components/PriceLadder.vue";
import OrderTicket from "./components/OrderTicket.vue";
import FootprintPanel from "./components/FootprintPanel.vue";
import {
  cancelAll,
  cancelOrder,
  connectWs,
  fetchAccounts,
  fetchHealth,
  fetchOpenOrders,
  fetchState,
  placeOrder,
} from "./api";
import type {
  Account,
  BookLevel,
  FootprintBar,
  OwnOrder,
  Side,
  TradeTick,
} from "./types";

const accounts = ref<Account[]>([]);
const accountId = ref("");
const qty = ref(0.01);
const postOnly = ref(false);
const bids = ref<BookLevel[]>([]);
const asks = ref<BookLevel[]>([]);
const ownOrders = ref<OwnOrder[]>([]);
const tape = ref<TradeTick[]>([]);
const footprint = ref<FootprintBar | null>(null);
const lastMsg = ref("");
const health = ref<Record<string, unknown>>({});
let ws: WebSocket | null = null;

function applyBook(data: any) {
  if (!data) return;
  bids.value = data.bids || [];
  asks.value = data.asks || [];
}

function applyFootprint(data: any, cvdFallback?: number) {
  if (!data) return;
  footprint.value = {
    symbol: data.symbol || "",
    intervalMs: data.intervalMs || 0,
    startTs: data.startTs || 0,
    bins: data.bins || [],
    totalDelta: data.totalDelta ?? 0,
    cvd: data.cvd ?? cvdFallback ?? footprint.value?.cvd ?? 0,
  };
}

function onWs(msg: any) {
  if (msg.type === "hello" || msg.type === "book") {
    applyBook(msg.data?.book || msg.data);
    if (msg.type === "hello") {
      if (msg.data?.tape) tape.value = msg.data.tape;
      if (msg.data?.footprint) {
        applyFootprint(msg.data.footprint, msg.data.cvd);
      } else if (typeof msg.data?.cvd === "number") {
        // 仅有 CVD 时保留现有 bar 的 cvd
        if (footprint.value) {
          footprint.value = { ...footprint.value, cvd: msg.data.cvd };
        }
      }
    }
  } else if (msg.type === "footprint") {
    applyFootprint(msg.data);
  } else if (msg.type === "trade") {
    tape.value = [msg.data, ...tape.value].slice(0, 40);
  } else if (msg.type === "order") {
    const d = msg.data;
    lastMsg.value = d.success
      ? `下单成功 ${d.side} ${d.qty} @ ${d.price} id=${d.orderId}`
      : `下单失败: ${d.message || "unknown"}`;
    if (d.success && d.orderId) {
      ownOrders.value = [
        {
          orderId: d.orderId,
          ofClientId: d.ofClientId,
          side: d.side,
          price: d.price,
          qty: d.qty,
          status: "open",
        },
        ...ownOrders.value.filter((o) => o.orderId !== d.orderId),
      ];
    }
  } else if (msg.type === "orders_cleared") {
    ownOrders.value = [];
    lastMsg.value = msg.data?.message || "全部撤单";
  }
}

async function onClickLevel(payload: { side: Side; price: number }) {
  if (!accountId.value) {
    lastMsg.value = "请先选择账户";
    return;
  }
  if (qty.value <= 0) {
    lastMsg.value = "数量必须 > 0";
    return;
  }
  lastMsg.value = `提交 ${payload.side} ${qty.value} @ ${payload.price} ...`;
  const res = await placeOrder({
    accountId: accountId.value,
    side: payload.side,
    price: payload.price,
    qty: qty.value,
    postOnly: postOnly.value,
  });
  if (!res.success) {
    lastMsg.value = `失败: ${res.message || "unknown"}`;
  }
}

async function onCancelOrder(orderId: string) {
  if (!accountId.value) return;
  const res = await cancelOrder({ accountId: accountId.value, orderId });
  if (res.success) {
    ownOrders.value = ownOrders.value.filter((o) => o.orderId !== orderId);
    lastMsg.value = `已撤 ${orderId}`;
  } else {
    lastMsg.value = `撤单失败: ${res.message || ""}`;
  }
}

async function onCancelAll() {
  if (!accountId.value) return;
  const ok = window.confirm("确认全部撤单？可能影响同账户其他策略挂单。");
  if (!ok) return;
  const res = await cancelAll({
    accountId: accountId.value,
    confirmed: true,
  });
  if (res.success) {
    ownOrders.value = [];
    lastMsg.value = res.message || "全部撤单完成";
  } else {
    lastMsg.value = `全部撤单失败: ${res.message || ""}`;
  }
}

onMounted(async () => {
  try {
    health.value = await fetchHealth();
  } catch (e) {
    lastMsg.value = `API 未就绪: ${e}`;
  }
  try {
    accounts.value = await fetchAccounts();
    if (accounts.value.length) accountId.value = accounts.value[0].id;
  } catch {
    /* mock 后端未起时忽略 */
  }
  try {
    const st = await fetchState();
    applyBook(st.book);
    if (st.tape) tape.value = st.tape;
    if (st.footprint) applyFootprint(st.footprint, st.cvd);
  } catch {
    /* ignore */
  }
  if (accountId.value) {
    try {
      ownOrders.value = await fetchOpenOrders(accountId.value);
    } catch {
      /* ignore */
    }
  }
  ws = connectWs(onWs);
});

onUnmounted(() => {
  ws?.close();
});
</script>

<template>
  <div class="shell">
    <header>
      <div class="brand">
        <strong>PXYORDERFLOW</strong>
        <span>Lighter DOM / Order Flow</span>
      </div>
      <div class="meta">
        <span>md={{ health.mdMode || "-" }}</span>
        <span>trade={{ health.tradeMode || "-" }}</span>
        <span :class="health.tradingEnabled ? 'on' : 'off'">
          OF_TRADING={{ health.tradingEnabled ? "on" : "off" }}
        </span>
      </div>
    </header>

    <main>
      <section class="fp-wrap">
        <FootprintPanel :bar="footprint" />
      </section>
      <section class="ladder-wrap">
        <PriceLadder
          :bids="bids"
          :asks="asks"
          :own-orders="ownOrders"
          @click-level="onClickLevel"
          @cancel-order="onCancelOrder"
        />
      </section>
      <aside>
        <h3>Tape</h3>
        <div class="tape">
          <div v-for="(t, i) in tape" :key="i" class="t" :class="t.side">
            <span>{{ t.side }}</span>
            <span>{{ Number(t.price).toFixed(2) }}</span>
            <span>{{ Number(t.qty).toFixed(4) }}</span>
          </div>
        </div>
      </aside>
    </main>

    <OrderTicket
      v-model:account-id="accountId"
      v-model:qty="qty"
      v-model:post-only="postOnly"
      :accounts="accounts"
      :last-msg="lastMsg"
      @cancel-all="onCancelAll"
    />
  </div>
</template>

<style scoped>
.shell {
  height: 100%;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 10px;
  padding: 12px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: baseline;
}
.brand strong {
  letter-spacing: 0.06em;
  font-size: 16px;
}
.brand span,
.meta {
  color: var(--muted);
  font-size: 12px;
}
.meta {
  display: flex;
  gap: 12px;
}
.meta .on {
  color: var(--bid);
}
.meta .off {
  color: var(--ask);
}
main {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(320px, 1.4fr) 220px;
  gap: 10px;
}
.fp-wrap,
.ladder-wrap,
aside {
  min-height: 0;
}
aside {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  display: flex;
  flex-direction: column;
}
aside h3 {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.tape {
  overflow: auto;
  flex: 1;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}
.t {
  display: grid;
  grid-template-columns: 40px 1fr 1fr;
  gap: 6px;
  padding: 2px 0;
}
.t.buy {
  color: var(--bid);
}
.t.sell {
  color: var(--ask);
}
</style>
