<script setup lang="ts">
/**
 * 兼容规则页（选型配置·兼容规则）——与需求分析规则页同款布局语法：
 * 简介行+搜索 / 按业务分类分组 section / RuleCard 卡片网格 / 虚线新增尾卡 / 空态。
 * 规则本体的 WHEN/THEN 编辑在 RuleEditModal（通用引擎编辑器），卡片只做浏览与快捷操作。
 */
import { computed } from 'vue'
import { useSelectionRulesStore } from '@/stores/selectionRules'
import RuleCard from '@/components/flow-canvas/RuleCard.vue'
import RuleEditModal from './selection/compatibility/RuleEditModal.vue'
import { useRuleCatalog } from '@/composables/useRuleCatalog'
import { useRuleEditor } from '@/composables/useRuleEditor'
import { RULE_TYPE_MAP, RULE_TYPE_BADGE } from '@/constants/ruleMeta'
import type { CompatibilityRule } from '@/api/compatibilityRules'

const selectionRulesStore = useSelectionRulesStore()

const catalog = useRuleCatalog()
const sections = computed(() => catalog.groupRules(catalog.searched.value))
const editor = useRuleEditor({
  rules: () => catalog.rules.value,
  afterChange,
})

async function afterChange() {
  await catalog.load()
  await selectionRulesStore.invalidateRules()
}

const { loading, searchText, categoryOpts, whenSummary } = catalog
const {
  fieldOpts, filterFn, isNew, saving, form, editModalVisible,
  openNew, openEdit, closeEdit, save, remove, toggleStatus, addCond, delCond,
} = editor

function countLabel(list: CompatibilityRule[]): string {
  const on = list.filter(r => r.status === 'active').length
  const draft = list.filter(r => r.status === 'draft' || r.status === 'testing').length
  return `${on} 生效${draft ? ` · ${draft} 草稿` : ''}`
}

function ruleMeta(r: CompatibilityRule): string {
  const parts = [RULE_TYPE_MAP[r.type]?.label || r.type]
  if (r.hit_count) parts.push(`命中 ${r.hit_count} 次`)
  return parts.join(' · ')
}

function ruleContent(r: CompatibilityRule): string {
  const desc = (r.body?.desc || r.description || '').trim()
  return desc || whenSummary(r.body)
}
</script>

<template>
  <div class="cre">
    <div class="cre-top">
      <p class="cre-sub">
        声明式兼容规则：WHEN 条件 → THEN 动作，选配与需求分析出方案时<em>实时校验</em>，保存即生效。
      </p>
      <a-input v-model:value="searchText" class="cre-search" placeholder="搜索规则名称/条件" size="small" allow-clear />
    </div>

    <a-spin :spinning="loading">
      <div class="cre-body">
        <section v-for="grp in sections" :key="grp.key" class="cre-sec">
          <div class="cre-sec-head">
            <span class="cre-sec-title">{{ grp.category || '未分类' }}</span>
            <span class="cre-sec-count">{{ countLabel(grp.rules) }}</span>
          </div>
          <div class="cre-grid">
            <div v-for="r in grp.rules" :key="r.id" class="cre-cell" @click="openEdit(r)">
              <RuleCard
                kind="rule" tone="group" :badge="RULE_TYPE_BADGE[r.type] || '条'"
                :name="r.name" :status="r.status" :meta="ruleMeta(r)" :summary="ruleContent(r)"
              >
                <template #actions>
                  <button class="rc-linkbtn" @click.stop="toggleStatus(r)">{{ r.status === 'active' ? '停用' : '启用' }}</button>
                  <button class="rc-linkbtn" @click.stop="openEdit(r)">编辑</button>
                  <button class="rc-linkbtn rc-linkbtn--danger" @click.stop="remove(r)">删除</button>
                </template>
              </RuleCard>
            </div>
            <button class="cre-add" @click="openNew(grp.category || undefined)">＋ 新增规则</button>
          </div>
        </section>
        <div v-if="!sections.length" class="cre-none">
          {{ searchText ? '没有匹配的规则，换个关键词试试' : '还没有规则，点「＋ 新增规则」建一条' }}
        </div>
      </div>
    </a-spin>

    <RuleEditModal
      :open="editModalVisible" :is-new="isNew" :saving="saving" :form="form"
      :field-opts="fieldOpts" :category-opts="categoryOpts" :filter-fn="filterFn"
      @update:open="v => editModalVisible = v" @close="closeEdit" @save="save"
      @add-cond="addCond" @del-cond="delCond"
    />
  </div>
</template>

<style scoped>
.cre { display: flex; flex-direction: column; gap: var(--cpq-space-4); max-width: 1228px; margin: 0 auto; }
.cre-top { display: flex; align-items: center; gap: var(--cpq-space-4); }
.cre-sub { flex: 1; margin: 0; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-secondary); }
.cre-sub em { font-style: normal; color: var(--cpq-accent-primary); }
.cre-search { width: 240px; flex-shrink: 0; }

.cre-sec { display: flex; flex-direction: column; gap: var(--cpq-space-3); }
.cre-sec-head { display: flex; align-items: center; gap: var(--cpq-space-2); }
.cre-sec-title { font-size: var(--cpq-font-size-base); font-weight: 600; color: var(--cpq-text-primary); }
.cre-sec-count { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); padding: 0 8px; border-radius: var(--cpq-radius-sm); background: var(--cpq-overlay-w6); }
.cre-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--cpq-space-3); }
.cre-cell { cursor: pointer; min-width: 0; }
.rc-linkbtn {
  border: 0; background: transparent; padding: 2px 8px;
  font-size: var(--cpq-font-size-xs); color: var(--cpq-text-secondary);
  cursor: pointer; border-radius: var(--cpq-radius-sm); transition: color .15s, background .15s;
}
.rc-linkbtn:hover { color: var(--cpq-accent-primary); background: var(--cpq-overlay-w6); }
.rc-linkbtn--danger:hover { color: var(--cpq-accent-danger); }
.cre-add {
  border: 1px dashed var(--cpq-glass-border); border-radius: var(--cpq-radius-lg); min-height: 72px;
  display: flex; align-items: center; justify-content: center; color: var(--cpq-text-muted);
  font-size: var(--cpq-font-size-sm); cursor: pointer; background: transparent; transition: border-color .18s, color .18s;
}
.cre-add:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-accent-primary); }

.cre-none {
  margin-top: var(--cpq-space-2); padding: var(--cpq-space-3); text-align: center; font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-muted); border: 1px dashed var(--cpq-glass-border); border-radius: var(--cpq-radius-lg);
}
</style>
