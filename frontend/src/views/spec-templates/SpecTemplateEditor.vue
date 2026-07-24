<template>
  <div class="spec-template-editor">
    <div class="editor-header">
      <a-button @click="handleBack">← 返回</a-button>
      <h2>编辑规格书模板：{{ template.display_name }}</h2>
      <div class="preview-source">
        <a-select
          v-model:value="previewOppId"
          placeholder="选择商机"
          style="width:200px"
          size="small"
          show-search
          :filter-option="filterOption"
          :loading="opportunityListLoading"
          :disabled="!!opportunityListError"
          @change="onOpportunityChange"
        >
          <a-select-option
            v-for="opp in opportunityList"
            :key="opp.opportunity_id"
            :value="opp.opportunity_id"
          >
            {{ opp.customer_name }}
          </a-select-option>
        </a-select>
        <a-tooltip v-if="opportunityListError" :title="opportunityListError">
          <a-icon type="exclamation-circle" style="color: #ff4d4f; margin-left: 4px;" />
        </a-tooltip>
        <a-select
          v-model:value="previewQuoteId"
          placeholder="选择报价单（可选）"
          style="width:200px"
          size="small"
          allow-clear
          :disabled="!previewOppId || !!quotationListError"
          :loading="quotationListLoading"
        >
          <a-select-option
            v-for="quo in quotationList"
            :key="quo.quotation_id"
            :value="quo.quotation_id"
          >
            {{ quo.quotation_name || quo.quotation_id }}
          </a-select-option>
        </a-select>
        <a-tooltip v-if="quotationListError" :title="quotationListError">
          <a-icon type="exclamation-circle" style="color: #ff4d4f; margin-left: 4px;" />
        </a-tooltip>
        <a-button size="small" @click="loadPreviewData" :loading="loadingPreview" :disabled="!previewOppId">加载预览</a-button>
      </div>
      <a-button @click="handlePrint">打印</a-button>
      <a-button type="primary" @click="handleSave" :loading="saving">保存</a-button>
    </div>

    <div class="editor-content">
      <!-- 左侧配置面板 -->
      <div class="config-panel glass">
        <a-tabs v-model:activeKey="activeTab">
          <!-- 品牌配置 -->
          <a-tab-pane key="branding" tab="品牌配置">
            <div class="config-section">
              <h4>Logo</h4>
              <a-upload
                :show-upload-list="false"
                :before-upload="handleLogoUpload"
                accept="image/*"
              >
                <a-button :loading="uploadingLogo">
                  <a-icon type="upload" />
                  {{ template.branding.logo_url ? '更换 Logo' : '上传 Logo' }}
                </a-button>
              </a-upload>
              <div v-if="template.branding.logo_url" class="logo-preview-wrapper">
                <img :src="template.branding.logo_url" class="logo-preview" />
                <a-button type="link" size="small" @click="removeLogo">删除</a-button>
              </div>
              <div v-else class="logo-placeholder">
                暂未上传 Logo
              </div>
            </div>

            <div class="config-section">
              <h4>公司信息</h4>
              <a-form layout="vertical">
                <a-form-item label="公司名称">
                  <a-input v-model:value="template.branding.company_name" />
                </a-form-item>
                <a-form-item label="标语">
                  <a-input v-model:value="template.branding.tagline" />
                </a-form-item>
                <a-form-item label="文档标题">
                  <a-input v-model:value="template.branding.doc_title" placeholder="配置规格书 / Server Build Specification" />
                </a-form-item>
              </a-form>
            </div>

            <div class="config-section">
              <h4>联系方式</h4>
              <a-form layout="vertical">
                <a-form-item label="电话">
                  <a-input v-model:value="template.branding.contact_phone" />
                </a-form-item>
                <a-form-item label="邮箱">
                  <a-input v-model:value="template.branding.contact_email" />
                </a-form-item>
                <a-form-item label="地址">
                  <a-textarea v-model:value="template.branding.address" :rows="2" />
                </a-form-item>
                <a-form-item label="页脚备注">
                  <a-textarea v-model:value="template.branding.footer_note" :rows="2" />
                </a-form-item>
              </a-form>
            </div>

            <div class="config-section">
              <h4>报价条款</h4>
              <div class="config-hint">显示在「合计」与「页脚」之间的商务条款，留空则该条不显示。</div>
              <a-form layout="vertical">
                <a-form-item label="报价单位">
                  <a-input v-model:value="template.branding.commercial_terms.currency" placeholder="报价单位：人民币含税" />
                </a-form-item>
                <a-form-item label="报价有效期">
                  <a-input v-model:value="template.branding.commercial_terms.validity" placeholder="因 KP 波动，报价有效期 2 天" />
                </a-form-item>
                <a-form-item label="交付与付款">
                  <a-textarea v-model:value="template.branding.commercial_terms.delivery" :rows="2" placeholder="交付周期为签订合同收到预付款后 2-4 周内，合同签订后预付 50% 预付款" />
                </a-form-item>
                <a-form-item label="寄送范围">
                  <a-input v-model:value="template.branding.commercial_terms.shipping" placeholder="寄送至中国大陆境内" />
                </a-form-item>
              </a-form>
            </div>
          </a-tab-pane>

          <!-- 显示控制 -->
          <a-tab-pane key="display" tab="显示控制">
            <div class="config-section">
              <h4>价格显示</h4>
              <a-checkbox v-model:checked="template.display_options.show_price_column">显示价格列</a-checkbox>
            </div>

            <div class="config-section">
              <h4>合计行显示</h4>
              <a-checkbox v-model:checked="template.display_options.show_chassis_total">显示机箱总价</a-checkbox>
              <a-checkbox v-model:checked="template.display_options.show_kp_subtotal">显示 KP 配件合计</a-checkbox>
              <a-checkbox v-model:checked="template.display_options.show_grand_total">显示含税总价</a-checkbox>
              <a-checkbox v-model:checked="template.display_options.show_config_subtotal">显示含税单价</a-checkbox>
            </div>

            <div class="config-section">
              <h4>页脚显示</h4>
              <a-checkbox v-model:checked="template.display_options.show_footer_check">显示"✓ 已通过机型兼容校验"</a-checkbox>
              <a-checkbox v-model:checked="template.display_options.show_commercial_terms">显示"报价条款"区块</a-checkbox>
            </div>

            <div class="config-section">
              <h4>自定义标签</h4>
              <a-form layout="vertical" size="small">
                <a-form-item label="机箱规格标题">
                  <a-input v-model:value="labels.chassis_title" placeholder="机箱规格" />
                </a-form-item>
                <a-row :gutter="8">
                  <a-col :span="12">
                    <a-form-item label="形态">
                      <a-input v-model:value="labels.chassis_form" placeholder="形态" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="12">
                    <a-form-item label="盘位">
                      <a-input v-model:value="labels.chassis_bays" placeholder="盘位" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <a-row :gutter="8">
                  <a-col :span="12">
                    <a-form-item label="背板类型">
                      <a-input v-model:value="labels.chassis_backplane" placeholder="背板类型" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="12">
                    <a-form-item label="电源">
                      <a-input v-model:value="labels.chassis_power" placeholder="电源" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <a-form-item label="机箱总价">
                  <a-input v-model:value="labels.chassis_total" placeholder="机箱总价" />
                </a-form-item>
                <a-form-item label="KP配件标题">
                  <a-input v-model:value="labels.kp_title" placeholder="KP 配件" />
                </a-form-item>
                <a-row :gutter="8">
                  <a-col :span="6">
                    <a-form-item label="Catalogue">
                      <a-input v-model:value="labels.kp_catalogue" placeholder="Catalogue" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="6">
                    <a-form-item label="Description">
                      <a-input v-model:value="labels.kp_description" placeholder="Description" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="6">
                    <a-form-item label="Qty">
                      <a-input v-model:value="labels.kp_qty" placeholder="Qty" />
                    </a-form-item>
                  </a-col>
                  <a-col :span="6">
                    <a-form-item label="单价列">
                      <a-input v-model:value="labels.kp_cost" placeholder="Cost" />
                    </a-form-item>
                  </a-col>
                </a-row>
                <a-form-item label="KP合计">
                  <a-input v-model:value="labels.kp_subtotal" placeholder="KP 配件合计" />
                </a-form-item>
                <a-form-item label="含税单价">
                  <a-input v-model:value="labels.config_subtotal" placeholder="含税单价" />
                </a-form-item>
                <a-form-item label="含税总价">
                  <a-input v-model:value="labels.grand_total" placeholder="含税总价" />
                </a-form-item>
              </a-form>
            </div>
          </a-tab-pane>
        </a-tabs>
      </div>

      <!-- 右侧预览面板 -->
      <div class="preview-panel glass">
        <h4>实时预览</h4>
        <div class="preview-container">
          <SpecSheet
            :configs="previewConfigs"
            :branding="template.branding"
            :business-person="previewBusinessPerson"
            :display-options="template.display_options"
          />
        </div>
      </div>
    </div>

    <!-- 打印专用 overlay：Teleport 到 body，复用 SpecSheet 已有的 @media print 规则 -->
    <Teleport to="body">
      <div v-if="printMode" class="spec-sheet-overlay">
        <div class="spec-sheet-scroll">
          <SpecSheet
            class="spec-sheet-root"
            :configs="previewConfigs"
            :branding="template.branding"
            :business-person="previewBusinessPerson"
            :display-options="template.display_options"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { specTemplateApi } from '@/api/specTemplate'
