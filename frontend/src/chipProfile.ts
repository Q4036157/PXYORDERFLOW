import type { ChartBar } from "./types";

export interface ChipProfileLevel {
  price: number;
  volume: number;
  widthPct: number;
  isBelowReference: boolean;
  isPoc: boolean;
}

export interface ChipProfile {
  referencePrice: number;
  levels: ChipProfileLevel[];
  totalVolume: number;
  belowReferencePct: number | null;
  averagePrice: number | null;
  pocPrice: number | null;
}

export function buildChipProfile(
  bars: readonly ChartBar[],
  endIndex: number,
): ChipProfile {
  if (endIndex < 0 || endIndex >= bars.length) {
    return {
      referencePrice: 0,
      levels: [],
      totalVolume: 0,
      belowReferencePct: null,
      averagePrice: null,
      pocPrice: null,
    };
  }

  const referencePrice = Number(bars[endIndex].close);
  const buckets = new Map<number, number>();
  for (let index = 0; index <= endIndex; index += 1) {
    for (const bin of bars[index].footprint?.bins || []) {
      const price = Number(bin.price);
      const volume = Number(bin.buyVol || 0)
        + Number(bin.sellVol || 0)
        + Number(bin.unknownVol || 0);
      if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(volume) || volume <= 0) {
        continue;
      }
      buckets.set(price, (buckets.get(price) || 0) + volume);
    }
  }

  if (!buckets.size) {
    return {
      referencePrice,
      levels: [],
      totalVolume: 0,
      belowReferencePct: null,
      averagePrice: null,
      pocPrice: null,
    };
  }

  let totalVolume = 0;
  let belowReferenceVolume = 0;
  let weightedPrice = 0;
  let maxVolume = 0;
  let pocPrice = 0;
  for (const [price, volume] of buckets) {
    totalVolume += volume;
    weightedPrice += price * volume;
    if (Number.isFinite(referencePrice) && price < referencePrice) {
      belowReferenceVolume += volume;
    }
    if (volume > maxVolume) {
      maxVolume = volume;
      pocPrice = price;
    }
  }

  const levels = [...buckets.entries()]
    .map(([price, volume]) => ({
      price,
      volume,
      widthPct: maxVolume > 0 ? (volume / maxVolume) * 100 : 0,
      isBelowReference: Number.isFinite(referencePrice) && price < referencePrice,
      isPoc: price === pocPrice,
    }))
    .sort((left, right) => left.price - right.price);

  return {
    referencePrice,
    levels,
    totalVolume,
    belowReferencePct: totalVolume > 0 ? (belowReferenceVolume / totalVolume) * 100 : null,
    averagePrice: totalVolume > 0 ? weightedPrice / totalVolume : null,
    pocPrice: maxVolume > 0 ? pocPrice : null,
  };
}
