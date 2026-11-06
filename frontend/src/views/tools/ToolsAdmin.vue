<script setup lang="ts">
/** 工具内容编辑（/tools/admin，权限键 action.tools.content.manage，默认仅 admin）。
 *  设置卡范式（页面→卡片→行，无字段级描边）：左列工具清单，右列四张设置卡
 *  （工具中心卡片 / 说明区条目 / 导流条 / 页面标题）。保存=整 blob 写 rules.tool_contents。
 *  工具内的计算数值不归这里（gpu-sizing 三软库照旧）。 */
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { TOOLS, type ToolContent } from '@/constants/toolsRegistry'
import { useToolsContentStore } from '@/stores/toolsContent'

const router = useRouter()
const store = useToolsContentStore()
const activeKey = ref(TOOLS[0]?.key || '')
const saving = ref(false)

const CTA_TARGETS = [
  { value: '/servers', label: '服务器产品库（/servers）' },
  { value: '/catalog', label: '公开产品目录（/catalog）' },
  { value: '/strategies', label: '解决方案门户（/strategies）' },
]

/** 表单工作副本：DB 内容合并默认值后深拷贝；tags 转逗号串便于行内编辑。 */
const form = reactive<ToolContent & { tagsText?: string }>(JSON.parse(JSON.stringify(TOOLS[0]?.defaultContent || {})))

function loadForm() {
  const c = store.of(activeKey.value)
  Object.assign(form, JSON.parse(JSON.stringify(c)), { tagsText: (c.tags || []).join(', ') })
}
watch(activeKey, loadForm, { immediate: true })

function addDocItem() {
  form.doc_items.push({ title: '', formula: '', text: '' })
}
function removeDocItem(i: number) {
  if (form.doc_items.length <= 1) {
    message.warning('至少保留一条说明（可在卡片上关闭「展示说明区」整块隐藏）')
    return
  }
  form.doc_items.splice(i, 1)
}