import type { SpecTemplate, PreviewConfig, DisplayOptions } from '@/types/specTemplate'
import { getDefaultTemplateConfig } from '@/utils/defaultTemplateConfig'
import SpecSheet from '@/components/server-config/SpecSheet.vue'

const route = useRoute()
const router = useRouter()

const activeTab = ref('branding')
const saving = ref(false)
const uploadingLogo = ref(false)
const printMode = ref(false)
const template = ref<SpecTemplate>({
  id: 0,
  name: 'new-spec-template',
  display_name: '新建规格书模板',
  is_default: false,
  ...getDefaultTemplateConfig(),
  created_at: '',
  updated_at: ''
})

// labels 在 DisplayOptions 中是可选字段，但运行时由 getDefaultTemplateConfig() / loadTemplate()
// 保证一定存在。这里加一层本地别名兜底 undefined，供模板 v-model 直接使用（TS18048 止血）。
const labels = computed(() => template.value.display_options?.labels ?? ({} as NonNullable<DisplayOptions['labels']>))

// 预览数据源
const previewOppId = ref('')
const previewQuoteId = ref('')
const loadingPreview = ref(false)
const opportunityList = ref<any[]>([])
const opportunityListLoading = ref(false)
const opportunityListError = ref('')
const quotationList = ref<any[]>([])
const quotationListLoading = ref(false)
const quotationListError = ref('')

