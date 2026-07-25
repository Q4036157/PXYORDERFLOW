<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import PriceLadder from "./components/PriceLadder.vue";
import OrderTicket from "./components/OrderTicket.vue";
import OrdersPanel from "./components/OrdersPanel.vue";
import FlowCanvas from "./components/FlowCanvas.vue";
import {
  ApiError,
  cancelAll,
  cancelOrder,
  connectWs,
  fetchAccounts,
  fetchChart,
  fetchHealth,
  fetchOpenOrders,
  fetchPortfolio,
  fetchState,
  placeOrder,
} from "./api";
import type {
  Account,
  BookLevel,
  ChartPayload,
  FootprintBar,
  FillRow,
  MarketDataStatus,
  OwnOrder,
  PositionRow,
  Side,
  TradeTick,
} from "./types";

const accounts = ref<Account[]>([]);
const accountId = ref("");
const qty = ref(0.01);
const postOnly = ref(true);
const bids = ref<BookLevel[]>([]);
const asks = ref<BookLevel[]>([]);
const ownOrders = ref<OwnOrder[]>([]);
const positions = ref<PositionRow[]>([]);
const fills = ref<FillRow[]>([]);
const tape = ref<TradeTick[]>([]);
const footprint = ref<FootprintBar | null>(null);
const chart = ref<ChartPayload | null>(null);
const marketData = ref<MarketDataStatus | null>(null);
const lastMsg = ref("");
const health = ref<Record<string, unknown>>({});
const submitting = ref(false);
const cancelAllPending = ref(false);
const cancellingOrderIds = ref<string[]>([]);
const tradeArmed = ref(false);
const sessionState = ref<"checking" | "ready" | "auth" | "gateway" | "unavailable" | "empty">("checking");
const sessionDetail = ref("Checking platform session...");
const submissionId = ref("");
const wsState = ref<"connecting" | "open" | "closed">("closed");
const mobileTab = ref<"chart" | "dom" | "tape" | "orders">("chart");
let ws: WebSocket | null = null;
let reconnectTimer: number | null = null;
let recordsTimer: number | null = null;
let shuttingDown = false;

const activeAccount = computed(() => accounts.value.find((account) => account.id === accountId.value));
const runtimeTradeMode = computed(() => String(health.value.tradeMode || "").toLowerCase());
const executionMode = computed<"LIVE" | "TESTNET" | "MOCK" | "READ ONLY">(() => {
  if (runtimeTradeMode.value === "mock") return "MOCK";
  if (activeAccount.value?.mode === "live") return "LIVE";
  if (activeAccount.value?.mode === "demo" && runtimeTradeMode.value.startsWith("lh")) return "TESTNET";
  return "READ ONLY";
});
const writesEnabled = computed(() => health.value.tradingEnabled === true);
const cancelsEnabled = computed(() => health.value.cancelEnabled === true);
const tradeLockReason = computed(() => {
  if (sessionState.value !== "ready") return sessionDetail.value;
  if (!activeAccount.value) return "No platform-authorized account is available.";
  if (!activeAccount.value.can_trade) return "The platform-authorized account is not enabled for trading.";
  if (wsState.value !== "open") return "Market stream is disconnected. New orders are blocked.";
  const currentBookState = marketData.value?.book?.state || marketData.value?.upstreamBook?.state || "unknown";
  if (currentBookState !== "healthy") return "Order book is not synchronized. New orders are blocked.";
  if (!writesEnabled.value) return String(health.value.tradeStatus || "Execution is disabled by the order-flow service.");
  if (!tradeArmed.value) return "Trading is locally locked. Arm execution before sending orders.";
  if (submitting.value) return "Order submission is in progress.";
  return "";
});
const canSubmit = computed(() => !tradeLockReason.value);
const cancelLockReason = computed(() => {
  if (sessionState.value !== "ready") return sessionDetail.value;
  if (!activeAccount.value) return "No platform-authorized account is available.";
  if (!cancelsEnabled.value) return String(health.value.tradeStatus || "Cancellation client is unavailable.");
  return "";
});
const canCancel = computed(() => !cancelLockReason.value);
const tradeStateText = computed(() => canSubmit.value ? `${executionMode.value} ARMED` : `${executionMode.value} LOCKED`);
const sessionStateText = computed(() => {
  if (sessionState.value === "ready") return "SESSION VERIFIED";
  if (sessionState.value === "auth") return "AUTH REQUIRED";
  if (sessionState.value === "gateway") return "PROXY ERROR";
  if (sessionState.value === "empty") return "NO ACCOUNT";
  if (sessionState.value === "checking") return "SESSION CHECK";
  return "SESSION UNAVAILABLE";
});
const marketState = computed(() => marketData.value?.book?.state || marketData.value?.upstreamBook?.state || "unknown");
const marketStateClass = computed(() => {
  if (marketState.value === "healthy") return "healthy";
  if (marketState.value === "resyncing") return "recovering";
  if (marketState.value === "failed") return "failed";
  return "unknown";
});
const marketStatusText = computed(() => {
  if (marketState.value === "healthy") return "BOOK SYNCED";
  if (marketState.value === "resyncing") return "BOOK RESYNCING";
  if (marketState.value === "failed") return "BOOK DESYNCED";
  return "BOOK STATUS -";
});
const marketStatusError = computed(() => marketData.value?.book?.error || marketData.value?.upstreamBook?.error || "");

