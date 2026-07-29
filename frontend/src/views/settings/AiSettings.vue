<template>
  <div class="ai-settings-page">
    <div class="page-header">
      <h2>AI 设置</h2>
      <p class="subtitle">配置 AI 趋势洞察和方案助手的行为</p>
    </div>

    <a-tabs v-model:activeKey="activeTab">
      <!-- 趋势洞察 -->
      <a-tab-pane key="insights" tab="趋势洞察">
        <a-spin :spinning="loading">
          <div class="form-section">
            <h4 class="section-title">基础设置</h4>

            <div class="form-row">
              <label class="form-label">生成方式</label>
              <div class="form-control">
                <a-radio-group v-model:value="insightsConfig.auto_generate">
                  <a-radio :value="true">自动生成</a-radio>
                  <a-radio :value="false">手动刷新</a-radio>
                </a-radio-group>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">洞察数量</label>
              <div class="form-control">
                <a-slider v-model:value="insightsConfig.insight_count" :min="1" :max="5" style="width: 200px" />
                <span class="form-hint">{{ insightsConfig.insight_count }} 条</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">关注维度</label>
              <div class="form-control">
                <a-checkbox-group v-model:value="insightsConfig.dimensions">
                  <a-checkbox v-for="label, key in insightsConfig.dimension_labels" :key="key" :value="key">
                    {{ label }}
                  </a-checkbox>
                </a-checkbox-group>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">数据范围</label>
              <div class="form-control">
                <a-checkbox-group v-model:value="insightsConfig.data_scope">
                  <a-checkbox value="kpi">核心指标</a-checkbox>
                  <a-checkbox value="platform">平台分布</a-checkbox>
                  <a-checkbox value="sales">业务排行</a-checkbox>
                  <a-checkbox value="trend">趋势变化</a-checkbox>
                </a-checkbox-group>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">分析深度</label>
              <div class="form-control">
                <a-radio-group v-model:value="insightsConfig.depth">
                  <a-radio value="brief">简洁</a-radio>
                  <a-radio value="detailed">详细</a-radio>
                </a-radio-group>
              </div>
            </div>
          </div>

          <!-- 高级设置：维度标签 -->
          <div class="form-section">
            <h4 class="section-title">
              维度标签
              <span class="section-hint">自定义洞察维度的显示名称</span>
            </h4>

            <div class="form-row">
              <label class="form-label">增长信号</label>
              <div class="form-control">
                <a-input v-model:value="insightsConfig.dimension_labels.growth" size="small" style="width: 140px" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">风险预警</label>
              <div class="form-control">
                <a-input v-model:value="insightsConfig.dimension_labels.risk" size="small" style="width: 140px" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">行动建议</label>
              <div class="form-control">
                <a-input v-model:value="insightsConfig.dimension_labels.suggestion" size="small" style="width: 140px" />
              </div>
            </div>
          </div>

          <!-- 高级设置：提示词模板 -->
          <div class="form-section">
            <h4 class="section-title">
              提示词模板
              <span class="section-hint">自定义 AI 分析指令，支持变量：{dimensions}、{count}、{depth_desc}</span>
            </h4>

            <div class="form-row">
              <label class="form-label">分析指令</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start;">
                <a-textarea
                  v-model:value="insightsConfig.prompt_template"
                  :auto-size="{ minRows: 4, maxRows: 8 }"
                  placeholder="留空使用默认模板"
                  style="width: 100%"
                />
              </div>
            </div>
          </div>

          <!-- 高级设置：兜底文案 -->
          <div class="form-section">
            <h4 class="section-title">
              兜底文案
              <span class="section-hint">AI 调用失败时显示的内容</span>
            </h4>

            <div class="form-row">
              <label class="form-label">无数据时</label>
              <div class="form-control">
                <a-input v-model:value="insightsConfig.fallback_templates.no_data" size="small" />
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">出错时</label>
              <div class="form-control">
                <a-input v-model:value="insightsConfig.fallback_templates.error" size="small" />
              </div>
            </div>
          </div>

          <div class="form-actions">
            <a-button type="primary" :loading="saving" @click="handleSaveInsights">保存设置</a-button>
            <a-button @click="handleResetInsights">恢复默认</a-button>
          </div>
        </a-spin>
      </a-tab-pane>

      <!-- 方案助手 -->
      <a-tab-pane key="assistant" tab="方案助手">
        <a-spin :spinning="loading">
          <div class="form-section">
            <h4 class="section-title">基础设置</h4>

            <div class="form-row">
              <label class="form-label">自动上下文</label>
              <div class="form-control">
                <a-switch v-model:checked="assistantConfig.auto_context" />
                <span class="form-hint">打开时自动注入当前页面数据作为上下文</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">回复风格</label>
              <div class="form-control">
                <a-radio-group v-model:value="assistantConfig.response_style">
                  <a-radio value="brief">简洁</a-radio>
                  <a-radio value="detailed">详细</a-radio>
                </a-radio-group>
              </div>
            </div>
          </div>

          <div class="form-section">
            <h4 class="section-title">
              上下文来源
              <span class="section-hint">选择哪些页面可以提供上下文给 AI</span>
            </h4>

            <div class="provider-grid">
              <div v-for="(provider, key) in assistantConfig.providers" :key="key" class="provider-item">
                <div class="provider-header">
                  <a-checkbox v-model:checked="provider.enabled">{{ provider.label }}</a-checkbox>
                </div>
                <div class="provider-detail">
                  <a-input v-model:value="provider.label" size="small" placeholder="显示名称" style="width: 100px" />
                  <a-radio-group v-model:value="provider.detail" size="small">
                    <a-radio-button value="brief">简要</a-radio-button>
                    <a-radio-button value="detailed">详细</a-radio-button>
                  </a-radio-group>
                </div>
              </div>
            </div>
          </div>

          <div class="form-actions">
            <a-button type="primary" :loading="saving" @click="handleSaveAssistant">保存设置</a-button>
            <a-button @click="handleResetAssistant">恢复默认</a-button>
          </div>
        </a-spin>
      </a-tab-pane>

      <!-- API 设置 -->
      <a-tab-pane key="api" tab="API 设置">
        <a-spin :spinning="loading">
          <div class="form-section">
            <h4 class="section-title">LLM API 配置</h4>

            <div class="form-row">
              <label class="form-label">API 端点</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start;">
                <a-input v-model:value="llmConfig.base_url" placeholder="留空使用 .env 配置" style="width: 100%" />
                <span class="form-hint">如：https://dashscope.aliyuncs.com/compatible-mode/v1</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">API Key</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start;">
                <a-input-password v-model:value="llmConfig.api_key" placeholder="留空使用 .env 配置" style="width: 100%" />
                <span class="form-hint">留空则从 .env 的 LLM_API_KEY 读取</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">模型</label>
              <div class="form-control">
                <a-input v-model:value="llmConfig.model" placeholder="如 qwen-plus、gpt-4" style="width: 200px" />
                <span class="form-hint">留空使用 .env 的 LLM_MODEL</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">温度</label>
              <div class="form-control">
                <a-slider v-model:value="llmConfig.temperature" :min="0" :max="2" :step="0.1" style="width: 160px" />
                <span class="form-hint">{{ llmConfig.temperature }}</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">最大 Tokens</label>
              <div class="form-control">
                <a-input-number v-model:value="llmConfig.max_tokens" :min="100" :max="8000" :step="100" style="width: 140px" />
              </div>
            </div>
          </div>

          <div class="form-section">
            <h4 class="section-title">
              System Prompt
              <span class="section-hint">AI 助手的系统提示词</span>
            </h4>

            <div class="form-row">
              <label class="form-label">提示词</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start;">
                <a-textarea
                  v-model:value="llmConfig.system_prompt"
                  :auto-size="{ minRows: 4, maxRows: 10 }"
                  style="width: 100%"
                />
              </div>
            </div>
          </div>

          <div class="form-actions">
            <a-button type="primary" :loading="saving" @click="handleSaveLlm">保存设置</a-button>
            <a-button @click="handleResetLlm">恢复默认</a-button>
          </div>
        </a-spin>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

