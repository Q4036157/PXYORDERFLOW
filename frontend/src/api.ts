import type {
  Account,
  BookSnapshot,
  ChartPayload,
  FootprintBar,
  MarketDataStatus,
  OrderEvent,
  OwnOrder,
  FillRow,
  PositionRow,
  TradeTick,
} from "./types";

const API_BASE = (import.meta.env.BASE_URL || "/").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function url(path: string): string {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function json<T>(response: Response): Promise<T> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Preserve the HTTP status even if a proxy emits an empty/non-JSON response.
  }
  if (!response.ok) {
    const record = body && typeof body === "object" ? body as Record<string, unknown> : {};
    const detail = typeof record.detail === "string"
      ? record.detail
      : typeof record.message === "string"
        ? record.message
        : response.statusText || "Request failed";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  return json<Record<string, unknown>>(await fetch(url("/health")));
}

export async function fetchAccounts(): Promise<Account[]> {
  const body = await json<{ accounts?: Account[] }>(await fetch(url("/api/accounts")));
  return body.accounts || [];
}

export async function fetchState(): Promise<{
  book?: BookSnapshot;
  tradingEnabled?: boolean;
  cancelEnabled?: boolean;
  mdMode?: string;
  tradeMode?: string;
  tape?: TradeTick[];
  footprint?: FootprintBar | null;
  chart?: ChartPayload | null;
  cvd?: number;
  marketData?: MarketDataStatus;
}> {
  return json(await fetch(url("/api/state")));
}

export async function fetchChart(limit = 120): Promise<ChartPayload> {
  const safeLimit = Math.min(120, Math.max(1, Math.trunc(limit)));
  return json(await fetch(url(`/api/chart?limit=${safeLimit}`)));
}

export async function fetchOpenOrders(accountId: string, symbol?: string): Promise<OwnOrder[]> {
  const query = new URLSearchParams({ accountId });
  if (symbol) query.set("symbol", symbol);
  const body = await json<{ orders?: Record<string, unknown>[] }>(
    await fetch(url(`/api/orders/open?${query.toString()}`)),
  );
  return (body.orders || []).map((order) => {
    const cancelId = String(order.cancelId || order.orderId || order.order_id || "");
    return {
      orderId: String(order.orderId || order.order_id || ""),
      cancelId,
      ofClientId: typeof (order.clientOrderId || order.ofClientId) === "string"
        ? String(order.clientOrderId || order.ofClientId)
        : undefined,
      side: order.side === "sell" ? "sell" : "buy",
      price: Number(order.price),
      qty: Number(order.qty),
      filledQty: Number(order.filledQty || order.filled_qty || 0),
      status: typeof order.status === "string" ? order.status : "open",
      cancellable: Boolean(cancelId) && order.cancellable !== false,
      cancelReason: typeof order.cancelReason === "string" ? order.cancelReason : undefined,
    };
  });
}

export async function fetchPortfolio(
  accountId: string,
  symbol?: string,
): Promise<{ positions: PositionRow[]; fills: FillRow[] }> {
  const query = new URLSearchParams({ accountId });
  if (symbol) query.set("symbol", symbol);
  const body = await json<{ positions?: PositionRow[]; fills?: FillRow[] }>(
    await fetch(url(`/api/portfolio?${query.toString()}`)),
  );
  return {
    positions: Array.isArray(body.positions) ? body.positions : [],
    fills: Array.isArray(body.fills) ? body.fills : [],
  };
}

export async function placeOrder(payload: {
  accountId: string;
  side: "buy" | "sell";
  price: number;
  qty: number;
  postOnly?: boolean;
  idempotencyKey?: string;
}): Promise<OrderEvent> {
  const { idempotencyKey, ...body } = payload;
  return json(await fetch(url("/api/orders/place"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
  }));
}

export async function cancelOrder(payload: { accountId: string; orderId: string; symbol?: string }): Promise<OrderEvent> {
  return json(await fetch(url("/api/orders/cancel"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function cancelAll(payload: { accountId: string; symbol?: string; confirmed: boolean }): Promise<OrderEvent> {
  return json(await fetch(url("/api/orders/cancel-all"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export function connectWs(onMessage: (msg: unknown) => void): WebSocket {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const path = url("/ws");
  const socket = new WebSocket(`${proto}://${location.host}${path}`);
  socket.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // Ignore malformed market-data messages.
    }
  };
  return socket;
}
