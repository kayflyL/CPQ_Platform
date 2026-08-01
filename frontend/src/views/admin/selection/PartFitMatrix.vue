<script setup lang="ts">
/**
 * 配件适配矩阵 —— 选型配置「🔗 配件适配」标签。
 *
 * L1 声明式适配的可视探查：选一台机箱(看其能力档案 rear_slots/psu_bays/gpu_slots)，
 * 再选一个料号库分类，列出该分类配件及其「适用系列」(读 specs.chassis)——是否适用当前机箱由
 * utils/partFit.fitsSeries 判定（specs.chassis 未声明视为通用=适用）。数据不全的件标「未声明(通用)」，
 * 不臆断——与 [[derive-must-have-manual-fallback]] 一致。
 *
 * 配件↔机箱的适配关系本就由料号库 specs 声明 + partFit 读取，本页只是把这套关系照见出来、可查可校。
 */
import { ref, computed, onMounted } from 'vue'
import { baseConfigApi, partsApi, type BaseConfig, type PartMaster } from '@/api/serverConfig'
import { slotCapOf, applicableSeries, fitsSeries } from '@/utils/partFit'

const configs = ref<BaseConfig[]>([])
const selectedConfigId = ref<number | null>(null)
// 料号库分类——数据驱动（partsApi.categories() 取 parts_master 真实 category DISTINCT），拒绝写死分类名
const categories = ref<string[]>([])
const selectedCategory = ref<string>('')
const parts = ref<PartMaster[]>([])
const loadingParts = ref(false)

const current = computed(() => configs.value.find(c => c.id === selectedConfigId.value) || null)

async function loadConfigs() {
  const res = await baseConfigApi.list()
  configs.value = res.configs || []
  if (configs.value.length && selectedConfigId.value == null) selectedConfigId.value = configs.value[0].id
}
async function loadCategories() {
  try {
    const res = await partsApi.categories()
    categories.value = res.categories || []
    // 默认挑一个后面板相关分类（存在则用，贴合本页主题），否则首个——列表本身全数据驱动
    if (!selectedCategory.value) {
      selectedCategory.value = categories.value.find(c => c.includes('Riser')) || categories.value[0] || ''
    }
  } catch { categories.value = [] }
}
async function loadParts() {
  if (!selectedCategory.value) return
  loadingParts.value = true
  try {
    const res = await partsApi.list({ category: selectedCategory.value })
    parts.value = res.parts || []
  } catch { parts.value = [] } finally { loadingParts.value = false }
}
onMounted(async () => { await loadConfigs(); await loadCategories(); await loadParts() })

function fitLabel(p: PartMaster): { text: string; ok: boolean } {
  const series = current.value?.series
  const list = applicableSeries(p)
  if (!series) return { text: '未选机箱', ok: false }
  if (list.length === 0) return { text: '未声明 · 按通用', ok: true }
  return fitsSeries(p, series)
    ? { text: `适用 (${series})`, ok: true }
    : { text: `不适用 (仅 ${list.join('/')})`, ok: false }
}
</script>

