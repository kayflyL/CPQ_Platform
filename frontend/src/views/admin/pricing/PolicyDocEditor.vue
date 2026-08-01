<script setup lang="ts">
/** 策略文档编辑器 —— a-modal:元数据 + markdown 编辑(左 textarea / 右实时预览)。
 *  新建:doc=null;编辑:doc=Strategy。保存走 strategyApi.saveDoc(自动落版本快照)。 */
import { ref, reactive, watch, computed } from 'vue'
import { message } from 'ant-design-vue'
import { strategyApi, type Strategy, type StrategyStatus } from '@/api/strategies'
import { DOC_CATEGORIES, readDocBody, type StrategyModule } from '@/constants/policyMeta'
import MarkdownView from '@/components/common/MarkdownView.vue'

const props = defineProps<{ open: boolean; doc: Strategy | null; module: StrategyModule }>()
const emit = defineEmits<{ 'update:open': [v: boolean]; saved: [] }>()

const saving = ref(false)
const previewMode = ref<'split' | 'edit' | 'preview'>('split')

interface DocForm {
  name: string
  category: string
  sort_order: number
  status: StrategyStatus
  change_reason: string
  description: string
  content_markdown: string
}

const form = reactive<DocForm>({
  name: '',
  category: DOC_CATEGORIES[0].value,
  sort_order: 1,
  status: 'active',
  change_reason: '',
  description: '',
  content_markdown: '',
})

watch(
  () => [props.open, props.doc] as const,
  ([isOpen, doc]) => {
    if (!isOpen) return
    if (doc) {
      const b = readDocBody(doc.body)
      form.name = doc.name
      form.category = b.category
      form.sort_order = b.sort_order
      form.status = doc.status
      form.change_reason = ''
      form.description = doc.description || ''
      form.content_markdown = b.content_markdown
    } else {
      form.name = ''
      form.category = DOC_CATEGORIES[0].value
      form.sort_order = 1
      form.status = 'active'
      form.change_reason = ''
      form.description = ''
      form.content_markdown = '# 新文档\n\n'
    }
  },
  { immediate: true },
)

const isEdit = computed(() => !!props.doc)

async function save() {
  const name = form.name.trim()
  const content = form.content_markdown.trim()
  if (!name) { message.warning('请填写文档标题'); return }
  if (!content) { message.warning('请填写文档内容'); return }
  saving.value = true
  try {
    await strategyApi.saveDoc({
      id: props.doc?.id,
      name,
      body: {
        module: props.module,
        category: form.category,
        sort_order: Number(form.sort_order) || 1,
        content_markdown: form.content_markdown,
      },
      description: form.description.trim() || undefined,
      change_reason: form.change_reason.trim() || undefined,
      status: form.status,
    })
    message.success(isEdit.value ? '已保存(新版本已留痕)' : '已创建')
    emit('saved')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function cancel() { emit('update:open', false) }
</script>

<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑文档' : '新建文档'"
    :width="980"
    :confirm-loading="saving"
    ok-text="保存"
    cancel-text="取消"
    :mask-closable="false"
    @ok="save"
    @cancel="cancel"
  >
    <div class="pe-meta">
      <a-input v-model:value="form.name" placeholder="文档标题" class="pe-title-input" />
      <a-select v-model:value="form.category" :options="DOC_CATEGORIES.map(c => ({ value: c.value, label: c.label }))" style="width: 140px" />
      <a-input-number v-model:value="form.sort_order" :min="0" :max="999" style="width: 90px">
        <template #addonBefore>排序</template>
      </a-input-number>
      <a-select v-model:value="form.status" :options="[{ value: 'active', label: 'active' }, { value: 'draft', label: 'draft' }, { value: 'archived', label: 'archived' }]" style="width: 110px" />
      <a-input v-model:value="form.change_reason" placeholder="修改说明(选填)" class="pe-reason-input" />
    </div>
    <a-input v-model:value="form.description" placeholder="摘要(选填)" class="pe-desc-input" />

    <div class="pe-toolbar">
      <a-radio-group v-model:value="previewMode" size="small" button-style="solid">
        <a-radio-button value="edit">仅编辑</a-radio-button>
        <a-radio-button value="split">分屏</a-radio-button>
        <a-radio-button value="preview">仅预览</a-radio-button>
      </a-radio-group>
      <span class="pe-hint">支持 Markdown(GFM 表格 / 代码块 / 引用)</span>
    </div>

    <div class="pe-editor" :data-mode="previewMode">
      <a-textarea
        v-show="previewMode !== 'preview'"
        v-model:value="form.content_markdown"
        :auto-size="{ minRows: 18, maxRows: 24 }"
        class="pe-textarea"
        placeholder="# 标题&#10;&#10;正文..."
      />
      <div v-show="previewMode !== 'edit'" class="pe-preview">
        <MarkdownView :content="form.content_markdown" />
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.pe-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.pe-title-input { flex: 1 1 220px; font-weight: 600; }
.pe-reason-input { flex: 1 1 200px; }
.pe-desc-input { margin-bottom: 10px; }
.pe-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.pe-hint { font-size: 11.5px; color: var(--cpq-text-muted); }
.pe-editor {
  display: flex;
  gap: 12px;
  min-height: 360px;
}
.pe-editor[data-mode='edit'] .pe-textarea,
.pe-editor[data-mode='preview'] .pe-preview { flex: 1 1 100%; }
.pe-editor[data-mode='split'] .pe-textarea { flex: 1 1 50%; }
.pe-editor[data-mode='split'] .pe-preview { flex: 1 1 50%; }
.pe-textarea { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; }
.pe-preview {
  border: 1px solid var(--cpq-border-secondary);
  border-radius: 8px;
  padding: 14px 18px;
  background: var(--cpq-bg-tertiary);
  overflow-y: auto;
  max-height: 460px;
}
</style>
