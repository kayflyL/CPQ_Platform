<script setup lang="ts">
/**
 * 添加规则弹窗（规则层「＋ 添加规则」入口）：打开即实时拉取策略中心当前规则清单——
 * 看到的就是策略中心此刻的状态，不是抽屉打开时的缓存。
 * 按组分节：节头「整组加入」（组内新增规则自动跟进），节内规则卡点击单条加入；
 * 已整组绑定的组整节不出现；已单选的规则卡不出现。弹窗不关可连续加，移除在已选卡。
 */
import { computed, ref, watch } from 'vue'
import { knowledgeApi, type KnowledgeGroupMeta } from '@/api/compatibilityRules'
import RuleCard from './RuleCard.vue'

const props = defineProps<{
  open: boolean
  selection: { groups: string[]; ruleIds: number[] }
}>()
const emit = defineEmits<{
  'update:open': [boolean]
  catalog: [KnowledgeGroupMeta[]]
  'add-group': [string]
  'add-rule': [number]
}>()

const groups = ref<KnowledgeGroupMeta[]>([])
const loading = ref(false)
const failed = ref(false)

/** 待选池 = 未整组绑定的组；节内规则卡排除已单选 */
const pool = computed(() => groups.value
  .filter(g => !props.selection.groups.includes(g.name))
  .map(g => ({ ...g, rules: g.rules.filter(r => !props.selection.ruleIds.includes(r.id)) })))

async function load() {
  loading.value = true
  failed.value = false
  try {
    const r = await knowledgeApi.getBindings()
    groups.value = r.groups || []
    emit('catalog', groups.value)
  } catch {
    groups.value = []
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (v) => { if (v) load() })
</script>

<template>
  <a-modal :open="open" title="添加规则" width="min(880px, calc(100vw - 32px))" :footer="null"
           wrap-class-name="portal-modal" @cancel="emit('update:open', false)">
    <p class="rpm-sub">实时读取策略中心·需求分析规则；点击规则卡单条加入，「整组加入」后组内新增规则自动跟进。规则本体去策略中心 → 需求分析规则页维护。</p>
    <a-spin :spinning="loading">
      <div v-if="failed" class="rpm-empty">规则清单拉取失败，请检查后端服务后重开。</div>
      <div v-else-if="!pool.length" class="rpm-empty">没有可引入的规则组——全部已整组引入，或策略中心暂无需求域规则。</div>
      <template v-else>
        <section v-for="g in pool" :key="g.name" class="rpm-section">
          <div class="rpm-group">
            <span class="rpm-name">{{ g.name }} <i class="rpm-count">（{{ g.count }} 条）</i></span>
            <span class="rpm-usage" :title="g.usage">{{ g.usage }}</span>
            <a-button size="small" type="link" class="rpm-join" @click="emit('add-group', g.name)">整组加入</a-button>
          </div>
          <div class="rpm-grid">
            <RuleCard v-for="r in g.rules" :key="r.id" kind="rule" :name="r.name"
                      :status="r.status" state="idle" interactive @add="emit('add-rule', r.id)" />
            <p v-if="!g.rules.length" class="rpm-empty rpm-empty--inline">该组规则已全部引入，可整组加入以跟进后续新增。</p>
          </div>
        </section>
      </template>
    </a-spin>
    <div class="rpm-foot">
      <a-button @click="emit('update:open', false)">完成</a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.rpm-sub { margin: 0 0 12px; font-size: 12px; color: var(--cpq-text-secondary); }
.rpm-section { margin-bottom: 14px; }
.rpm-group { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; min-width: 0; }
.rpm-name { font-size: 13px; font-weight: 600; color: var(--cpq-text-primary); white-space: nowrap; }
.rpm-count { font-style: normal; font-weight: 400; font-size: 11.5px; color: var(--cpq-text-muted); }
.rpm-usage {
  flex: 1; font-size: 11.5px; color: var(--cpq-text-secondary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.rpm-join { flex-shrink: 0; padding: 0; }
.rpm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 8px;
}
.rpm-empty { font-size: 12px; color: var(--cpq-text-muted); padding: 12px 0; }
.rpm-empty--inline { grid-column: 1 / -1; padding: 2px 6px; }
.rpm-foot { display: flex; justify-content: flex-end; margin-top: 8px; }
</style>
