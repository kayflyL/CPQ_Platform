<script setup lang="ts">
/** 系统内置推导规则透明化面板（功耗/电源/线缆/背板/GPU线/Switch）。
 *  从 DerivationEngine.describe() 拿人话逻辑 + 可调参数，展示并支持就地编辑（改完 PUT 立即生效）。
 *  底层算法不动，只暴露/可调参数——把黑盒变玻璃盒。嵌入 CompatibilityRuleEditor。 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { deriveApi, type DerivationRule } from '@/api/serverConfig'

const derivations = ref<DerivationRule[]>([])
const loading = ref(false)
// 输入态：number 存数字；list 存「逗号分隔」串；map 存 JSON 串
const drafts = ref<Record<string, any>>({})

async function load() {
  loading.value = true
  try {
    const r = await deriveApi.rules()
    derivations.value = r.derivations || []
    for (const d of derivations.value) {
      for (const p of d.params) {
        const k = `${p.rule_key}.${p.field}`
        if (p.type === 'number') drafts.value[k] = p.value
        else if (p.type === 'list') drafts.value[k] = Array.isArray(p.value) ? p.value.join(', ') : String(p.value ?? '')
        else drafts.value[k] = JSON.stringify(p.value ?? {})
      }
    }
  } catch {
    message.error('加载推导规则失败')
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function saveParam(p: DerivationRule['params'][number]) {
  const k = `${p.rule_key}.${p.field}`
  const raw = drafts.value[k]
  let val: any = raw
  if (p.type === 'number') {
    val = Number(raw)
    if (!Number.isFinite(val)) { message.error(`「${p.label}」需填数字`); return }
  } else if (p.type === 'list') {
    val = String(raw ?? '').split(/[，,\s]+/).map((s: string) => s.trim()).filter(Boolean)
  } else if (p.type === 'map') {
    try { val = String(raw ?? '').trim() ? JSON.parse(raw) : {} }
    catch { message.error(`「${p.label}」需填合法 JSON，如 {"H100": 4}`); return }
  }
  try {
    await deriveApi.updateRuleParam(p.rule_key, p.field, val)
    message.success(`已更新「${p.label}」`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || '更新失败')
  }
}
</script>

<template>
  <a-spin :spinning="loading">
    <div v-if="derivations.length" class="drp-list">
      <div v-for="d in derivations" :key="d.key" class="drp-card glass-light">
        <div class="drp-head">
          <span class="drp-name">{{ d.name }}</span>
          <span class="drp-key">{{ d.key }}</span>
        </div>
        <p class="drp-logic">{{ d.logic }}</p>
        <div class="drp-params">
          <div v-for="p in d.params" :key="p.field" class="drp-param">
            <label class="drp-plabel">{{ p.label }}</label>
            <a-input-number
              v-if="p.type === 'number'"
              v-model:value="drafts[`${p.rule_key}.${p.field}`]"
              style="width: 150px"
              @blur="saveParam(p)"
            />
            <a-input
              v-else-if="p.type === 'list'"
              v-model:value="drafts[`${p.rule_key}.${p.field}`]"
              placeholder="逗号分隔，如 SATA, SAS"
              style="flex: 1; min-width: 180px"
              @blur="saveParam(p)"
            />
            <a-textarea
              v-else
              v-model:value="drafts[`${p.rule_key}.${p.field}`]"
              :rows="2"
              :placeholder='`JSON，如 {&quot;H100&quot;: 4}`'
              style="flex: 1; min-width: 180px"
              @blur="saveParam(p)"
            />
          </div>
        </div>
      </div>
    </div>
    <a-empty v-else description="暂无内置推导规则" />
  </a-spin>
</template>

<style scoped>
.drp-list { display: flex; flex-direction: column; gap: 10px; }
.drp-card { padding: 12px 14px; border-radius: 12px; }
.drp-head { display: flex; align-items: baseline; gap: 8px; }
.drp-name { font-weight: 600; color: var(--cpq-text-primary); }
.drp-key { font-size: 11px; color: var(--cpq-text-muted); font-family: monospace; }
.drp-logic { margin: 4px 0 8px; font-size: 12px; color: var(--cpq-text-secondary); line-height: 1.5; }
.drp-params { display: flex; flex-direction: column; gap: 6px; }
.drp-param { display: flex; align-items: center; gap: 8px; }
.drp-plabel { width: 150px; flex: none; font-size: 12px; color: var(--cpq-text-secondary); }
</style>