function applyBook(data: { bids?: BookLevel[]; asks?: BookLevel[] } | undefined): void {
  if (!data) return;
  bids.value = data.bids || [];
  asks.value = data.asks || [];
}

function applyFootprint(data: Partial<FootprintBar> | undefined, cvdFallback?: number): void {
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

function applyChart(data: ChartPayload | null | undefined): void {
  if (!data || !Array.isArray(data.bars)) return;
  chart.value = data;
}

function applyMarketData(data: MarketDataStatus | null | undefined): void {
  if (data) marketData.value = data;
}

function describeError(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

async function refreshOrderSafetyState(): Promise<void> {
  const selectedAccountId = accountId.value;
  const [nextHealth, nextOrders, nextPortfolio] = await Promise.allSettled([
    fetchHealth(),
    selectedAccountId ? fetchOpenOrders(selectedAccountId) : Promise.resolve([]),
    selectedAccountId
      ? fetchPortfolio(selectedAccountId)
      : Promise.resolve({ positions: [], fills: [] }),
  ]);
  if (nextHealth.status === "fulfilled") health.value = nextHealth.value;
  if (selectedAccountId !== accountId.value) return;
  if (nextOrders.status === "fulfilled") ownOrders.value = nextOrders.value;
  if (nextPortfolio.status === "fulfilled") {
    positions.value = nextPortfolio.value.positions;
    fills.value = nextPortfolio.value.fills;
  }
}

function setSessionFailure(error: unknown): void {
  const detail = describeError(error);
  sessionDetail.value = detail;
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    sessionState.value = "auth";
  } else if (error instanceof ApiError && (error.status === 502 || error.status === 504)) {
    sessionState.value = "gateway";
  } else {
    sessionState.value = "unavailable";
  }
  tradeArmed.value = false;
}

function makeSubmissionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `of-ui-${crypto.randomUUID()}`;
  }
  return `of-ui-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function setTradeArmed(next: boolean): void {
  if (next && ["LIVE", "TESTNET"].includes(executionMode.value)) {
    const target = executionMode.value === "LIVE" ? "the live exchange" : "the exchange testnet";
    const confirmed = window.confirm(`Arm ${executionMode.value} order entry? Orders will be submitted to ${target}.`);
    if (!confirmed) return;
  }
  tradeArmed.value = next;
  lastMsg.value = next
    ? `${executionMode.value} execution armed for ${activeAccount.value?.name || "the authorized account"}.`
    : "Trading locked locally. No new orders can be sent.";
}

function onWs(msg: any): void {
  if (msg.type === "hello" || msg.type === "book") {
    applyBook(msg.data?.book || msg.data);
    if (msg.type === "hello") {
      health.value = {
        ...health.value,
        tradingEnabled: msg.data?.tradingEnabled,
        cancelEnabled: msg.data?.cancelEnabled,
        tradeMode: msg.data?.tradeMode,
        tradeStatus: msg.data?.tradeStatus,
      };
      if (msg.data?.tape) tape.value = msg.data.tape;
      if (msg.data?.footprint) applyFootprint(msg.data.footprint, msg.data.cvd);
      if (msg.data?.chart) applyChart(msg.data.chart);
      if (msg.data?.marketData) applyMarketData(msg.data.marketData);
      else if (typeof msg.data?.cvd === "number" && footprint.value) {
        footprint.value = { ...footprint.value, cvd: msg.data.cvd };
      }
    }
  } else if (msg.type === "footprint") {
    applyFootprint(msg.data);
  } else if (msg.type === "chart") {
    applyChart(msg.data);
  } else if (msg.type === "market_data") {
    applyMarketData(msg.data);
  } else if (msg.type === "trade") {
    tape.value = [msg.data, ...tape.value].slice(0, 80);
  } else if (msg.type === "order") {
    const order = msg.data;
    lastMsg.value = order.success
      ? `Order confirmed: ${order.side} ${order.qty} @ ${order.price} (${order.ofClientId || order.orderId || submissionId.value})`
      : `Order rejected: ${order.message || "unknown"}`;
    if (order.success && order.orderId) {
      ownOrders.value = [
        {
          orderId: order.orderId,
          cancelId: order.cancelId || order.orderId,
          ofClientId: order.ofClientId,
          side: order.side,
          price: order.price,
          qty: order.qty,
          status: "open",
        },
        ...ownOrders.value.filter((item) => item.orderId !== order.orderId),
      ];
    }
  } else if (msg.type === "orders_cleared") {
    ownOrders.value = [];
    lastMsg.value = msg.data?.message || "All orders cancelled.";
  }
}

function connectMarketStream(): void {
  if (shuttingDown) return;
  wsState.value = "connecting";
  ws = connectWs(onWs);
  ws.addEventListener("open", () => { wsState.value = "open"; });
  ws.addEventListener("error", () => {
    wsState.value = "closed";
    tradeArmed.value = false;
  });
  ws.addEventListener("close", () => {
    wsState.value = "closed";
    tradeArmed.value = false;
    if (!shuttingDown) reconnectTimer = window.setTimeout(connectMarketStream, 1500);
  });
}

async function onClickLevel(payload: { side: Side; price: number }): Promise<void> {
  if (submitting.value) return;
  if (!canSubmit.value) {
    lastMsg.value = tradeLockReason.value;
    return;
  }
  if (qty.value <= 0) {
    lastMsg.value = "Quantity must be greater than zero.";
    return;
  }

  submissionId.value = makeSubmissionId();
  submitting.value = true;
  lastMsg.value = `Submitting ${payload.side} ${qty.value} @ ${payload.price} (${submissionId.value})...`;
  try {
    const response = await placeOrder({
      accountId: accountId.value,
      side: payload.side,
      price: payload.price,
      qty: qty.value,
      postOnly: postOnly.value,
      idempotencyKey: submissionId.value,
    });
    if (response.success) {
      lastMsg.value = `Accepted ${response.ofClientId || response.orderId || submissionId.value}. Awaiting order stream confirmation.`;
    } else {
      lastMsg.value = `Order rejected: ${response.message || "unknown"}`;
    }
  } catch (error) {
    tradeArmed.value = false;
    lastMsg.value = `Submit outcome unknown (${submissionId.value}): ${describeError(error)}. Trading relocked.`;
    await refreshOrderSafetyState();
  } finally {
    submitting.value = false;
  }
}

async function onCancelOrder(cancelId: string): Promise<void> {
  if (!accountId.value || cancellingOrderIds.value.includes(cancelId)) return;
  if (!canCancel.value) {
    lastMsg.value = cancelLockReason.value;
    return;
  }
  cancellingOrderIds.value = [...cancellingOrderIds.value, cancelId];
  try {
    const response = await cancelOrder({ accountId: accountId.value, orderId: cancelId });
    if (response.success) {
      ownOrders.value = ownOrders.value.filter((order) => order.cancelId !== cancelId);
      lastMsg.value = `Cancelled ${cancelId}`;
    } else {
      lastMsg.value = `Cancel rejected: ${response.message || "unknown"}`;
    }
  } catch (error) {
    lastMsg.value = `Cancel request failed: ${describeError(error)}`;
  } finally {
    cancellingOrderIds.value = cancellingOrderIds.value.filter((id) => id !== cancelId);
  }
}

async function onCancelAll(): Promise<void> {
  if (!accountId.value || cancelAllPending.value) return;
  if (!canCancel.value) {
    lastMsg.value = cancelLockReason.value;
    return;
  }
  if (!window.confirm("Cancel all orders for the selected order-flow account?")) return;

  cancelAllPending.value = true;
  try {
    const response = await cancelAll({ accountId: accountId.value, confirmed: true });
    if (response.success) {
      ownOrders.value = [];
      lastMsg.value = response.message || "All orders cancelled.";
    } else {
      lastMsg.value = `Cancel all rejected: ${response.message || "unknown"}`;
    }
  } catch (error) {
    lastMsg.value = `Cancel all request failed: ${describeError(error)}`;
  } finally {
    cancelAllPending.value = false;
  }
}

watch(accountId, async (nextAccountId) => {
  ownOrders.value = [];
  positions.value = [];
  fills.value = [];
  tradeArmed.value = false;
  if (!nextAccountId) return;
  try {
    await refreshOrderSafetyState();
  } catch (error) {
    lastMsg.value = `Could not load account records: ${describeError(error)}`;
  }
});

onMounted(async () => {
  try {
    health.value = await fetchHealth();
  } catch (error) {
    lastMsg.value = `API not available: ${describeError(error)}`;
  }
  try {
    accounts.value = await fetchAccounts();
    const authorizedAccount = accounts.value.find((account) => account.can_trade) || accounts.value[0];
    if (authorizedAccount) {
      accountId.value = authorizedAccount.id;
      sessionState.value = "ready";
      sessionDetail.value = `Platform session authorized ${authorizedAccount.name}.`;
    } else {
      sessionState.value = "empty";
      sessionDetail.value = "No account was returned for this platform session.";
      lastMsg.value = sessionDetail.value;
    }
  } catch (error) {
    setSessionFailure(error);
    lastMsg.value = `Account access unavailable: ${sessionDetail.value}`;
  }
  try {
    const state = await fetchState();
    applyBook(state.book);
    if (state.tape) tape.value = state.tape;
    if (state.footprint) applyFootprint(state.footprint, state.cvd);
    if (state.chart) applyChart(state.chart);
    if (state.marketData) applyMarketData(state.marketData);
  } catch (error) {
    lastMsg.value = `Market data unavailable: ${describeError(error)}`;
  }
  try {
    chart.value = await fetchChart(120);
  } catch (error) {
    if (!chart.value) lastMsg.value = `Chart unavailable: ${describeError(error)}`;
  }
  connectMarketStream();
  recordsTimer = window.setInterval(() => {
    if (sessionState.value === "ready" && accountId.value) {
      void refreshOrderSafetyState();
    }
  }, 5000);
});

onUnmounted(() => {
  shuttingDown = true;
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  if (recordsTimer !== null) window.clearInterval(recordsTimer);
  ws?.close();
});
</script>

<template>
  <div class="shell">
    <header class="terminal-header">
      <div class="brand">
        <strong>PXY ORDER FLOW</strong>
        <span>LIGHTER EXECUTION TERMINAL</span>
      </div>
      <div class="meta">
        <span>MD {{ health.mdMode || "-" }}</span>
        <span>ROUTE {{ health.tradeMode || "-" }}</span>
        <span class="execution-state" :class="{ live: executionMode === 'LIVE', testnet: executionMode === 'TESTNET', mock: executionMode === 'MOCK', locked: !canSubmit }">{{ tradeStateText }}</span>
        <span class="session-state" :class="sessionState" :title="sessionDetail">{{ sessionStateText }}</span>
        <span class="market-state" :class="marketStateClass" :title="marketStatusError">{{ marketStatusText }}</span>
      </div>
    </header>

    <nav class="mobile-tabs" aria-label="Order flow workspace">
      <button type="button" :class="{ active: mobileTab === 'chart' }" @click="mobileTab = 'chart'">CHART</button>
      <button type="button" :class="{ active: mobileTab === 'dom' }" @click="mobileTab = 'dom'">DOM</button>
      <button type="button" :class="{ active: mobileTab === 'tape' }" @click="mobileTab = 'tape'">TAPE</button>
      <button type="button" :class="{ active: mobileTab === 'orders' }" @click="mobileTab = 'orders'">ORDERS</button>
    </nav>

    <main class="workstation">
      <section class="chart-panel mobile-view" :class="{ selected: mobileTab === 'chart' }">
        <FlowCanvas :chart="chart" />
      </section>
      <section class="ladder-wrap mobile-view" :class="{ selected: mobileTab === 'dom' }" aria-label="Depth of market">
        <PriceLadder
          :bids="bids"
          :asks="asks"
          :own-orders="ownOrders"
          :locked="!canSubmit"
          :cancel-locked="!canCancel"
          :cancelling-order-ids="cancellingOrderIds"
          @click-level="onClickLevel"
          @cancel-order="onCancelOrder"
        />
      </section>
      <aside class="tape-panel mobile-view" :class="{ selected: mobileTab === 'tape' }">
        <div class="tape-head">
          <h3>TIME &amp; SALES</h3>
          <span>{{ tape.length }}</span>
        </div>
        <div class="tape-labels">
          <span>TIME</span><span>PRICE</span><span>SIZE</span>
        </div>
        <div class="tape">
          <div v-for="(trade, index) in tape" :key="trade.id || `${trade.ts}-${index}`" class="t" :class="trade.side">
            <span>{{ new Date(trade.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }}</span>
            <span>{{ Number(trade.price).toFixed(2) }}</span>
            <span>{{ Number(trade.qty).toFixed(4) }}</span>
          </div>
          <div v-if="!tape.length" class="tape-empty">Waiting for trades</div>
        </div>
      </aside>
    </main>

    <OrdersPanel
      class="records-panel mobile-view"
      :class="{ selected: mobileTab === 'orders' }"
      :orders="ownOrders"
      :positions="positions"
      :fills="fills"
      :cancel-locked="!canCancel"
      :cancelling-order-ids="cancellingOrderIds"
      @cancel-order="onCancelOrder"
    />

    <OrderTicket
      v-model:account-id="accountId"
      v-model:qty="qty"
      v-model:post-only="postOnly"
      :account="activeAccount"
      :execution-mode="executionMode"
      :session-text="sessionStateText"
      :session-detail="sessionDetail"
      :trade-armed="tradeArmed"
      :can-arm="sessionState === 'ready' && Boolean(activeAccount?.can_trade) && writesEnabled"
      :trade-lock-reason="tradeLockReason"
      :submission-id="submissionId"
      :last-msg="lastMsg"
      :submitting="submitting"
      :cancel-all-pending="cancelAllPending"
      :cancel-enabled="canCancel"
      :cancel-lock-reason="cancelLockReason"
      @update:trade-armed="setTradeArmed"
      @cancel-all="onCancelAll"
    />
  </div>
</template>

<style scoped>
.shell { height: 100%; display: grid; grid-template-rows: auto minmax(0, 1fr) minmax(110px, 150px) auto; gap: 8px; padding: 8px; }
.terminal-header { display: flex; justify-content: space-between; align-items: center; min-height: 40px; border: 1px solid var(--border); background: var(--panel); padding: 0 10px; }
.brand { display: flex; gap: 11px; align-items: baseline; min-width: 0; }
.brand strong { color: var(--brand); letter-spacing: 0; font-size: 14px; }
.brand span, .meta { color: var(--muted); font-size: 11px; }
.meta { display: flex; gap: 12px; font-variant-numeric: tabular-nums; }
.meta .on { color: var(--bid); }
.meta .off { color: var(--ask); }
.execution-state, .session-state { padding: 3px 5px; border: 1px solid var(--border); font-size: 10px; }
.execution-state.live { color: #ffab91; border-color: #8b3d35; background: #2b1618; }
.execution-state.testnet { color: #ffd166; border-color: #7a6427; background: #28230f; }
.execution-state.mock { color: var(--brand); border-color: #23635c; background: #102a2b; }
.execution-state.locked { color: var(--mid); }
.session-state.ready { color: var(--bid); }
.session-state.auth, .session-state.gateway, .session-state.unavailable { color: var(--ask); }
.session-state.empty { color: var(--mid); }
.market-state.healthy { color: var(--bid); }
.market-state.recovering { color: var(--mid); }
.market-state.failed { color: var(--ask); }
.mobile-tabs { display: none; }
.workstation { min-height: 0; display: grid; grid-template-columns: minmax(380px, 1fr) minmax(245px, 300px) minmax(168px, 205px); gap: 8px; }
.chart-panel, .ladder-wrap, .tape-panel { min-height: 0; }
.tape-panel { background: var(--panel-deep); border: 1px solid var(--border); display: flex; flex-direction: column; }
.tape-head { height: 31px; min-height: 31px; padding: 0 8px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border); }
.tape-head h3 { margin: 0; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.tape-head span { color: var(--muted); font-size: 11px; }
.tape-labels { display: grid; grid-template-columns: 1.1fr 1fr 0.8fr; gap: 4px; padding: 5px 8px; color: var(--muted); font-size: 10px; border-bottom: 1px solid var(--border); }
.tape { overflow: auto; flex: 1; font-variant-numeric: tabular-nums; font-size: 11px; }
.t { display: grid; grid-template-columns: 1.1fr 1fr 0.8fr; gap: 4px; padding: 3px 8px; border-bottom: 1px solid rgba(31, 40, 50, 0.5); }
.t.buy { color: var(--bid); }
.t.sell { color: var(--ask); }
.tape-empty { color: var(--muted); text-align: center; padding: 18px 8px; }
@media (max-width: 920px) {
  .shell { height: auto; min-height: 100dvh; min-width: 0; overflow: visible; grid-template-rows: auto auto auto auto auto; }
  .terminal-header { flex-wrap: wrap; align-items: flex-start; gap: 5px 12px; }
  .brand, .meta { flex-wrap: wrap; min-width: 0; }
  .meta { flex: 1 1 100%; width: 100%; justify-content: flex-start; gap: 5px 8px; }
  .meta span { max-width: 100%; white-space: nowrap; }
  .meta .market-state { flex: 0 0 100%; }
  .mobile-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); min-height: 38px; border: 1px solid var(--border); background: var(--panel-deep); }
  .mobile-tabs button { min-width: 0; border: 0; border-right: 1px solid var(--border); border-radius: 0; background: transparent; color: var(--muted); font-size: 10px; }
  .mobile-tabs button:last-child { border-right: 0; }
  .mobile-tabs button.active { color: var(--text); background: #18212b; box-shadow: inset 0 -2px var(--brand); }
  .workstation { min-height: 0; display: block; }
  .mobile-view:not(.selected) { display: none !important; }
  .chart-panel.selected, .ladder-wrap.selected, .tape-panel.selected { display: block; height: min(62vh, 540px); min-height: 420px; }
  .tape-panel.selected { display: flex; }
  .records-panel.selected { display: grid; min-height: 460px; }
}
@media (max-width: 440px) {
  .shell { padding: 4px; gap: 4px; }
  .terminal-header { padding-bottom: 4px; }
  .brand { gap: 7px; }
  .brand span { font-size: 10px; }
  .meta { width: 100%; font-size: 10px; }
  .workstation { gap: 4px; }
  .chart-panel.selected, .ladder-wrap.selected, .tape-panel.selected { height: 500px; min-height: 500px; }
}
</style>
