<script setup lang="ts">
import type { Account } from "../types";

const props = defineProps<{
  accountId: string;
  account?: Account;
  qty: number;
  postOnly: boolean;
  executionMode: "LIVE" | "MOCK" | "READ ONLY";
  sessionText: string;
  sessionDetail: string;
  tradeArmed: boolean;
  canArm: boolean;
  tradeLockReason: string;
  submissionId: string;
  lastMsg: string;
  submitting: boolean;
  cancelAllPending: boolean;
  cancelEnabled: boolean;
  cancelLockReason: string;
}>();

const emit = defineEmits<{
  "update:accountId": [value: string];
  "update:qty": [value: number];
  "update:postOnly": [value: boolean];
  "update:tradeArmed": [value: boolean];
  cancelAll: [];
}>();

function onQty(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  emit("update:qty", Number.isFinite(value) ? value : 0);
}

function setQty(value: number): void {
  emit("update:qty", value);
}
</script>

<template>
  <section class="ticket" aria-label="Order entry controls">
    <div class="account-readout">
      <span>AUTHORIZED ACCOUNT</span>
      <strong>{{ account?.name || "Unavailable" }}</strong>
      <small>{{ account?.id || sessionText }}</small>
    </div>

    <div class="mode-readout" :class="executionMode.toLowerCase()">
      <span>EXECUTION MODE</span>
      <strong>{{ executionMode }}</strong>
      <small>{{ sessionText }}</small>
    </div>

    <label class="arm-switch" :title="tradeLockReason || 'Execution is armed'">
      <span>ORDER ENTRY</span>
      <input
        type="checkbox"
        role="switch"
        :checked="tradeArmed"
        :disabled="!canArm || submitting"
        @change="emit('update:tradeArmed', ($event.target as HTMLInputElement).checked)"
      />
      <b :class="tradeArmed ? 'armed' : 'locked'">{{ tradeArmed ? 'ARMED' : 'LOCKED' }}</b>
    </label>

    <label class="qty-field">
      QTY
      <input type="number" min="0" step="0.001" :value="qty" :disabled="!tradeArmed" @input="onQty" />
    </label>
    <div class="qty-presets" aria-label="Quantity presets">
      <button type="button" :disabled="!tradeArmed" @click="setQty(0.01)">.01</button>
      <button type="button" :disabled="!tradeArmed" @click="setQty(0.05)">.05</button>
      <button type="button" :disabled="!tradeArmed" @click="setQty(0.1)">.10</button>
    </div>
    <label class="check">
      <input
        type="checkbox"
        :checked="postOnly"
        :disabled="!tradeArmed"
        @change="emit('update:postOnly', ($event.target as HTMLInputElement).checked)"
      />
      POST ONLY
    </label>
    <button class="danger" type="button" :title="cancelLockReason" :disabled="!cancelEnabled || cancelAllPending" @click="emit('cancelAll')">
      {{ cancelAllPending ? "CANCELLING" : "CANCEL ALL" }}
    </button>

    <div class="submission-status" :class="{ pending: submitting }">
      <span>{{ lastMsg || tradeLockReason || sessionDetail }}</span>
      <small v-if="submissionId">REQUEST {{ submissionId }}</small>
    </div>
  </section>
</template>

<style scoped>
.ticket { min-height: 67px; display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: end; padding: 8px 10px; background: var(--panel-deep); border: 1px solid var(--border); }
.account-readout, .mode-readout { min-width: 148px; display: grid; gap: 2px; align-self: stretch; padding-right: 10px; border-right: 1px solid var(--border); }
.account-readout span, .mode-readout span, label { color: var(--muted); font-size: 10px; letter-spacing: 0.04em; }
.account-readout strong, .mode-readout strong { font-size: 12px; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.account-readout small, .mode-readout small { color: var(--muted); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mode-readout.live strong { color: #ffab91; }
.mode-readout.mock strong { color: var(--brand); }
.arm-switch { min-width: 115px; display: grid; grid-template-columns: auto auto; gap: 3px 6px; align-items: center; padding-bottom: 1px; }
.arm-switch > span { grid-column: 1 / -1; }
.arm-switch input { margin: 0; accent-color: var(--bid); }
.arm-switch b { font-size: 11px; letter-spacing: 0.05em; }
.arm-switch b.armed { color: var(--bid); }
.arm-switch b.locked { color: var(--mid); }
.qty-field { display: flex; flex-direction: column; gap: 4px; }
.qty-field input { width: 82px; letter-spacing: 0; }
.qty-presets { display: flex; align-items: end; gap: 2px; padding-bottom: 1px; }
.qty-presets button { min-width: 33px; height: 28px; padding: 0 5px; font-size: 11px; }
.check { display: flex; align-items: center; gap: 6px; padding-bottom: 6px; }
.submission-status { flex: 1 1 220px; min-width: 0; display: grid; gap: 2px; align-self: stretch; align-content: center; padding-left: 3px; color: var(--muted); font-size: 11px; }
.submission-status > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.submission-status small { color: #758397; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.submission-status.pending { color: var(--mid); }
button:disabled, input:disabled { cursor: not-allowed; opacity: 0.5; }
@media (max-width: 920px) {
  .ticket { align-items: end; }
  .account-readout, .mode-readout { flex: 1 1 44%; min-width: 0; border-right: 0; padding-right: 0; }
  .submission-status { flex: 0 0 100%; min-width: 0; align-self: auto; }
  .submission-status > span, .submission-status small { white-space: normal; overflow: visible; text-overflow: clip; }
}
@media (max-width: 440px) {
  .ticket { gap: 7px; padding: 7px; }
  .account-readout, .mode-readout { flex-basis: 100%; padding-bottom: 5px; border-bottom: 1px solid var(--border); }
  .account-readout strong, .mode-readout strong { font-size: 13px; }
  .danger { margin-left: auto; }
}
</style>
