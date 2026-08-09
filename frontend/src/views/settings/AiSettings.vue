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
            <h4 class="section-title">
              启用 AI 引擎
              <span class="section-hint">统一开关：关闭后所有 AI 能力（需求分析抽取/方案助手/趋势分析）走规则或停用，不调用大模型</span>
            </h4>
            <div class="form-row">
              <label class="form-label">启用 AI</label>
              <div class="form-control">
                <a-switch v-model:checked="llmConfig.enabled" />
                <span class="form-hint">{{ llmConfig.enabled ? '已启用（大模型介入理解类环节，选件/算价仍由规则确定性完成）' : '已关闭（系统全规则运行，不依赖大模型）' }}</span>
              </div>
            </div>
          </div>

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
              <div class="form-control" style="flex-direction: column; align-items: flex-start; gap: 6px;">
                <div style="display: flex; gap: 8px; width: 100%; flex-wrap: wrap; align-items: center;">
                  <a-auto-complete
                    v-model:value="llmConfig.model"
                    :options="modelOptions"
                    :filter-option="filterModel"
                    placeholder="模型 id，可点「拉取模型列表」选取"
                    style="width: 280px"
                  />
                  <a-button size="small" :loading="fetchingModels" @click="handleFetchModels">拉取模型列表</a-button>
                </div>
                <span class="form-hint">
                  <template v-if="modelOptions.length">已拉取 {{ modelOptions.length }} 个可用模型，可在下拉中选择或直接输入 id</template>
                  <template v-else>留空使用 .env 的 LLM_MODEL；点「拉取模型列表」从当前端点获取可选 id</template>
                </span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">温度</label>
              <div class="form-control">
                <a-slider v-model:value="llmConfig.temperature" :min="0" :max="2" :step="0.1" style="width: 160px" />
                <span class="form-hint">{{ llmConfig.temperature }} · 控制随机性:低更稳准(数据/报告建议 0.3~0.5),高越发散(头脑风暴用)</span>
              </div>
            </div>

            <div class="form-row">
              <label class="form-label">最大 Tokens</label>
              <div class="form-control">
                <a-input-number v-model:value="llmConfig.max_tokens" :min="100" :max="32000" :step="100" style="width: 140px" />
                <span class="form-hint">reasoning(思考)类模型的思考也占此预算,建议 ≥ 8000</span>
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
            <a-button :loading="testing" @click="handleTestConnection">测试连接</a-button>
            <a-button @click="handleResetLlm">恢复默认</a-button>
            <span v-if="testResult" class="test-result" :class="testResult.success ? 'test-ok' : 'test-fail'">
              {{ testResult.success ? '✅' : '❌' }} {{ testResult.message }}
            </span>
          </div>
        </a-spin>
      </a-tab-pane>

      <!-- 会话记录（AI 设置·管理页） -->
      <a-tab-pane key="threads" tab="会话记录">
        <a-spin :spinning="threadsLoading">
          <div class="threads-wrap">
            <div class="threads-head">
              <div>
                <h4 class="section-title">会话记录</h4>
                <div class="thread-stats">
                  <span>总 {{ threads.length }}</span>
                  <span>正常 {{ activeCount }}</span>
                  <span>回收站 {{ trashCount }}</span>
                  <span>消息 {{ msgTotal }}</span>
                </div>
              </div>
              <div class="threads-head-right">
                <a-button size="small" @click="loadThreads">刷新</a-button>
              </div>
            </div>

            <a-radio-group v-model:value="trashView" button-style="solid" size="small" style="margin: 10px 0">
              <a-radio-button :value="false">正常会话</a-radio-button>
              <a-radio-button :value="true">回收站（{{ trashCount }}）</a-radio-button>
            </a-radio-group>

            <!-- 正常会话列表 -->
            <template v-if="!trashView">
              <div class="threads-ops">
                <span class="threads-ops-tip">本列表 {{ activeThreads.length }} 个（空会话 {{ activeEmptyCount }}）</span>
                <a-popconfirm
                  :title="`一键彻底删除 ${activeEmptyCount} 个空会话（0 消息，硬删除不可恢复）？`"
                  @confirm="cleanupEmptyThreads"
                >
                  <a-button size="small" danger :disabled="!activeEmptyCount">一键清理空会话</a-button>
                </a-popconfirm>
                <span v-if="activeSelected.length" class="threads-ops-tip">已选 {{ activeSelected.length }} 个</span>
                <a-popconfirm
                  :title="`把选中的 ${activeSelected.length} 个会话移入回收站（其中 ${selectedEmptyCount} 个无消息）？可在回收站恢复或彻底清除`"
                  @confirm="batchDelete"
                >
                  <a-button size="small" danger :disabled="!activeSelected.length">批量删除（进回收站）</a-button>
                </a-popconfirm>
              </div>
              <a-table
                :data-source="activeThreads"
                :columns="threadColumns"
                :pagination="activePagination"
                @change="onActiveTableChange"
                size="small"
                row-key="thread_id"
                :scroll="{ x: 820 }"
                :row-selection="{ selectedRowKeys: activeSelected, onChange: (k: any) => { activeSelected = k } }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'title'">
                    <span class="thread-title">{{ record.title || '(未命名)' }}</span>
                  </template>
                  <template v-else-if="column.key === 'msg_count'">
                    <span :class="{ 'thread-msg-empty': !(record.msg_count || 0) }">
                      {{ record.msg_count || 0 }}{{ !(record.msg_count || 0) ? '（空）' : '' }}
                    </span>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-space>
                      <a-button size="small" @click="viewThread(record)">查看</a-button>
                      <a-popconfirm title="删除后进回收站，可在回收站恢复或彻底清除？" @confirm="softDeleteThread(record)">
                        <a-button size="small" danger>删除</a-button>
                      </a-popconfirm>
                    </a-space>
                  </template>
                </template>
              </a-table>
            </template>

            <!-- 回收站列表（独立入口） -->
            <template v-else>
              <div class="threads-ops">
                <span v-if="trashSelected.length" class="threads-ops-tip">已选 {{ trashSelected.length }} 个</span>
                <a-button size="small" :disabled="!trashSelected.length" @click="batchRestore">批量恢复</a-button>
                <a-popconfirm :title="`彻底清除选中的 ${trashSelected.length} 个会话（消息+状态一起删除，不可恢复）？`" @confirm="batchPurge">
                  <a-button size="small" danger :disabled="!trashSelected.length">批量彻底清除</a-button>
                </a-popconfirm>
              </div>
              <a-table
                :data-source="trashThreads"
                :columns="trashColumns"
                :pagination="trashPagination"
                @change="onTrashTableChange"
                size="small"
                row-key="thread_id"
                :scroll="{ x: 900 }"
                :row-selection="{ selectedRowKeys: trashSelected, onChange: (k: any) => { trashSelected = k } }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'title'">
                    <span class="thread-title">{{ record.title || '(未命名)' }}</span>
                  </template>
                  <template v-else-if="column.key === 'msg_count'">
                    <span :class="{ 'thread-msg-empty': !(record.msg_count || 0) }">
                      {{ record.msg_count || 0 }}{{ !(record.msg_count || 0) ? '（空）' : '' }}
                    </span>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-space>
                      <a-button size="small" @click="viewThread(record)">查看</a-button>
                      <a-button size="small" type="primary" ghost @click="restoreThread(record)">恢复</a-button>
                      <a-popconfirm title="彻底删除该会话（消息+状态一起清除，不可恢复）？" @confirm="purgeThread(record)">
                        <a-button size="small" danger>彻底清除</a-button>
                      </a-popconfirm>
                    </a-space>
                  </template>
                </template>
              </a-table>
            </template>

            <div class="form-section" style="margin-top: 20px">
              <h4 class="section-title">历史数据清理</h4>
              <div class="form-row">
                <label class="form-label">LLM 调用记录</label>
                <div class="form-control">
                  <a-input-number v-model:value="traceKeepDays" :min="0" :max="365" style="width:120px" />
                  <a-button size="small" @click="cleanupTrace">清理更早的记录</a-button>
                  <span class="form-hint">只保留最近 N 天（0=清空全部），删除不可恢复</span>
                </div>
              </div>
              <div class="form-row">
                <label class="form-label">需求反馈样本</label>
                <div class="form-control">
                  <a-input-number v-model:value="sampleKeepN" :min="0" :max="10000" style="width:120px" />
                  <a-button size="small" @click="cleanupSamples">清理多余的样本</a-button>
                  <span class="form-hint">保留最近 N 条（0=清空全部），删除不可恢复</span>
                </div>
              </div>
            </div>
          </div>
        </a-spin>
      </a-tab-pane>

    </a-tabs>

    <!-- 查看会话消息 -->
    <a-modal v-model:open="viewOpen" :title="`会话记录：${viewThreadTitle}`" :footer="null" width="680">
      <div class="thread-msgs">
        <div v-for="m in viewMessages" :key="m.message_id" class="thread-msg" :class="`role-${m.role}`">
          <div class="thread-msg-head">
            <span class="thread-msg-role">{{ m.role === 'user' ? '用户' : m.role === 'assistant' ? '助手' : '系统' }}</span>
            <span class="thread-msg-meta">{{ m.kind || 'text' }} · {{ m.created_at }}</span>
          </div>
          <pre class="thread-msg-content">{{ m.content }}</pre>
        </div>
        <a-empty v-if="!viewMessages.length" description="无消息" />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import axios from 'axios'
