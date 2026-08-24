<script setup lang="ts">
import { DeleteOutlined, EditOutlined, PoweroffOutlined } from '@ant-design/icons-vue'
import { RULE_TYPE_MAP, RULE_OP_MAP, humanizeFieldPath } from '@/constants/ruleMeta'
import type { CompatibilityRule } from '@/api/compatibilityRules'

defineProps<{
  rules: CompatibilityRule[]
  loading: boolean
  searchText: string
  catFilter: string
  categoryChips: { name: string; count: number }[]
  uncategorizedCount: number
  groupedFiltered: { key: string; category: string; rules: CompatibilityRule[] }[]
}>()

const emit = defineEmits<{
  (e: 'update:search-text', value: string): void
  (e: 'update:cat-filter', value: string): void
  (e: 'open-edit', rule: CompatibilityRule): void
  (e: 'remove', rule: CompatibilityRule): void
  (e: 'toggle-status', rule: CompatibilityRule): void
}>()

function whenSummary(b: any): string {
  const w = b?.when
  if (!w || (!w.all && !w.any && !w.field)) return '始终生效'
  const conds: any[] = w.field ? [w] : (w.all || w.any || [])
  const joiner = Array.isArray(w.any) ? ' 或 ' : ' 且 '
  const parts = conds.map((c: any) => {
    const field = humanizeFieldPath(c.field)
    const op = RULE_OP_MAP[c.op] || c.op
    let val: any = c.value
    if (typeof val === 'string' && /^(kp|config|opportunity)\./.test(val)) val = humanizeFieldPath(val)
    return `${field} ${op} ${val}`
  })
  return parts.join(joiner) + ' 时'
}

function ruleContent(r: CompatibilityRule): string {
  const desc = (r.body?.desc || r.description || '').trim()
  return desc || whenSummary(r.body)
}
</script>

<template>
  <aside class="cre-hud-left glass-light">
    <div class="cre-hud-head">
      <a-input :value="searchText" placeholder="搜索规则名称/条件" size="small" allow-clear @update:value="(v: string) => emit('update:search-text', v)" />
    </div>

    <div class="cre-cats">
      <button class="cre-cat" :class="{ on: catFilter === '__all__' }" @click="emit('update:cat-filter', '__all__')">全部<em>{{ rules.length }}</em></button>
      <button v-for="c in categoryChips" :key="c.name" class="cre-cat" :class="{ on: catFilter === c.name }" @click="emit('update:cat-filter', c.name)">{{ c.name }}<em>{{ c.count }}</em></button>
      <button v-if="uncategorizedCount" class="cre-cat" :class="{ on: catFilter === '__none__' }" @click="emit('update:cat-filter', '__none__')">未分类<em>{{ uncategorizedCount }}</em></button>
    </div>

    <div class="cre-hud-cards">
      <a-spin :spinning="loading">
        <div v-if="groupedFiltered.length">
          <div v-for="grp in groupedFiltered" :key="grp.key" class="cre-group">
            <div class="cre-group-head">
              <span class="cre-group-bar"></span>
              <span class="cre-group-name">{{ grp.category || '未分类' }}</span>
              <span class="cre-group-count">{{ grp.rules.length }}</span>
            </div>
            <div class="cre-list">
              <div
                v-for="r in grp.rules"
                :key="r.id"
                class="cre-card glass-light"
                :class="{ archived: r.status !== 'active' }"
                @click="emit('open-edit', r)"
              >
                <div class="cre-card-head">
                  <span class="cre-dot" :class="r.status === 'active' ? 'on' : 'off'" :title="r.status === 'active' ? '生效中' : '已停用'"></span>
                  <span class="cre-name" :title="r.name">{{ r.name }}</span>
                </div>
                <div class="cre-meta">
                  <span class="cre-type-label">{{ RULE_TYPE_MAP[r.type]?.label }}</span>
                  <span v-if="r.hit_count" class="cre-hit" title="WHEN 条件命中累计次数（工作台选配 + 需求分析自动出方案都会记）">命中 {{ r.hit_count }} 次</span>
                </div>
                <p class="cre-trigger" :title="ruleContent(r)">{{ ruleContent(r) }}</p>
                <div class="cre-card-foot" @click.stop>
                  <a-tooltip :title="r.status === 'active' ? '停用' : '启用'"><a-button size="small" type="text" @click="emit('toggle-status', r)"><PoweroffOutlined /></a-button></a-tooltip>
                  <a-tooltip title="编辑"><a-button size="small" type="text" @click="emit('open-edit', r)"><EditOutlined /></a-button></a-tooltip>
                  <a-tooltip title="删除"><a-button size="small" type="text" danger @click="emit('remove', r)"><DeleteOutlined /></a-button></a-tooltip>
                </div>
              </div>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无此类规则，点「新建规则」添加" />
      </a-spin>
    </div>
  </aside>
