import type {
  Account,
  BookSnapshot,
  FootprintBar,
  OrderEvent,
  OwnOrder,
  TradeTick,
} from "./types";

// Vite base 在生产为 /apps/orderflow/；开发为 /
const API_BASE = (import.meta.env.BASE_URL || "/").replace(/\/$/, "");

function url(path: string): string {
  if (!path.startsWith("/")) path = `/${path}`;
  return `${API_BASE}${path}`;
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  const r = await fetch(url("/health"));
  return r.json();
}

export async function fetchAccounts(): Promise<Account[]> {
  const r = await fetch(url("/api/accounts"));
  const body = await r.json();
  return body.accounts || [];
}

export async function fetchState(): Promise<{
  book?: BookSnapshot;
  tradingEnabled?: boolean;
  mdMode?: string;
  tradeMode?: string;
  tape?: TradeTick[];
  footprint?: FootprintBar | null;
  cvd?: number;
}> {
  const r = await fetch(url("/api/state"));
  return r.json();
}

export async function fetchOpenOrders(
  accountId: string,
  symbol?: string,
): Promise<OwnOrder[]> {
  const q = new URLSearchParams({ accountId });
  if (symbol) q.set("symbol", symbol);
  const r = await fetch(url(`/api/orders/open?${q.toString()}`));
  const body = await r.json();
  const rows = body.orders || [];
  return rows.map((o: any) => ({
    orderId: o.orderId || o.order_id,
    ofClientId: o.clientOrderId || o.ofClientId,
    side: (o.side === "sell" ? "sell" : "buy") as "buy" | "sell",
    price: Number(o.price),
    qty: Number(o.qty),
    status: o.status || "open",
  }));
}

export async function placeOrder(payload: {
  accountId: string;
  side: "buy" | "sell";
  price: number;
  qty: number;
  postOnly?: boolean;
}): Promise<OrderEvent> {
  const r = await fetch(url("/api/orders/place"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function cancelOrder(payload: {
  accountId: string;
  orderId: string;
  symbol?: string;
}): Promise<OrderEvent> {
  const r = await fetch(url("/api/orders/cancel"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export async function cancelAll(payload: {
  accountId: string;
  symbol?: string;
  confirmed: boolean;
}): Promise<OrderEvent> {
  const r = await fetch(url("/api/orders/cancel-all"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

export function connectWs(onMessage: (msg: any) => void): WebSocket {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const path = url("/ws");
  const ws = new WebSocket(`${proto}://${location.host}${path}`);
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data));
    } catch {
      /* ignore */
    }
  };
  return ws;
}