import { assistantApi, type AssistantThread, type AssistantMessage } from '@/api/assistant'

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
  enabled: true,
  base_url: '',
  api_key: '',
  model: '',
  system_prompt: '你是 CPQ 平台的「方案助手」,辅助销售/FAE 做服务器配置与报价。用户当前所在页面的业务上下文会以「当前上下文」形式提供给你,作答时优先基于它。要求:1) 用中文回复;2) 对料号价格、库存、具体型号编号等易变信息,不要编造——不确定时请用户在配置页确认或查料号库;3) 回答简洁、分点。',
  temperature: 0.7,
  max_tokens: 8000,
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

// 模型拉取 / 连接测试（API 设置 tab）
const modelOptions = ref<{ value: string; label: string }[]>([])
const fetchingModels = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)
const filterModel = (input: string, option: { value: string }) =>
  option.value.toLowerCase().includes(input.toLowerCase())

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
  modelOptions.value = []
  testResult.value = null
  message.info('已恢复默认，请点击保存生效')
}

// 拉取当前端点（base_url + api_key）下的可用模型 id 列表，填入下拉
async function handleFetchModels() {
  if (!llmConfig.value.api_key) {
    message.warning('请先填写 API Key')
    return
  }
  fetchingModels.value = true
  testResult.value = null
  try {
    const { data } = await axios.post('/api/system-config/llm_config/models', {
      base_url: llmConfig.value.base_url,
      api_key: llmConfig.value.api_key,
      model: llmConfig.value.model,
    })
    if (data.success) {
      modelOptions.value = data.models.map((id: string) => ({ value: id, label: id }))
      message.success(`已拉取 ${data.models.length} 个模型`)
    } else {
      message.error(data.message || '拉取失败')
    }
  } catch (err) {
    console.error('拉取模型失败:', err)
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '网络错误'
    message.error('拉取失败：' + detail)
  } finally {
    fetchingModels.value = false
  }
}

