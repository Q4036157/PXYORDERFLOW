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

export interface OwnOrder {
  orderId: string;
  ofClientId?: string;
  side: Side;
  price: number;
  qty: number;
  status: string;
}