async function save() {
  if (!form.name?.trim()) { message.warning('工具名称不能为空'); return }
  saving.value = true
  try {
    const payload: ToolContent = {
      ...JSON.parse(JSON.stringify(form)),
      tags: (form.tagsText || '').split(/[,，]/).map(s => s.trim()).filter(Boolean),
    }
    delete (payload as any).tagsText
    await store.save(activeKey.value, payload)
    message.success('已保存，前台即时生效')
    loadForm()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="ta-page">
    <div class="back-row">
      <a class="ta-back" @click="router.push('/tools')">
        <span class="ta-back-arrow">←</span> 工具
      </a>
      <span class="back-sep">/</span>
      <span class="back-cur">内容编辑</span>
    </div>

    <div class="page-head">
      <h1>工具内容编辑</h1>
      <p class="sub">工具中心与工具页的展示文案统一在这里维护，保存即生效；工具内的计算数值不归这里管（继续走各自的数据库）。</p>
    </div>

    <div class="admin-cols">
      <div class="set-card">
        <div class="sc-head">
          <div class="sc-title">工具</div>
          <div class="sc-desc">选择要编辑内容的工具</div>
        </div>
        <div class="tool-list">
          <button
            v-for="t in TOOLS" :key="t.key"
            class="tl-item" :class="{ active: t.key === activeKey }"
            @click="activeKey = t.key"
          >
            {{ store.of(t.key).name || t.key }}
            <span class="tl-sub">{{ t.path }} · {{ store.of(t.key).visible === false ? '已下架' : '已上架' }}</span>
          </button>
        </div>
      </div>

      <div>
        <div class="set-card">
          <div class="sc-head">
            <div class="sc-title">工具中心卡片</div>
            <div class="sc-desc">工具中心列表卡片上展示的文字</div>
          </div>
          <div class="set-row"><span class="set-label">工具名称</span><span class="set-ctrl"><a-input v-model:value="form.name" :maxlength="30" /></span></div>
          <div class="set-row set-row--top"><span class="set-label">一句话描述</span><span class="set-ctrl"><a-textarea v-model:value="form.desc" :rows="3" :maxlength="200" /></span></div>
          <div class="set-row"><span class="set-label">分类</span><span class="set-ctrl"><a-input v-model:value="form.category" :maxlength="20" /></span></div>
          <div class="set-row"><span class="set-label">标签（逗号分隔）</span><span class="set-ctrl"><a-input v-model:value="form.tagsText" :maxlength="60" /></span></div>
          <div class="set-row"><span class="set-label">排序权重</span><span class="set-ctrl"><a-input-number v-model:value="form.order" :min="0" :max="9999" /></span></div>
          <div class="set-row"><span class="set-label">在工具中心展示</span><span class="set-ctrl"><a-switch v-model:checked="form.visible" /></span></div>
        </div>

        <div class="set-card">
          <div class="sc-head">
            <div class="sc-title">说明区条目</div>
            <div class="sc-desc">工具页底部「{{ form.doc_title }}」区块；每条 = 标题 + 公式行 + 说明文字</div>
          </div>
          <div class="set-row"><span class="set-label">区块标题</span><span class="set-ctrl"><a-input v-model:value="form.doc_title" :maxlength="20" /></span></div>
          <div v-for="(item, i) in form.doc_items" :key="i" class="entry">
            <div class="en-row">
              <span class="en-label">标题</span>
              <a-input v-model:value="item.title" :maxlength="20" />
              <button class="en-del" @click="removeDocItem(i)">删除</button>
            </div>
            <div class="en-row"><span class="en-label">公式行</span><a-input v-model:value="item.formula" :maxlength="80" /></div>
            <div class="en-row en-row--top"><span class="en-label">说明</span><a-textarea v-model:value="item.text" :rows="2" :maxlength="200" /></div>
          </div>
          <button class="entry-add" @click="addDocItem"><PlusOutlined /> 新增条目</button>
          <div class="set-row" style="margin-top: var(--cpq-space-2)"><span class="set-label">展示说明区</span><span class="set-ctrl"><a-switch v-model:checked="form.doc_visible" /></span></div>
        </div>

        <div class="set-card">
          <div class="sc-head">
            <div class="sc-title">导流条</div>
            <div class="sc-desc">工具页底部的行动引导</div>
          </div>
          <div class="set-row set-row--top"><span class="set-label">文案</span><span class="set-ctrl"><a-textarea v-model:value="form.cta_text" :rows="2" :maxlength="100" /></span></div>
          <div class="set-row"><span class="set-label">按钮文字</span><span class="set-ctrl"><a-input v-model:value="form.cta_button" :maxlength="20" /></span></div>
          <div class="set-row"><span class="set-label">跳转目标</span><span class="set-ctrl"><a-select v-model:value="form.cta_target" :options="CTA_TARGETS" class="cta-select" /></span></div>
          <div class="set-row"><span class="set-label">展示导流条</span><span class="set-ctrl"><a-switch v-model:checked="form.cta_visible" /></span></div>
        </div>

        <div class="set-card">
          <div class="sc-head">
            <div class="sc-title">页面标题</div>
            <div class="sc-desc">工具页打开时的标题与副标题</div>
          </div>
          <div class="set-row"><span class="set-label">页标题</span><span class="set-ctrl"><a-input v-model:value="form.page_title" :maxlength="30" /></span></div>
          <div class="set-row set-row--top"><span class="set-label">副标题</span><span class="set-ctrl"><a-textarea v-model:value="form.page_sub" :rows="2" :maxlength="120" /></span></div>
        </div>

        <div class="admin-save">
          <button class="save-btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ta-page { max-width: 1600px; margin: 0 auto; padding: var(--cpq-space-4) var(--cpq-space-5) 80px; }
.back-row { display: flex; align-items: center; gap: var(--cpq-space-2); margin-bottom: var(--cpq-space-3); }
.ta-back { color: var(--cpq-text-secondary); cursor: pointer; font-size: 13px; transition: color 0.15s; user-select: none; white-space: nowrap; }
.ta-back:hover { color: var(--cpq-accent-primary); }
.ta-back-arrow { margin-right: 2px; }
.back-sep { color: var(--cpq-text-disabled); }
.back-cur { color: var(--cpq-text-secondary); font-size: 13px; }
.page-head { margin-bottom: var(--cpq-space-4); }
.page-head h1 { font-size: var(--cpq-font-size-2xl); font-weight: var(--cpq-font-weight-semibold); line-height: var(--cpq-line-height-heading); color: var(--cpq-text-primary); }
.page-head .sub { margin-top: var(--cpq-space-2); font-size: var(--cpq-font-size-base); color: var(--cpq-text-secondary); }

.admin-cols { display: grid; grid-template-columns: 240px minmax(min(560px, 100%), 1fr); gap: var(--cpq-space-4); align-items: start; }

.set-card {
  padding: var(--cpq-space-4);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-1-bg);
  backdrop-filter: blur(var(--cpq-glass-blur-1)); -webkit-backdrop-filter: blur(var(--cpq-glass-blur-1));
}
.set-card + .set-card { margin-top: var(--cpq-space-4); }
.sc-head { margin-bottom: var(--cpq-space-2); }
.sc-title { font-size: var(--cpq-font-size-lg); font-weight: var(--cpq-font-weight-semibold); color: var(--cpq-text-primary); }
.sc-desc { margin-top: 3px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); line-height: 1.55; }

