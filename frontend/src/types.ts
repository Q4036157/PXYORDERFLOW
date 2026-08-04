export type Side = "buy" | "sell";

export interface BookLevel {
  price: number;
  qty: number;
}

export interface BookSnapshot {
  symbol: string;
  bids: BookLevel[];
  asks: BookLevel[];
  ts: number;
  nonce?: number | null;
}

export interface Account {
  id: string;
  name: string;
  mode: "live" | "demo";
  can_trade: boolean;
}

export interface OrderEvent {
  success: boolean;
  orderId?: string;
  ofClientId?: string;
  message?: string;
  side?: Side;
  price?: number;
  qty?: number;
  source?: string;
}

export interface TradeTick {
  symbol: string;
  price: number;
  qty: number;
  side: Side;
  ts: number;
  id?: string;
}

export interface FootprintBin {
  price: number;
  buyVol: number;
  sellVol: number;
  unknownVol?: number;
  tradeCount: number;
  delta: number;
}

export interface FootprintBar {
  symbol: string;
  intervalMs: number;
  startTs: number;
  bins: FootprintBin[];
  totalDelta: number;
  cvd?: number;
}

export interface ChartBar {
  startTs: number;
  endTs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  buyVol: number;
  sellVol: number;
  delta: number;
  cvd: number;
  tradeCount: number;
  footprint: {
    bins: FootprintBin[];
  };
}

export interface ChartPayload {
  symbol: string;
  intervalMs: number;
  bars: ChartBar[];
  cvd: number;
}

export interface MarketDataStatus {
  transport?: string | null;
  book?: {
    state?: string;
    lastNonce?: number | null;
    error?: string | null;
  };
  upstreamBook?: {
    state?: string;
    error?: string | null;
    resyncCount?: number;
  };
}

export interface OwnOrder {
  orderId: string;
  cancelId: string;
  ofClientId?: string;
  side: Side;
  price: number;
  qty: number;
  filledQty?: number;
  status: string;
  cancellable?: boolean;
  cancelReason?: string;
}

export interface PositionRow {
  symbol: string;
  side: Side;
  qty: number;
  entryPrice: number;
  markPrice: number;
  unrealizedPnl: number;
}

export interface FillRow {
  id: string;
  orderId: string;
  side: Side;
  price: number;
  qty: number;
  fee?: number;
  ts: number;
}