function filterOption(input: string, option: any) {
  const label = option?.children?.[0]?.children || ''
  return String(label).toLowerCase().includes(input.toLowerCase())
}

async function loadOpportunityList() {
  opportunityListLoading.value = true
  opportunityListError.value = ''
  try {
    const { opportunityApi } = await import('@/api/template')
    const list = await opportunityApi.list()
    opportunityList.value = list || []
    if (!list || list.length === 0) {
      opportunityListError.value = '暂无商机数据'
    }
  } catch (err: any) {
    console.warn('加载商机列表失败:', err.message)
    opportunityListError.value = err?.message || '加载失败'
    message.error('加载商机列表失败')
  } finally {
    opportunityListLoading.value = false
  }
}

async function loadQuotationList(opportunityId: string) {
  if (!opportunityId) {
    quotationList.value = []
    quotationListError.value = ''
    return
  }
  quotationListLoading.value = true
  quotationListError.value = ''
  try {
    const { quotationApi } = await import('@/api')
    const list = await quotationApi.getByOpportunity(opportunityId)
    quotationList.value = list || []
    if (!list || list.length === 0) {
      quotationListError.value = '该商机暂无报价单'
    }
  } catch (err: any) {
    console.warn('加载报价单列表失败:', err.message)
    quotationListError.value = err?.message || '加载失败'
    quotationList.value = []
  } finally {
    quotationListLoading.value = false
  }
}