// 用表单当前值（含未保存）实测一次 chat，展示真实成功/失败与错误
async function handleTestConnection() {
  testing.value = true
  try {
    const { data } = await axios.post('/api/system-config/llm_config/test', {
      base_url: llmConfig.value.base_url,
      api_key: llmConfig.value.api_key,
      model: llmConfig.value.model,
    })
    testResult.value = { success: data.success, message: data.message }
    if (data.success) message.success(data.message)
    else message.error(data.message)
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '请求失败'
    testResult.value = { success: false, message: detail }
    message.error(detail)
  } finally {
    testing.value = false
  }
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

// ── 会话记录（AI 设置·管理页）──
const threads = ref<AssistantThread[]>([])
const threadsLoading = ref(false)
const trashView = ref(false)          // false=正常会话 / true=回收站
const activePage = ref(1)
const activePageSize = ref(10)
const trashPage = ref(1)
const trashPageSize = ref(10)
const activePagination = computed(() => ({
  current: activePage.value, pageSize: activePageSize.value, total: activeThreads.value.length,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100'],
}))
const trashPagination = computed(() => ({
  current: trashPage.value, pageSize: trashPageSize.value, total: trashThreads.value.length,
  showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
  pageSizeOptions: ['10', '20', '50', '100'],
}))
function onActiveTableChange(pag: any) {
  activePage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== activePageSize.value) activePageSize.value = pag.pageSize
}
function onTrashTableChange(pag: any) {
  trashPage.value = pag.current || 1
  if (pag.pageSize && pag.pageSize !== trashPageSize.value) trashPageSize.value = pag.pageSize
}
const activeSelected = ref<string[]>([])
const trashSelected = ref<string[]>([])
const viewOpen = ref(false)
const viewThreadTitle = ref('')
const viewMessages = ref<AssistantMessage[]>([])
const traceKeepDays = ref(30)
const sampleKeepN = ref(0)

