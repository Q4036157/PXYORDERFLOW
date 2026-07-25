<script setup lang="ts">
const props = defineProps<{
  accountId: string;
  qty: number;
  postOnly: boolean;
  accounts: { id: string; name: string; mode: string }[];
  lastMsg: string;
}>();

const emit = defineEmits<{
  "update:accountId": [string];
  "update:qty": [number];
  "update:postOnly": [boolean];
  cancelAll: [];
}>();

function onQty(e: Event) {
  const v = Number((e.target as HTMLInputElement).value);
  emit("update:qty", Number.isFinite(v) ? v : 0);
}
</script>

<template>
  <div class="ticket">
    <label>
      账户
      <select
        :value="accountId"
        @change="emit('update:accountId', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="a in accounts" :key="a.id" :value="a.id">
          {{ a.name }} ({{ a.mode }})
        </option>
      </select>
    </label>
    <label>
      数量
      <input type="number" min="0" step="0.001" :value="qty" @input="onQty" />
    </label>
    <label class="check">
      <input
        type="checkbox"
        :checked="postOnly"
        @change="emit('update:postOnly', ($event.target as HTMLInputElement).checked)"
      />
      Post Only
    </label>
    <button class="danger" type="button" @click="emit('cancelAll')">全部撤单</button>
    <div class="msg">{{ lastMsg || "点击买量列买入 / 卖量列卖出" }}</div>
  </div>
</template>

<style scoped>
.ticket {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: end;
  padding: 10px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
label.check {
  flex-direction: row;
  align-items: center;
  gap: 6px;
  padding-bottom: 6px;
}
.msg {
  flex: 1;
  min-width: 200px;
  font-size: 12px;
  color: var(--muted);
  padding-bottom: 6px;
}
</style>