.set-row {
  display: flex; align-items: center; justify-content: space-between; gap: var(--cpq-space-3);
  padding: var(--cpq-space-3) 0;
  border-bottom: 1px solid var(--cpq-border-secondary);
}
.set-row:last-child { border-bottom: none; }
.set-row--top { align-items: flex-start; }
.set-row--top .set-label { padding-top: 6px; }
.set-label { font-size: var(--cpq-font-size-base); color: var(--cpq-text-primary); white-space: nowrap; flex: none; }
.set-ctrl { flex: 1; display: flex; justify-content: flex-end; }

.tool-list { display: flex; flex-direction: column; gap: var(--cpq-space-2); }
.tl-item {
  padding: var(--cpq-space-3); border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-border-secondary); background: transparent;
  cursor: pointer; text-align: left; font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-secondary); transition: all var(--cpq-dur-1);
}
.tl-item:hover { border-color: var(--cpq-border-light); color: var(--cpq-text-primary); }
.tl-item.active { border-color: var(--cpq-accent-primary); background: var(--cpq-overlay-a5); color: var(--cpq-text-primary); font-weight: var(--cpq-font-weight-semibold); }
.tl-item .tl-sub { display: block; margin-top: 2px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); font-weight: var(--cpq-font-weight-normal); }

.entry { padding: var(--cpq-space-3) 0; border-bottom: 1px solid var(--cpq-border-secondary); }
.en-row { display: flex; align-items: center; gap: var(--cpq-space-3); margin-top: var(--cpq-space-2); }
.en-row:first-child { margin-top: 0; }
.en-label { width: 52px; flex: none; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.en-row .en-label + * { flex: 1; }
.en-row--top { align-items: flex-start; }
.en-row--top .en-label { padding-top: 6px; }
.en-del { flex: none; font-size: var(--cpq-font-size-xs); color: var(--cpq-accent-danger); background: none; border: 0; cursor: pointer; }
.en-del:hover { opacity: 0.8; }
.entry-add {
  margin-top: var(--cpq-space-3); width: 100%; min-height: 38px;
  border: 1px dashed var(--cpq-glass-border); border-radius: var(--cpq-radius-md);
  background: transparent; color: var(--cpq-text-muted); cursor: pointer; font-size: var(--cpq-font-size-sm);
  display: inline-flex; align-items: center; justify-content: center; gap: var(--cpq-space-1);
  transition: all var(--cpq-dur-1);
}
.entry-add:hover { border-color: var(--cpq-glass-border-strong); color: var(--cpq-accent-primary); }

.admin-save { display: flex; justify-content: flex-end; margin-top: var(--cpq-space-4); }
.save-btn {
  border: 0; cursor: pointer; padding: var(--cpq-space-2) var(--cpq-space-5);
  border-radius: var(--cpq-radius-sm); background: var(--cpq-accent-gradient);
  color: var(--cpq-accent-on-primary); font-size: var(--cpq-font-size-base); font-weight: var(--cpq-font-weight-semibold);
  box-shadow: 0 4px 14px var(--cpq-shadow-color-soft);
  transition: transform var(--cpq-dur-1) var(--cpq-ease-spring);
}
.save-btn:hover { transform: translateY(-1px); }
.save-btn:disabled { opacity: 0.6; transform: none; cursor: default; }

.cta-select { width: 320px; max-width: 100%; }

@media (max-width: 768px) {
  .ta-page { padding: var(--cpq-space-3) var(--cpq-space-4) 80px; }
  .admin-cols { grid-template-columns: 1fr; }
  .set-row { flex-wrap: wrap; }
  .set-ctrl { justify-content: flex-start; width: 100%; }
  .set-ctrl :deep(.ant-input), .set-ctrl :deep(.ant-select), .set-ctrl :deep(.ant-input-number),
  .cta-select { width: 100%; }
  .set-ctrl :deep(textarea.ant-input) { min-width: 0; }
  .admin-save { position: sticky; bottom: calc(var(--cpq-tabbar-inset, 58px) + var(--cpq-space-3)); }
  .save-btn { width: 100%; }
}
</style>