const DEFAULT_INSIGHTS_CONFIG = {
  auto_generate: true,
  insight_count: 3,
  dimensions: ['growth', 'risk', 'suggestion'],
  data_scope: ['kpi', 'platform', 'sales', 'trend'],
  depth: 'brief',
  dimension_labels: {
    growth: '增长信号',
    risk: '风险预警',
    suggestion: '行动建议'
  },
  prompt_template: '请分析以上数据，从以下维度发现值得关注的点：{dimensions}。\n\n要求：\n1. 输出 {count} 条洞察\n2. 每条洞察{depth_desc}\n3. 不要套话，直接给结论\n4. 如果发现增长，说明是什么在增长\n5. 如果发现风险，说明具体风险点\n6. 如果有建议，给出具体可操作的建议',
  fallback_templates: {
    no_data: '本周期暂无新增商机，建议关注跟进效率',
    error: '刷新重试获取 AI 分析'
  }
}

const DEFAULT_ASSISTANT_CONFIG = {
  auto_context: true,
  response_style: 'detailed',
  providers: {
    quote: { enabled: true, label: '报价工作台', detail: 'brief' },
    opportunity: { enabled: true, label: '商机详情', detail: 'brief' },
    'opportunity-list': { enabled: true, label: '商机线索', detail: 'brief' }
  }
}