<template>
  <div class="pfm">
    <div class="pfm-bar">
      <span class="pfm-hint">L1 声明式适配：机箱能力档案 × 配件 specs。选机箱看其物理容量，选分类查配件适用系列——关系由料号库 specs 声明，partFit 读取。</span>
    </div>

    <div class="pfm-cols">
      <!-- 左：机箱能力档案 -->
      <div class="pfm-left glass-light">
        <div class="pfm-sec-head">机箱能力档案</div>
        <a-select v-model:value="selectedConfigId" style="width:100%; margin-bottom: 12px"
          :options="configs.map(c => ({ value: c.id, label: `${c.series || ''} ${c.form || ''} · ${c.name}` }))" />
        <template v-if="current">
          <div class="pfm-cap">
            <div class="pfm-cap-row"><span>电源槽</span><b>{{ current.psu_bays ?? 2 }}</b></div>
            <div class="pfm-cap-row"><span>GPU 上限</span><b>{{ current.gpu_slots ?? 0 }}</b></div>
            <div class="pfm-cap-row"><span>TDP 上限</span><b>{{ current.max_tdp ?? '—' }}<small v-if="current.max_tdp">W</small></b></div>
          </div>
          <div class="pfm-sec-sub">后面板槽位容量（partFit.slotCapOf）</div>
          <div class="pfm-slots">
            <div v-for="s in (current.rear_slots || [])" :key="s.name" class="pfm-slot">
              <span class="pfm-slot-n">{{ s.name }}</span>
              <span class="pfm-slot-c">×{{ slotCapOf(current.rear_slots, s.name) }}</span>
            </div>
            <div v-if="!current.rear_slots?.length" class="pfm-muted">未配置后面板槽位</div>
          </div>
        </template>
      </div>

      <!-- 右：配件适用系列 -->
      <div class="pfm-right glass-light">
        <div class="pfm-sec-head">
          配件适用系列
          <a-select v-model:value="selectedCategory" size="small" style="width: 170px"
            :options="categories.map(c => ({ value: c, label: c }))" placeholder="选分类" @change="loadParts" />
        </div>
        <a-spin :spinning="loadingParts">
          <div v-if="parts.length" class="pfm-parts">
            <div v-for="p in parts" :key="p.pn" class="pfm-part" :class="{ ok: fitLabel(p).ok, no: !fitLabel(p).ok }">
              <div class="pfm-part-top">
                <span class="pfm-part-name">{{ p.name || p.pn }}</span>
                <span class="pfm-fit" :class="fitLabel(p).ok ? 'ok' : 'no'">{{ fitLabel(p).text }}</span>
              </div>
              <div class="pfm-part-pn">{{ p.pn }}<span v-if="applicableSeries(p).length"> · 声明系列: {{ applicableSeries(p).join('/') }}</span></div>
            </div>
          </div>
          <div v-else class="pfm-muted">该分类暂无配件</div>
        </a-spin>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pfm { padding: 4px 0; }
.pfm-bar { margin-bottom: 14px; }
.pfm-hint { font-size: 12.5px; color: var(--cpq-text-muted); }
.pfm-cols { display: grid; grid-template-columns: 320px 1fr; gap: 14px; }
.pfm-left, .pfm-right { border: 1px solid var(--cpq-glass-border); border-radius: 12px; padding: 14px 16px; }
.pfm-sec-head { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; }
.pfm-sec-sub { font-size: 11.5px; color: var(--cpq-text-muted); margin: 12px 0 6px; }
.pfm-cap { display: flex; gap: 18px; }
.pfm-cap-row { display: flex; flex-direction: column; gap: 2px; }
.pfm-cap-row span { font-size: 11px; color: var(--cpq-text-disabled); }
.pfm-cap-row b { font-size: 15px; color: var(--cpq-text-primary); }
.pfm-cap-row small { font-size: 10px; color: var(--cpq-text-muted); font-weight: 400; }
.pfm-slots { display: flex; flex-wrap: wrap; gap: 6px; }
.pfm-slot { border: 1px solid var(--cpq-border-secondary); border-radius: 8px; padding: 4px 10px; display: flex; flex-direction: column; align-items: center; min-width: 56px; }
.pfm-slot-n { font-size: 12px; color: var(--cpq-text-primary); font-weight: 500; }
.pfm-slot-c { font-size: 13px; color: var(--cpq-accent-primary); font-weight: 600; }
.pfm-parts { display: flex; flex-direction: column; gap: 8px; max-height: 460px; overflow-y: auto; }
.pfm-part { border: 1px solid var(--cpq-border-secondary); border-left-width: 3px; border-radius: 8px; padding: 8px 12px; }
.pfm-part.ok { border-left-color: var(--cpq-color-success, #52c41a); }
.pfm-part.no { border-left-color: var(--cpq-accent-danger, #ff4d4f); }
.pfm-part-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pfm-part-name { font-size: 13px; color: var(--cpq-text-primary); font-weight: 500; }
.pfm-fit { font-size: 11px; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.pfm-fit.ok { color: var(--cpq-color-success, #52c41a); background: color-mix(in srgb, var(--cpq-color-success, #52c41a) 12%, transparent); }
.pfm-fit.no { color: var(--cpq-accent-danger, #ff4d4f); background: color-mix(in srgb, var(--cpq-accent-danger, #ff4d4f) 12%, transparent); }
.pfm-part-pn { font-size: 11px; color: var(--cpq-text-muted); margin-top: 2px; }
.pfm-muted { color: var(--cpq-text-muted); font-size: 12.5px; padding: 20px 0; text-align: center; }
</style>