function onOpportunityChange() {
  previewQuoteId.value = ''
  loadQuotationList(previewOppId.value)
}

/** 多配置模式的数据结构（对应后端 PreviewConfig） */
const previewConfigs = ref<PreviewConfig[]>([])
const previewBusinessPerson = ref('')

async function loadPreviewData() {
  if (!previewOppId.value) {
    message.warning('请选择商机')
    return
  }
  loadingPreview.value = true
  try {
    console.log('[SpecTemplateEditor] 加载预览数据，opportunity_id:', previewOppId.value)
    const data = await specTemplateApi.getPreviewData(previewOppId.value, previewQuoteId.value || undefined)
    console.log('[SpecTemplateEditor] 后端返回数据:', data)

    // 提取销售人员信息
    previewBusinessPerson.value = data.business_person || ''

    // 直接使用后端返回的 configs 数组
    previewConfigs.value = data.configs || []
    console.log('[SpecTemplateEditor] previewConfigs:', previewConfigs.value.length, '条')

    // 没有配置时给出明确提示
    if (!previewConfigs.value.length) {
      message.info('该商机/报价单暂无配置数据，请先在报价单中添加配置')
      return
    }

    message.success(`已加载 ${previewConfigs.value.length} 个配置`)
  } catch (error: any) {
    console.error('加载预览数据失败:', error)
    message.error(error?.message || '加载预览数据失败，请检查商机/报价单是否有效')
  } finally {
    loadingPreview.value = false
  }
}

async function handlePrint() {
  if (!previewConfigs.value.length) {
    message.warning('请先加载预览数据后再打印')
    return
  }
  // 渲染 teleported overlay（携带 .spec-sheet-root），复用 SpecSheet 的 @media print 规则
  printMode.value = true
  await nextTick()
  fitPagesForPrint()
  // 浏览器「另存为 PDF」用 document.title 当文件名：临时改成规格书名，打印后还原
  const prevTitle = document.title
  document.title = buildPrintTitle()
  window.addEventListener('afterprint', () => {
    document.title = prevTitle
    printMode.value = false
  }, { once: true })
  window.print()
}

/** 打印文件名：文档标题 - 公司名 - 日期 */
function buildPrintTitle() {
  const b = template.value.branding
  const date = new Date().toLocaleDateString('zh-CN')
  return [b?.doc_title || '规格书', b?.company_name, date]
    .filter(s => s && s.trim())
    .join('-')
}

/** 打印前按 A4 可打印区缩放每个配置页，保证「一配置一页」、末尾不被挤到下一页。
 *  只写 CSS 变量，真正 scale 只在 @media print 生效，屏内 overlay 不受影响。 */
function fitPagesForPrint() {
  const PRINT_W = (210 - 28) * 96 / 25.4 // A4 减 14mm 页边距 ≈ 688px
  const PRINT_H = (297 - 28) * 96 / 25.4 // ≈ 1017px
  document.querySelectorAll<HTMLElement>('.spec-sheet-overlay .ss-page').forEach(page => {
    // 克隆到离屏容器，按「打印宽度 + 无 padding」量自然内容高度，避开屏幕样式(min-height:297mm)干扰
    const clone = page.cloneNode(true) as HTMLElement
    clone.style.minHeight = 'auto'
    clone.style.height = 'auto'
    clone.style.padding = '0'
    clone.style.width = '100%'
    clone.style.transform = ''
    const meter = document.createElement('div')
    meter.style.cssText = `position:absolute;left:-99999px;top:0;width:${PRINT_W}px;visibility:hidden;`
    meter.appendChild(clone)
    document.body.appendChild(meter)
    const naturalH = clone.scrollHeight
    document.body.removeChild(meter)

    const scale = naturalH > 0 ? Math.min(1, PRINT_H / naturalH) : 1
    page.style.setProperty('--print-scale', String(scale))
    page.style.setProperty('--print-h', scale < 1 ? `${Math.round(naturalH * scale)}px` : 'auto')
  })
}

onMounted(async () => {
  await loadOpportunityList()
  const templateId = route.params.id
  if (templateId && templateId !== 'new') {
    await loadTemplate(Number(templateId))
  }
})

