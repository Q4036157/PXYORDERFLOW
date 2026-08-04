import assert from "node:assert/strict";
import test from "node:test";
import { buildChipProfile } from "../src/chipProfile.ts";
import type { ChartBar, FootprintBin } from "../src/types.ts";

function bar(close: number, bins: FootprintBin[]): ChartBar {
  return {
    startTs: 0,
    endTs: 60_000,
    open: close,
    high: close,
    low: close,
    close,
    volume: 0,
    buyVol: 0,
    sellVol: 0,
    delta: 0,
    cvd: 0,
    tradeCount: 0,
    footprint: { bins },
  };
}

function bin(
  price: number,
  buyVol: number,
  sellVol: number,
  unknownVol = 0,
): FootprintBin {
  return {
    price,
    buyVol,
    sellVol,
    unknownVol,
    tradeCount: 1,
    delta: buyVol - sellVol,
  };
}

test("筹码分布只累计截至悬停 K 线的真实成交量", () => {
  const bars = [
    bar(101, [bin(100, 2, 1)]),
    bar(102, [bin(100, 1, 0), bin(102, 0, 4)]),
    bar(99, [bin(99, 10, 0)]),
  ];

  const first = buildChipProfile(bars, 0);
  const second = buildChipProfile(bars, 1);

  assert.deepEqual(first.levels.map((level) => [level.price, level.volume]), [[100, 3]]);
  assert.deepEqual(second.levels.map((level) => [level.price, level.volume]), [[100, 4], [102, 4]]);
  assert.equal(second.referencePrice, 102);
  assert.equal(second.totalVolume, 8);
  assert.equal(second.belowReferencePct, 50);
  assert.equal(second.pocPrice, 100);
});

test("未知方向成交计入总分布但不伪造买卖方向", () => {
  const profile = buildChipProfile([
    bar(101, [bin(100, 0, 0, 5), bin(101, 1, 1)]),
  ], 0);

  assert.equal(profile.totalVolume, 7);
  assert.equal(profile.levels.find((level) => level.price === 100)?.volume, 5);
  assert.equal(profile.pocPrice, 100);
  assert.equal(profile.averagePrice, (100 * 5 + 101 * 2) / 7);
});

test("无效悬停索引返回空分布", () => {
  const profile = buildChipProfile([bar(100, [bin(100, 1, 0)])], -1);
  assert.equal(profile.levels.length, 0);
  assert.equal(profile.totalVolume, 0);
  assert.equal(profile.referencePrice, 0);
});