const DEFAULT_LLM_CONFIG = {
  base_url: '',
  api_key: '',
  model: '',
  system_prompt: '你是 CPQ 平台的「方案助手」,辅助销售/FAE 做服务器配置与报价。用户当前所在页面的业务上下文会以「当前上下文」形式提供给你,作答时优先基于它。要求:1) 用中文回复;2) 对料号价格、库存、具体型号编号等易变信息,不要编造——不确定时请用户在配置页确认或查料号库;3) 回答简洁、分点。',
  temperature: 0.7,
  max_tokens: 2000,
}

const activeTab = ref('insights')
const loading = ref(true)
const saving = ref(false)
const insightsConfig = ref(JSON.parse(JSON.stringify(DEFAULT_INSIGHTS_CONFIG)))
const assistantConfig = ref({ ...DEFAULT_ASSISTANT_CONFIG })
const llmConfig = ref({ ...DEFAULT_LLM_CONFIG })

async function loadConfig() {
  loading.value = true
  try {
    const [insightsRes, assistantRes, llmRes] = await Promise.all([
      axios.get('/api/system-config/ai_insights_config/value'),
      axios.get('/api/system-config/ai_assistant_config/value'),
      axios.get('/api/system-config/llm_config/value'),
    ])
    if (insightsRes.data.value) {
      insightsConfig.value = { ...JSON.parse(JSON.stringify(DEFAULT_INSIGHTS_CONFIG)), ...insightsRes.data.value }
    }
    if (assistantRes.data.value) {
      assistantConfig.value = { ...DEFAULT_ASSISTANT_CONFIG, ...assistantRes.data.value }
    }
    if (llmRes.data.value) {
      llmConfig.value = { ...DEFAULT_LLM_CONFIG, ...llmRes.data.value }
    }
  } catch (err) {
    console.error('加载 AI 设置失败:', err)
    message.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

async function handleSaveInsights() {
  saving.value = true
  try {
    await axios.put('/api/system-config/ai_insights_config', {
      value: insightsConfig.value,
      type: 'json',
    })
    message.success('保存成功')
  } catch (err) {
    console.error('保存失败:', err)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSaveAssistant() {
  saving.value = true
  try {
    await axios.put('/api/system-config/ai_assistant_config', {
      value: assistantConfig.value,
      type: 'json',
    })
    message.success('保存成功')
  } catch (err) {
    console.error('保存失败:', err)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

function handleResetInsights() {
  insightsConfig.value = JSON.parse(JSON.stringify(DEFAULT_INSIGHTS_CONFIG))
  message.info('已恢复默认，请点击保存生效')
}

function handleResetAssistant() {
  assistantConfig.value = { ...DEFAULT_ASSISTANT_CONFIG }
  message.info('已恢复默认，请点击保存生效')
}

async function handleSaveLlm() {
  saving.value = true
  try {
    await axios.put('/api/system-config/llm_config', {
      value: llmConfig.value,
      type: 'json',
    })
    message.success('保存成功')
  } catch (err) {
    console.error('保存失败:', err)
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

function handleResetLlm() {
  llmConfig.value = { ...DEFAULT_LLM_CONFIG }
  message.info('已恢复默认，请点击保存生效')
}

onMounted(loadConfig)
</script>

<style scoped>
.ai-settings-page {
  padding: 24px;
  max-width: 800px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

.form-section {
  padding: 16px 0;
}

.section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--cpq-text-muted);
}

.form-row {
  display: flex;
  align-items: flex-start;
  padding: 10px 0;
  border-bottom: 1px solid var(--cpq-border-tertiary);
}

.form-row:last-child {
  border-bottom: none;
}

.form-label {
  flex-shrink: 0;
  width: 100px;
  font-size: 13px;
  font-weight: 500;
  color: var(--cpq-text-secondary);
  padding-top: 4px;
}

.form-control {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.form-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
}

.form-actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  margin-top: 8px;
  border-top: 1px solid var(--cpq-border-secondary);
}

.form-actions :deep(.ant-btn) {
  min-width: 88px;
}

.provider-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.provider-item {
  padding: 12px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-md);
}

.provider-header {
  margin-bottom: 8px;
}

.provider-detail {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-left: 24px;
}
</style>