async function loadTemplate(id: number) {
  try {
    const data = await specTemplateApi.getById(id)
    const defaults = getDefaultTemplateConfig()
    template.value = {
      ...defaults,
      ...data,
      // 兼容旧数据：缺失字段用默认值填充
      branding: { ...defaults.branding, ...data.branding },
      display_options: {
        ...defaults.display_options,
        ...data.display_options,
        labels: { ...defaults.display_options.labels, ...data.display_options?.labels }
      }
    }
    // 旧默认值迁移：config_subtotal/grand_total 曾默认为「小计」「整机合计」，
    // 语义已改为含税单价/含税总价。命中旧默认串视为「未自定义」，替换为新默认，
    // 避免历史模板残留旧叫法（用户若曾自定义成别的值则不动）。
    const lg = template.value.display_options.labels
    if (lg && lg.config_subtotal === '小计') lg.config_subtotal = defaults.display_options.labels!.config_subtotal
    if (lg && lg.grand_total === '整机合计') lg.grand_total = defaults.display_options.labels!.grand_total
  } catch (error) {
    message.error('加载模板失败')
  }
}

async function handleLogoUpload(file: File) {
  uploadingLogo.value = true
  try {
    const result = await specTemplateApi.uploadLogo(file)
    template.value.branding.logo_url = result.url
    message.success('Logo 上传成功')
  } catch (error) {
    console.error('Logo 上传失败:', error)
    message.error('Logo 上传失败，请重试')
  } finally {
    uploadingLogo.value = false
  }
  return false
}

function removeLogo() {
  template.value.branding.logo_url = ''
}

async function handleSave() {
  saving.value = true
  try {
    if (template.value.id === 0) {
      // 新建
      const created = await specTemplateApi.create(template.value)
      message.success('创建成功')
      router.push(`/spec-templates/${created.id}/edit`)
    } else {
      // 更新
      await specTemplateApi.update(template.value.id, template.value)
      message.success('保存成功')
    }
  } catch (error: any) {
    console.error('保存模板失败:', error)
    message.error(error?.response?.data?.detail || error?.message || '保存失败，请重试')
  } finally {
    saving.value = false
  }
}

function handleBack() {
  router.push('/export-templates')
}
</script>

<style scoped>
.spec-template-editor {
  padding: 24px;
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.editor-header h2 {
  margin: 0;
  flex: 1;
}

.editor-content {
  display: flex;
  gap: 24px;
  flex: 1;
  overflow: hidden;
}

.config-panel {
  width: 400px;
  border-radius: 8px;
  padding: 20px;
  overflow-y: auto;
}

.config-section {
  margin-bottom: 24px;
}

.config-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
}

.config-hint {
  margin: -4px 0 12px 0;
  font-size: 12px;
  color: var(--cpq-text-tertiary, #9CA3AF);
  line-height: 1.5;
}

.logo-preview {
  max-width: 200px;
  max-height: 100px;
  border: 1px solid var(--cpq-border-dark);
  border-radius: 4px;
}

.logo-preview-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.logo-preview-wrapper .logo-preview {
  margin-top: 0;
}

.logo-placeholder {
  margin-top: 12px;
  padding: 16px;
  text-align: center;
  color: var(--cpq-text-tertiary);
  font-size: 12px;
  background: var(--cpq-bg-dark);
  border: 1px dashed var(--cpq-border-dark);
  border-radius: 4px;
}

.preview-panel {
  flex: 1;
  border-radius: 8px;
  padding: 20px;
  overflow-y: auto;
}

.preview-panel h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
}

.preview-container {
  border: 1px solid var(--cpq-border-dark);
  border-radius: 4px;
  padding: 20px;
  background: var(--cpq-bg-dark);
}

/* 打印 overlay：Teleport 到 body（保留本组件 scoped data-v，样式仍生效）。
   打印规则由 SpecSheet.vue 的非 scoped @media print 接管，这里只管屏内表现。 */
.spec-sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--cpq-overlay-b85);
  backdrop-filter: blur(8px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 32px 16px;
  overflow-y: auto;
}
.spec-sheet-scroll {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  width: 100%;
  max-width: 900px;
}
</style>