const trashCount = computed(() => threads.value.filter((t) => t.deleted_at).length)
const activeCount = computed(() => threads.value.length - trashCount.value)
const msgTotal = computed(() => threads.value.reduce((a, t) => a + (t.msg_count || 0), 0))
const activeThreads = computed(() => threads.value.filter((t) => !t.deleted_at))
const activeEmptyCount = computed(() => activeThreads.value.filter((t) => !(t.msg_count || 0)).length)
const selectedActiveThreads = computed(() => activeThreads.value.filter((t) => activeSelected.value.includes(t.thread_id)))
const selectedEmptyCount = computed(() => selectedActiveThreads.value.filter((t) => !(t.msg_count || 0)).length)
const trashThreads = computed(() => threads.value.filter((t) => !!t.deleted_at))
const threadColumns = [
  { title: '标题', key: 'title', width: 220 },
  { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 150 },
  { title: '消息数', dataIndex: 'msg_count', key: 'msg_count', width: 90 },
  { title: '最后活跃', dataIndex: 'updated_at', key: 'updated_at', width: 170 },
  { title: '操作', key: 'action', width: 150 },
]
const trashColumns = [
  { title: '标题', key: 'title', width: 220 },
  { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 150 },
  { title: '消息数', dataIndex: 'msg_count', key: 'msg_count', width: 90 },
  { title: '删除时间', dataIndex: 'deleted_at', key: 'deleted_at', width: 170 },
  { title: '操作', key: 'action', width: 220 },
]

