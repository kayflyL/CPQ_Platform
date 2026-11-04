<template>
  <div class="conversion-table-wrap">
    <button v-if="expanded" class="conv-expand-toggle" @click="expanded = false">收起 ▲</button>
    <div v-if="rows.length" class="conv-list">
      <div class="conv-row conv-head">
        <span class="conv-rank"></span>
        <span class="conv-name">业务</span>
        <span class="conv-num">线索</span>
        <span class="conv-num">成交</span>
        <span class="conv-rate-head">成交率</span>
      </div>
      <div v-for="(r, i) in rows" :key="r.name + i" class="conv-row" :class="{ 'conv-others': r.others, 'conv-clickable': r.expandable }" @click="onRowClick(r)">
        <span class="conv-rank">{{ r.others ? '·' : i + 1 }}</span>
        <span class="conv-name">{{ r.name }}<span v-if="r.expandable" class="conv-expand-hint"> ▸</span></span>
        <span class="conv-num">{{ r.count }}</span>
        <span class="conv-num conv-won">{{ r.won }}</span>
        <span class="conv-rate" :style="{ color: rateColor(r.rate) }">{{ r.rate }}%</span>
      </div>
    </div>
    <div v-else class="chart-empty">暂无转化数据</div>
  </div>
</template>

<script setup lang="ts">
// 线索转化表（业务/线索/成交/成交率）：商机线索页与驾驶舱共用。
import { computed, ref } from 'vue'

interface RankItem { name: string; count: number; won?: number }

const props = defineProps<{
  top: RankItem[]
  others?: { count: number; people: number } | null
  othersList?: RankItem[]
}>()

const expanded = ref(false)

const rows = computed(() => {
  const rows: (RankItem & { others?: boolean; expandable?: boolean; rate: number })[] =
    props.top.map(s => ({ ...s, won: s.won || 0, others: false, expandable: false, rate: 0 }))
  if (expanded.value) {
    (props.othersList || []).forEach(s => rows.push({ ...s, won: s.won || 0, others: false, expandable: false, rate: 0 }))
  } else if (props.others && props.others.count > 0) {
    const othersWon = (props.othersList || []).reduce((a, s) => a + (s.won || 0), 0)
    rows.push({ name: `其他 ${props.others.people} 人`, count: props.others.count, won: othersWon, others: true, expandable: true, rate: 0 })
  }
  return rows.map(r => ({ ...r, rate: r.count > 0 ? Math.round(((r.won || 0) / r.count) * 100) : 0 }))
})

function onRowClick(r: any) {
  if (r.expandable) expanded.value = true
}

function rateColor(rate: number) {
  if (rate >= 50) return '#52C9A0'
  if (rate >= 30) return '#1677FF'
  return '#86909c'
}
</script>

<style scoped>
.conversion-table-wrap { flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; }
.conv-expand-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; margin-bottom: 4px; align-self: flex-end; border: 1px solid var(--cpq-overlay-a20); border-radius: var(--cpq-radius-full); background: var(--cpq-overlay-a8); color: var(--cpq-accent-primary); font-size: var(--cpq-font-size-xs); cursor: pointer; transition: all var(--cpq-dur-1) var(--cpq-ease-smooth); }
.conv-expand-toggle:hover { background: var(--cpq-overlay-a15); border-color: var(--cpq-accent-primary); }
.conv-list { flex: 1 1 0; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; }
.conv-list::-webkit-scrollbar { width: 6px; }
.conv-list::-webkit-scrollbar-thumb { background: var(--cpq-overlay-a20); border-radius: var(--cpq-radius-xs); }
.conv-list::-webkit-scrollbar-track { background: transparent; }
.conv-row { display: grid; grid-template-columns: 20px 1fr 34px 34px 46px; align-items: center; gap: 8px; padding: 6px 2px; flex: 1 1 0; min-height: 16px; border-bottom: 1px solid var(--cpq-overlay-w4); }
.conv-row:last-child { border-bottom: none; }
.conv-head { flex: 0 0 auto; min-height: 0; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); font-weight: 500; border-bottom-color: var(--cpq-overlay-w8); }
.conv-clickable { cursor: pointer; transition: background var(--cpq-dur-1) var(--cpq-ease-smooth); }
.conv-clickable:hover { background: var(--cpq-overlay-a8); }
.conv-expand-hint { color: var(--cpq-accent-primary); font-size: 10px; }
.conv-rank { font-size: var(--cpq-font-size-xs); font-weight: 700; color: var(--cpq-accent-primary); text-align: center; font-variant-numeric: tabular-nums; }
.conv-name { font-size: 12.5px; color: var(--cpq-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-num { font-size: 12.5px; color: var(--cpq-text-secondary); text-align: right; font-variant-numeric: tabular-nums; }
.conv-won { color: #52C9A0; font-weight: 600; }
.conv-rate-head { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); text-align: right; }
.conv-rate { font-size: 12.5px; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.conv-others .conv-name, .conv-others .conv-num { color: var(--cpq-text-muted); }
.chart-empty { flex: 1 1 0; display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted); font-size: var(--cpq-font-size-sm); }
</style>