</template>

<style scoped>
.cre-hud-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cre-hud-head .ant-input-affix-wrapper { flex: 1; min-width: 120px; }
.cre-hud-cards { flex: 1; min-height: 0; overflow-y: auto; padding-right: 4px; }
.cre-hud-cards .cre-group { margin-bottom: 12px; }
.cre-cats { display: flex; flex-wrap: wrap; gap: 8px; }
.cre-cat { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px; cursor: pointer; border: 1px solid var(--cpq-glass-border); background: var(--cpq-glass-2-bg); color: var(--cpq-text-secondary); font-size: 12.5px; transition: border-color var(--cpq-dur-1) var(--cpq-ease-smooth), background var(--cpq-dur-1) var(--cpq-ease-smooth), color var(--cpq-dur-1) var(--cpq-ease-smooth); }
.cre-cat em { font-style: normal; font-size: 11px; padding: 0 6px; border-radius: 8px; background: var(--cpq-overlay-a8); color: var(--cpq-text-muted); }
.cre-cat:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-text-primary); }
.cre-cat.on { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); background: var(--cpq-overlay-a8); }
.cre-cat.on em { background: var(--cpq-accent-primary); color: #fff; }
.cre-group { margin-bottom: 16px; }
.cre-group-head { display: flex; align-items: center; gap: 8px; margin: 2px 0 8px; }
.cre-group-bar { width: 3px; height: 14px; border-radius: 2px; flex: none; background: var(--cpq-text-disabled); }
.cre-group-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); }
.cre-group-count { font-size: 11px; color: var(--cpq-text-muted); padding: 0 7px; border-radius: 8px; background: var(--cpq-overlay-a10, rgba(0,0,0,.06)); }
.cre-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }
.cre-card { position: relative; padding: 8px 10px; display: flex; flex-direction: column; gap: 5px; cursor: pointer; transition: transform var(--cpq-dur-1) var(--cpq-ease-smooth); }
.cre-card:hover { transform: translateY(-1px); }
.cre-card.archived { opacity: .55; }
.cre-card-head { display: flex; align-items: center; gap: 6px; min-width: 0; }
.cre-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.cre-dot.on { background: var(--cpq-color-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cpq-color-success) 22%, transparent); }
.cre-dot.off { background: var(--cpq-text-muted); }
.cre-name { font-weight: 600; font-size: 13px; color: var(--cpq-text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cre-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; min-width: 0; }
.cre-hit { font-size: 10.5px; color: var(--cpq-text-muted); background: var(--cpq-overlay-a10); padding: 1px 6px; border-radius: 7px; white-space: nowrap; flex-shrink: 0; }
.cre-type-label { font-size: 10.5px; font-weight: 600; color: var(--cpq-text-muted); flex: none; padding: 1px 5px; border-radius: 5px; background: var(--cpq-overlay-a8); }
.cre-trigger { margin: 0; font-size: 11.5px; line-height: 1.35; color: var(--cpq-text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cre-card-foot { position: absolute; right: 8px; bottom: 6px; display: flex; gap: 2px; padding: 2px; border-radius: 8px; background: color-mix(in srgb, var(--cpq-glass-2-bg) 88%, transparent); opacity: 0; transition: opacity var(--cpq-dur-1) var(--cpq-ease-smooth); }
.cre-card:hover .cre-card-foot { opacity: 1; }

@media (max-width: 1180px) {
  .cre-hud-cards { max-height: 420px; }
}
@media (max-width: 560px) {
  .cre-list { grid-template-columns: 1fr; }
}
</style>