async function loadThreads() {
  threadsLoading.value = true
  activeSelected.value = []
  trashSelected.value = []
  try {
    threads.value = await assistantApi.threads.listAll()
  } catch (err) {
    console.error('加载会话失败:', err)
    message.error('加载会话失败')
  } finally {
    threadsLoading.value = false
  }
}
async function viewThread(t: AssistantThread) {
  viewThreadTitle.value = t.title || t.thread_id
  viewMessages.value = []
  viewOpen.value = true
  try {
    viewMessages.value = await assistantApi.threads.messages(t.thread_id)
  } catch (err) {
    console.error('加载消息失败:', err)
    message.error('加载消息失败')
  }
}
async function restoreThread(t: AssistantThread) {
  try {
    await assistantApi.threads.restore(t.thread_id)
    message.success('已恢复')
    loadThreads()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '恢复失败')
  }
}
async function softDeleteThread(t: AssistantThread) {
  try {
    await assistantApi.threads.remove(t.thread_id)
    message.success('已移入回收站')
    loadThreads()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '删除失败')
  }
}
async function purgeThread(t: AssistantThread) {
  try {
    await assistantApi.threads.purge(t.thread_id)
    message.success('已彻底清除')
    loadThreads()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清除失败')
  }
}
async function cleanupEmptyThreads() {
  try {
    const deleted = await assistantApi.threads.cleanupEmptyThreads()
    message.success(`已彻底清除 ${deleted} 个空会话`)
    loadThreads()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清理失败')
  }
}
async function batchDelete() {
  if (!activeSelected.value.length) return
  for (const id of activeSelected.value) {
    try { await assistantApi.threads.remove(id) } catch (e) { /* 单条失败继续 */ }
  }
  message.success(`已把 ${activeSelected.value.length} 个会话移入回收站`)
  loadThreads()
}
async function batchRestore() {
  if (!trashSelected.value.length) return
  for (const id of trashSelected.value) {
    try { await assistantApi.threads.restore(id) } catch (e) { /* 单条失败继续 */ }
  }
  message.success(`已恢复 ${trashSelected.value.length} 个会话`)
  loadThreads()
}
async function batchPurge() {
  if (!trashSelected.value.length) return
  for (const id of trashSelected.value) {
    try { await assistantApi.threads.purge(id) } catch (e) { /* 单条失败继续 */ }
  }
  message.success(`已彻底清除 ${trashSelected.value.length} 个会话`)
  loadThreads()
}
async function cleanupTrace() {
  try {
    const r = await axios.post('/api/assistant/admin/cleanup/trace', { keep_days: traceKeepDays.value })
    message.success(`已清理 ${r.data?.deleted ?? 0} 条 LLM 调用记录`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清理失败')
  }
}
async function cleanupSamples() {
  try {
    const r = await axios.post('/api/assistant/admin/cleanup/samples', { keep_n: sampleKeepN.value })
    message.success(`已清理 ${r.data?.deleted ?? 0} 条反馈样本`)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清理失败')
  }
}
watch(activeTab, (k) => { if (k === 'threads') loadThreads() })

onMounted(loadConfig)
</script>

<style scoped>
.ai-settings-page {
  padding: 24px;
  max-width: 1100px;
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

.test-result {
  font-size: 12px;
  line-height: 1.4;
}

.test-result.test-ok {
  color: var(--cpq-success, #52c41a);
}

.test-result.test-fail {
  color: var(--cpq-error, #ff4d4f);
}
.threads-wrap { width: 100%; }
.threads-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.threads-head-right { display: flex; align-items: center; gap: 10px; }
.thread-stats { display: flex; align-items: center; gap: 16px; color: var(--cpq-text-secondary); font-size: 13px; margin-top: 6px; }
.threads-ops { display: flex; align-items: center; gap: 10px; margin: 8px 0; }
.threads-ops-tip { font-size: 12px; color: var(--cpq-text-muted); }
.thread-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; display: inline-block; vertical-align: bottom; }
.thread-msg-empty { color: var(--cpq-text-muted); }
.thread-msgs { max-height: 60vh; overflow: auto; display: flex; flex-direction: column; gap: 8px; }
.thread-msg { border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; padding: 8px 10px; }
.thread-msg.role-user { border-left: 3px solid var(--cpq-accent-primary); }
.thread-msg.role-assistant { border-left: 3px solid var(--cpq-color-success); }
.thread-msg-head { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--cpq-text-muted); }
.thread-msg-content { margin: 4px 0 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; font-family: inherit; color: var(--cpq-text-primary); }
</style>