<script setup lang="ts">
import { computed } from 'vue'
import { useSelectionRulesStore } from '@/stores/selectionRules'

import RuleCatalogPanel from './selection/compatibility/RuleCatalogPanel.vue'
import RuleEditModal from './selection/compatibility/RuleEditModal.vue'
import { useRuleCatalog } from '@/composables/useRuleCatalog'
import { useRuleEditor } from '@/composables/useRuleEditor'

const selectionRulesStore = useSelectionRulesStore()

const catalog = useRuleCatalog()
const groupedFiltered = computed(() => catalog.groupRules(catalog.searched.value))
const editor = useRuleEditor({
  rules: () => catalog.rules.value,
  afterChange,
})

async function afterChange() {
  await catalog.load()
  await selectionRulesStore.invalidateRules()
}

const {
  rules, loading, catFilter, searchText,
  categoryChips, uncategorizedCount, categoryOpts,
} = catalog
const {
  fieldOpts, filterFn, isNew, saving, form, editModalVisible,
  openNew, openEdit, closeEdit, save, remove, toggleStatus, resetDefaults, addCond, delCond,
} = editor

</script>


<template>
  <div class="cre">
    <div class="cre-main">
      <div class="cre-head">
        <span class="cre-hint">声明式兼容性规则 · WHEN 条件 → THEN 动作 · 选配时实时校验</span>
        <a-space>
          <a-button size="small" @click="resetDefaults">重置默认</a-button>
          <a-button type="primary" size="small" @click="openNew">+ 新建规则</a-button>
        </a-space>
      </div>

      <div class="cre-hud">
        <RuleCatalogPanel
          :rules="rules"
          :loading="loading"
          :search-text="searchText"
          :cat-filter="catFilter"
          :category-chips="categoryChips"
          :uncategorized-count="uncategorizedCount"
          :grouped-filtered="groupedFiltered"
          @update:search-text="v => searchText = v"
          @update:cat-filter="v => catFilter = v"
          @open-edit="openEdit"
          @remove="remove"
          @toggle-status="toggleStatus"
        />
      </div>
    </div>

    <RuleEditModal
      :open="editModalVisible"
      :is-new="isNew"
      :saving="saving"
      :form="form"
      :field-opts="fieldOpts"
      :category-opts="categoryOpts"
      :filter-fn="filterFn"
      @update:open="v => editModalVisible = v"
      @close="closeEdit"
      @save="save"
      @add-cond="addCond"
      @del-cond="delCond"
    />
  </div>
</template>

<style scoped>
.cre { display: flex; flex-direction: column; gap: 12px; }
.cre-main { display: flex; flex-direction: column; gap: 12px; }
.cre-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.cre-hint { color: var(--cpq-text-secondary); font-size: 12px; }

.cre-hud {
  display: block;
}
</style>
