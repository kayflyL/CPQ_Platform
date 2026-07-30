<template>
  <div class="ai-settings-page">
    <div class="page-header">
      <h2>AI 设置</h2>
      <p class="subtitle">配置方案助手的行为与模型 API</p>
    </div>

    <a-tabs v-model:activeKey="activeTab">
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

      <!-- 趋势分析 -->
      <a-tab-pane key="trend" tab="趋势分析">
        <a-spin :spinning="loading">
          <div class="form-section">
            <h4 class="section-title">
              分析本期趋势
              <span class="section-hint">商机线索页方案助手「📈 分析本期趋势」快捷指令的提示词</span>
            </h4>

            <div class="form-row">
              <label class="form-label">重点商机条数</label>
              <div class="form-control">
                <a-slider v-model:value="trendConfig.highlight_count" :min="5" :max="20" style="width: 200px" />
                <span class="form-hint">{{ trendConfig.highlight_count }} 条（近半年，按台数降序）</span>
              </div>
            </div>
          </div>

          <div class="form-section">
            <h4 class="section-title">
              提示词模板
              <span class="section-hint">引导 AI 输出口径；周/月/半年数据与重点商机由系统自动注入</span>
            </h4>

            <div class="form-row">
              <label class="form-label">分析指令</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start;">
                <a-textarea
                  v-model:value="trendConfig.prompt_template"
                  :auto-size="{ minRows: 6, maxRows: 16 }"
                  style="width: 100%"
                />
              </div>
            </div>
          </div>

          <div class="form-actions">
            <a-button type="primary" :loading="saving" @click="handleSaveTrend">保存设置</a-button>
            <a-button @click="handleResetTrend">恢复默认</a-button>
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

// 与后端 ai_trend_analysis 种子保持一致（恢复默认用）；运行时实际从后端读取
const DEFAULT_TREND_CONFIG = {
  highlight_count: 10,
  prompt_template: `你是 CPQ 平台的数据分析师。下面提供「本周/本月/近半年」三个周期的商机聚合数据,以及近期重点商机明细。请输出一份结构化趋势洞察报告,严格按以下分节:

# 一、周数据
本周商机数、各平台商机数与配置数。

# 二、月数据
本月商机数、各平台商机数与配置数。

# 三、半年度商机趋势
近半年逐月商机数与环比变化(自行计算),点出趋势方向(连续增长/回落/新高)。

# 四、平台格局
近半年各平台商机数与占比;若主导平台发生切换,描述切换方向。切换原因可推测,但必须标注「(推测)」。

# 五、机箱形态
近半年各机箱形态占比。

# 六、半年业务 TOP5
近半年销售人员商机数前五。

# 七、近期重点商机
列出提供的近期重点商机(客户/平台/机箱/台数/状态)。

# 八、关键洞察
用 ✅⚠️🔥📊 标注 3-5 条:增长信号、风险信号、结构变化、值得跟进的重点。归因性结论标注「(推测/待核实)」。

要求:只使用提供的数据;占比与环比自行计算;未提供的信息(如具体成交价)不要编造。`,
}

const activeTab = ref('assistant')
const loading = ref(true)
const saving = ref(false)
const assistantConfig = ref({ ...DEFAULT_ASSISTANT_CONFIG })
const llmConfig = ref({ ...DEFAULT_LLM_CONFIG })
const trendConfig = ref({ ...DEFAULT_TREND_CONFIG })

async function loadConfig() {
  loading.value = true
  try {
    const [assistantRes, llmRes, trendRes] = await Promise.all([
      axios.get('/api/system-config/ai_assistant_config/value'),
      axios.get('/api/system-config/llm_config/value'),
      axios.get('/api/system-config/ai_trend_analysis/value'),
    ])
    if (assistantRes.data.value) {
      assistantConfig.value = { ...DEFAULT_ASSISTANT_CONFIG, ...assistantRes.data.value }
    }
    if (llmRes.data.value) {
      llmConfig.value = { ...DEFAULT_LLM_CONFIG, ...llmRes.data.value }
    }
    if (trendRes.data.value) {
      trendConfig.value = { ...DEFAULT_TREND_CONFIG, ...trendRes.data.value }
    }
  } catch (err) {
    console.error('加载 AI 设置失败:', err)
    message.error('加载设置失败')
  } finally {
    loading.value = false
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

async function handleSaveTrend() {
  saving.value = true
  try {
    await axios.put('/api/system-config/ai_trend_analysis', {
      value: trendConfig.value,
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

function handleResetTrend() {
  trendConfig.value = { ...DEFAULT_TREND_CONFIG }
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