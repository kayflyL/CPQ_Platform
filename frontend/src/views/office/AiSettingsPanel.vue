<template>
  <div class="ai-settings-page" :class="{ 'is-embedded': embedded, 'is-embedded-section': embedded && section !== 'all' }">
    <div v-if="!embedded" class="page-header">
      <h2>AI 设置</h2>
      <p class="subtitle">配置方案助手行为、数据查询与模型连接</p>
    </div>

    <a-alert v-if="!embedded" message="AI 同事配置已迁移到 AI 办公室 → Manage Teams" type="info" show-icon style="margin-bottom: 16px">
  <template #action>
    <a-button type="link" @click="router.push('/ai-office')">前往 AI 办公室</a-button>
  </template>
</a-alert>
<a-tabs v-model:activeKey="activeTab" class="ai-settings-outer-tabs">
<!-- 公共设置 -->
      <a-tab-pane v-if="showModel || showTools" key="public" tab="公共设置">
        <a-tabs v-model:activeKey="publicTab">
      <!-- 模型与连接 -->
      <a-tab-pane v-if="showModel" key="api" tab="模型与连接">
        <a-spin :spinning="loading">
          <div class="form-section">
            <h4 class="section-title">
              启用 AI 引擎
            </h4>
            <div class="form-row">
              <label class="form-label">启用 AI</label>
              <div class="form-control">
                <a-switch v-model:checked="llmConfig.enabled" />
                <span class="form-hint">{{ llmConfig.enabled ? '已启用' : '已关闭' }}</span>
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
      <a-tab-pane v-if="showModel" key="capabilities" tab="模型能力档案">
        <a-spin :spinning="capabilityLoading">
          <div class="form-section">
            <h4 class="section-title">
              模型能力档案
              <span class="section-hint">控制 JSON Mode / 原生工具 / Reasoning 策略；未识别模型走保守默认</span>
            </h4>
            <div class="form-row">
              <label class="form-label">当前模型</label>
              <div class="form-control">
                <a-tag color="blue">{{ llmConfig.model || '未配置' }}</a-tag>
              </div>
            </div>
            <div v-for="field in capabilityFields" :key="field.key" class="form-row">
              <label class="form-label">{{ field.label }}</label>
              <div class="form-control" style="flex-direction: column; align-items: flex-start; gap: 6px;">
                <a-radio-group v-model:value="capabilityForm[field.key]" button-style="solid" size="small">
                  <a-radio-button value="auto">自动（内置）</a-radio-button>
                  <a-radio-button value="on">开</a-radio-button>
                  <a-radio-button value="off">关</a-radio-button>
                </a-radio-group>
                <span class="form-hint">{{ field.hint }}</span>
              </div>
            </div>
          </div>
          <div class="form-actions">
            <a-button type="primary" :loading="capabilitySaving" @click="handleSaveCapabilities">保存能力档案</a-button>
            <a-button :loading="capabilityProbing" @click="handleProbeCapabilities">能力探测</a-button>
            <a-button @click="handleResetCapabilities">恢复内置默认</a-button>
            <span v-if="capabilityProbeResult" class="test-result" :class="capabilityProbeResult.success ? 'test-ok' : 'test-fail'">
              {{ capabilityProbeResult.success ? '✅' : '❌' }} {{ capabilityProbeMessage }}
            </span>
          </div>
          <a-alert v-if="capabilityBuiltin" type="info" show-icon style="margin-top: 12px">
            <template #message>
              内置档案：JSON Mode {{ capabilityBuiltin.supports_json_mode ? '支持' : '不支持' }} · 原生工具 {{ capabilityBuiltin.supports_native_tools ? '支持' : '不支持' }} · Reasoning {{ capabilityBuiltin.reasoning_model ? '是' : '否' }}
            </template>
          </a-alert>
        </a-spin>
      </a-tab-pane>
      <a-tab-pane v-if="showTools" key="tools" tab="AI 工具目录">
        <a-spin :spinning="toolsLoading">
          <div class="form-section">
            <h4 class="section-title">
              AI 工具目录
              <span class="section-hint">全系统 LLM 工具 · 唯一注册表 agent_tools.py（只读）</span>
            </h4>
            <a-table
              :data-source="tools"
              :columns="toolColumns"
              :loading="toolsLoading"
              :pagination="false"
              size="small"
              row-key="name"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'category'">
                  <a-tag :color="record.category === 'data' ? 'blue' : 'purple'">{{ categoryLabel(record.category) }}</a-tag>
                </template>
                <template v-else-if="column.key === 'parameters'">
                  <span class="tool-params">{{ summarizeParams(record.parameters) }}</span>
                </template>
                <template v-else-if="column.key === 'default_enabled'">
                  <a-tag :color="record.default_enabled ? 'success' : 'default'">{{ record.default_enabled ? '默认启用' : '需勾选启用' }}</a-tag>
                </template>
              </template>
            </a-table>
          </div>
        </a-spin>
      </a-tab-pane>
        </a-tabs>
      </a-tab-pane>

      <a-tab-pane v-if="showAccess" key="access" tab="账户与权限">
        <a-spin :spinning="accessRolesLoading">
          <div class="form-section">
            <h4 class="section-title">
              账户与权限
              <span class="section-hint">控制哪些系统角色可以进入 AI 办公室的 Manage Teams；具体“谁能聊哪个 AI 角色”仍在 Manage Teams → 访问权限配置</span>
            </h4>
            <a-alert
              message="开启后，该角色的用户会看到 AI 办公室右上角的 Manage Teams 按钮，并可修改 AI 办公室管理配置。"
              type="info"
              show-icon
              style="margin-bottom: 12px"
            />
            <a-table
              :data-source="accessRoles"
              :columns="accessRoleColumns"
              :loading="accessRolesLoading"
              :pagination="false"
              size="small"
              row-key="role_key"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'role_name'">
                  <span>{{ record.name }}</span>
                  <span v-if="record.role_key === 'admin'" class="role-tag">超级管理员</span>
                </template>
                <template v-else-if="column.key === 'can_manage'">
                  <span v-if="record.role_key === 'admin'">全部权限</span>
                  <a-switch
                    v-else
                    :checked="record.permissions.includes('ai.office.manage')"
                    size="small"
                    :loading="accessSavingRole === record.role_key"
                    @change="(checked: boolean) => onAiManageChange(record, checked)"
                  />
                </template>
              </template>
            </a-table>
          </div>
        </a-spin>
      </a-tab-pane>

      <!-- 会话记录（AI 设置·管理页） -->
      <a-tab-pane v-if="showThreads" key="threads" tab="会话记录">
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

            <div class="threads-filters">
              <a-select v-model:value="threadKindFilter" allow-clear placeholder="会话类型" style="width: 150px">
                <a-select-option value="assistant">方案助手</a-select-option>
                <a-select-option value="office_colleague">AI Office</a-select-option>
              </a-select>
              <a-select v-model:value="roleKeyFilter" allow-clear show-search placeholder="AI 角色" style="width: 180px" :options="colleagueOptions" />
              <a-input v-model:value="keywordFilter" allow-clear placeholder="标题 / 会话 ID" style="width: 200px" @press-enter="loadThreads" />
              <a-button size="small" @click="loadThreads">筛选</a-button>
              <a-button size="small" @click="resetThreadFilters">重置</a-button>
            </div>

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
                  <template v-if="column.key === 'thread_kind'">
                    <a-tag :color="record.thread_kind === 'office_colleague' ? 'purple' : 'blue'">
                      {{ record.thread_kind === 'office_colleague' ? 'AI Office' : '方案助手' }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'colleague_name'">
                    <span>{{ record.colleague_name || record.colleague_role_key || '—' }}</span>
                  </template>
                  <template v-else-if="column.key === 'title'">
                    <span class="thread-title">{{ record.title || '(未命名)' }}</span>
                  </template>
                  <template v-else-if="column.key === 'entry_point'">
                    <span>{{ entryPointLabel(record.entry_point) }}</span>
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
                  <template v-if="column.key === 'thread_kind'">
                    <a-tag :color="record.thread_kind === 'office_colleague' ? 'purple' : 'blue'">
                      {{ record.thread_kind === 'office_colleague' ? 'AI Office' : '方案助手' }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'colleague_name'">
                    <span>{{ record.colleague_name || record.colleague_role_key || '—' }}</span>
                  </template>
                  <template v-else-if="column.key === 'title'">
                    <span class="thread-title">{{ record.title || '(未命名)' }}</span>
                  </template>
                  <template v-else-if="column.key === 'entry_point'">
                    <span>{{ entryPointLabel(record.entry_point) }}</span>
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

      <!-- 审计 / 绩效（AI 同事 LLM 与工具调用 trace） -->
      <a-tab-pane v-if="showAudit" key="audit" tab="审计 / 绩效">
        <a-spin :spinning="auditLoading">
          <div class="form-section">
            <h4 class="section-title">AI 同事调用指标</h4>
            <div class="audit-kpis">
              <div class="audit-kpi">
                <span>LLM 调用</span>
                <strong>{{ audit.calls }}</strong>
              </div>
              <div class="audit-kpi">
                <span>工具调用</span>
                <strong>{{ audit.tool_calls }}</strong>
              </div>
              <div class="audit-kpi">
                <span>平均耗时</span>
                <strong>{{ audit.avg_duration_ms }}ms</strong>
              </div>
              <div class="audit-kpi">
                <span>成功率</span>
                <strong>{{ Math.round(audit.success_rate * 100) }}%</strong>
              </div>
            </div>
          </div>

          <div class="form-section">
            <h4 class="section-title">最近调用</h4>
            <a-table
              :data-source="audit.last_calls"
              :columns="auditColumns"
              :loading="auditLoading"
              :pagination="{ pageSize: 20 }"
              size="small"
              row-key="id"
            />
          </div>
        </a-spin>
      </a-tab-pane>

    </a-tabs>

    <!-- 查看会话消息 -->
    <a-modal v-model:open="viewOpen" :title="`会话记录：${viewThreadTitle}`" :footer="null" width="720">
      <div v-if="viewThreadMeta" class="thread-meta-line">
        <span>{{ viewThreadMeta.thread_kind === 'office_colleague' ? 'AI Office' : '方案助手' }}</span>
        <span>{{ viewThreadMeta.colleague_name || viewThreadMeta.colleague_role_key || '总助手' }}</span>
        <span>{{ viewThreadMeta.created_by_name || viewThreadMeta.created_by || '未知用户' }}</span>
        <span>{{ viewThreadMeta.created_at }}</span>
      </div>
      <div class="thread-msgs">
        <div v-for="m in viewMessages" :key="m.message_id" class="thread-msg" :class="`role-${m.role}`">
          <div class="thread-msg-head">
            <span class="thread-msg-role">{{ m.role === 'user' ? '用户' : m.role === 'assistant' ? (m.colleague_role_key || '助手') : '系统' }}</span>
            <span class="thread-msg-meta">{{ m.kind || 'text' }} · {{ m.colleague_role_key || 'assistant' }} · {{ m.created_at }}</span>
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
import { useRouter } from 'vue-router'
import { assistantApi, type AssistantThread, type AssistantMessage, type AssistantToolInfo } from '@/api/assistant'
import { rbacApi, type RoleItem } from '@/api/rbac'

const router = useRouter()

const props = defineProps<{
  embedded?: boolean
  section?: 'model' | 'tools' | 'access' | 'threads' | 'audit' | 'all'
}>()

const embedded = computed(() => props.embedded === true)
const section = computed(() => props.section || 'all')
const showModel = computed(() => section.value === 'all' || section.value === 'model')
const showTools = computed(() => section.value === 'all' || section.value === 'tools')
const showAccess = computed(() => section.value === 'all' || section.value === 'access')
const showThreads = computed(() => section.value === 'all' || section.value === 'threads')
const showAudit = computed(() => section.value === 'all' || section.value === 'audit')

const DEFAULT_LLM_CONFIG = {
  enabled: true,
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
  max_tokens: 8000,
  capabilities_override: {} as Record<string, Record<string, boolean>>,
}

const activeTab = ref(section.value === 'access' ? 'access' : section.value === 'threads' ? 'threads' : section.value === 'audit' ? 'audit' : 'public')
const accessRoles = ref<RoleItem[]>([])
const accessRolesLoading = ref(false)
const accessSavingRole = ref<string | null>(null)
const accessRoleColumns = [
  { title: '角色 key', dataIndex: 'role_key', key: 'role_key', width: 160 },
  { title: '角色名称', dataIndex: 'name', key: 'role_name' },
  { title: 'AI 办公室管理', key: 'can_manage', width: 180 },
]

async function loadAccessRoles() {
  accessRolesLoading.value = true
  try {
    accessRoles.value = await rbacApi.roles.list()
  } catch {
    message.error('加载角色失败')
  } finally {
    accessRolesLoading.value = false
  }
}

async function onAiManageChange(role: RoleItem, checked: boolean) {
  accessSavingRole.value = role.role_key
  try {
    const next = new Set(role.permissions || [])
    if (checked) next.add('ai.office.manage')
    else next.delete('ai.office.manage')
    await rbacApi.roles.update(role.role_key, { permissions: Array.from(next) })
    role.permissions = Array.from(next)
    message.success(`${role.name || role.role_key} 已${checked ? '开启' : '关闭'} AI 办公室管理`)
  } catch {
    message.error('保存失败')
  } finally {
    accessSavingRole.value = null
  }
}
const publicTab = ref(section.value === 'tools' ? 'tools' : 'api')
const loading = ref(true)
const saving = ref(false)
const llmConfig = ref({ ...DEFAULT_LLM_CONFIG })

// 模型拉取 / 连接测试（模型与连接 tab）
const modelOptions = ref<{ value: string; label: string }[]>([])
const fetchingModels = ref(false)
const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

// ── 模型能力档案（模型与接入 → 模型能力档案 tab）──
const capabilityFields = [
  { key: 'supports_json_mode', label: 'JSON Mode（response_format=json_object）', hint: '关闭后走「提示词要求 JSON + 解析器」，适配不支持 JSON mode 的模型' },
  { key: 'supports_native_tools', label: '原生工具调用（function calling）', hint: '关闭后 ReAct 直接走文本协议，避免原生 tools 不稳定' },
  { key: 'reasoning_model', label: 'Reasoning 模型', hint: '思考预算会占用 max_tokens；开启后空正文会按 reasoning 截断诊断' },
]
const capabilityLoading = ref(false)
const capabilitySaving = ref(false)
const capabilityProbing = ref(false)
const capabilityProbeResult = ref<{ success: boolean; message?: string; supports_json_mode?: boolean; supports_native_tools?: boolean; reasoning_model?: boolean } | null>(null)
const capabilityBuiltin = ref<Record<string, boolean> | null>(null)
const capabilityForm = ref<Record<string, 'auto' | 'on' | 'off'>>({})
const capabilityProbeMessage = computed(() => {
  const r = capabilityProbeResult.value
  if (!r) return ''
  if (!r.success) return r.message || '探测失败'
  return `JSON Mode ${r.supports_json_mode ? '支持' : '不支持'} · 原生工具 ${r.supports_native_tools ? '支持' : '不支持'}`
})
const filterModel = (input: string, option: { value: string }) =>
  option.value.toLowerCase().includes(input.toLowerCase())

function normalizeLlmConfig() {
  delete (llmConfig.value as any).system_prompt
}

async function loadConfig() {
  loading.value = true
  try {
    const llmRes = await axios.get('/api/system-config/llm_config/value')
    if (llmRes.data.value) {
      llmConfig.value = { ...DEFAULT_LLM_CONFIG, ...llmRes.data.value }
      normalizeLlmConfig()
    }
  } catch (err) {
    console.error('加载 AI 设置失败:', err)
    message.error('加载设置失败')
  } finally {
    loading.value = false
  }
}

async function handleSaveLlm() {
  saving.value = true
  try {
    normalizeLlmConfig()
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

async function loadCapabilities() {
  capabilityLoading.value = true
  try {
    const { data } = await axios.get('/api/system-config/llm_config/capabilities', {
      params: { model: llmConfig.value.model || undefined },
    })
    if (data.success) {
      capabilityBuiltin.value = data.builtin || null
      const override = data.override || {}
      for (const field of capabilityFields) {
        capabilityForm.value[field.key] = field.key in override
          ? (override[field.key] ? 'on' : 'off')
          : 'auto'
      }
    } else {
      message.error(data.message || '加载能力档案失败')
    }
  } catch (err) {
    console.error('加载能力档案失败:', err)
    message.error('加载能力档案失败')
  } finally {
    capabilityLoading.value = false
  }
}

async function handleSaveCapabilities() {
  const model = llmConfig.value.model
  if (!model) {
    message.warning('请先在「模型与连接」页选择模型')
    return
  }
  const override: Record<string, boolean> = {}
  for (const field of capabilityFields) {
    const value = capabilityForm.value[field.key]
    if (value === 'on') override[field.key] = true
    else if (value === 'off') override[field.key] = false
  }
  const capabilitiesOverride = (llmConfig.value as any).capabilities_override || {}
  if (Object.keys(override).length) {
    capabilitiesOverride[model] = override
  } else {
    delete capabilitiesOverride[model]
  }
  llmConfig.value = { ...llmConfig.value, capabilities_override: capabilitiesOverride }
  capabilitySaving.value = true
  try {
    normalizeLlmConfig()
    await axios.put('/api/system-config/llm_config', {
      value: llmConfig.value,
      type: 'json',
    })
    message.success('能力档案已保存')
    await loadCapabilities()
  } catch (err) {
    console.error('保存能力档案失败:', err)
    message.error('保存失败')
  } finally {
    capabilitySaving.value = false
  }
}

async function handleProbeCapabilities() {
  if (!llmConfig.value.api_key || !llmConfig.value.model) {
    message.warning('请先填写 API Key 和模型')
    return
  }
  capabilityProbing.value = true
  capabilityProbeResult.value = null
  try {
    const { data } = await axios.post('/api/system-config/llm_config/probe', {
      base_url: llmConfig.value.base_url,
      api_key: llmConfig.value.api_key,
      model: llmConfig.value.model,
    })
    capabilityProbeResult.value = data
    if (data.success) {
      capabilityForm.value.supports_json_mode = data.supports_json_mode ? 'on' : 'off'
      capabilityForm.value.supports_native_tools = data.supports_native_tools ? 'on' : 'off'
      capabilityForm.value.reasoning_model = 'auto'
      message.success('探测完成，请点击保存能力档案生效')
    } else {
      message.error(data.message || '探测失败')
    }
  } catch (err) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '请求失败'
    capabilityProbeResult.value = { success: false, message: detail }
    message.error(detail)
  } finally {
    capabilityProbing.value = false
  }
}

function handleResetCapabilities() {
  for (const field of capabilityFields) {
    capabilityForm.value[field.key] = 'auto'
  }
  message.info('已恢复自动（内置），点击保存能力档案生效')
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

// ── 会话记录（AI 设置·管理页）──
const threads = ref<AssistantThread[]>([])
const threadsLoading = ref(false)
const threadKindFilter = ref<string | undefined>(undefined)
const roleKeyFilter = ref<string | undefined>(undefined)
const keywordFilter = ref('')
const colleagueOptions = ref<{ value: string; label: string }[]>([])
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
const viewThreadMeta = ref<AssistantThread | null>(null)
const viewMessages = ref<AssistantMessage[]>([])
const traceKeepDays = ref(30)
const sampleKeepN = ref(0)

// ── 审计 / 绩效（AI 同事 LLM 与工具调用 trace）──
const auditLoading = ref(false)
const audit = ref<{
  calls: number
  tool_calls: number
  avg_duration_ms: number
  success_rate: number
  by_node: any[]
  last_calls: any[]
}>({
  calls: 0,
  tool_calls: 0,
  avg_duration_ms: 0,
  success_rate: 0,
  by_node: [],
  last_calls: [],
})
const auditColumns = [
  { title: '节点 / 工具', dataIndex: 'node_type', key: 'node_type', width: 220 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: '耗时', dataIndex: 'duration_ms', key: 'duration_ms', width: 90 },
  { title: '线程', dataIndex: 'thread_id', key: 'thread_id', width: 180 },
  { title: '模型', dataIndex: 'model', key: 'model', width: 130 },
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
]
async function loadColleagueOptions() {
  try {
    const data = await assistantApi.aiColleagues.list()
    const colleagues = Array.isArray(data?.colleagues) ? data.colleagues : []
    colleagueOptions.value = colleagues
      .filter((c: any) => c?.role_key)
      .map((c: any) => ({ value: String(c.role_key), label: c.name || c.role_key }))
  } catch {
    colleagueOptions.value = []
  }
}

async function loadAudit() {
  auditLoading.value = true
  try {
    audit.value = await assistantApi.threads.audit()
  } catch (err) {
    console.error('加载 AI 同事审计数据失败:', err)
    message.error('加载审计数据失败')
  } finally {
    auditLoading.value = false
  }
}

const trashCount = computed(() => threads.value.filter((t) => t.deleted_at).length)
const activeCount = computed(() => threads.value.length - trashCount.value)
const msgTotal = computed(() => threads.value.reduce((a, t) => a + (t.msg_count || 0), 0))
const activeThreads = computed(() => threads.value.filter((t) => !t.deleted_at))
const activeEmptyCount = computed(() => activeThreads.value.filter((t) => !(t.msg_count || 0)).length)
const selectedActiveThreads = computed(() => activeThreads.value.filter((t) => activeSelected.value.includes(t.thread_id)))
const selectedEmptyCount = computed(() => selectedActiveThreads.value.filter((t) => !(t.msg_count || 0)).length)
const trashThreads = computed(() => threads.value.filter((t) => !!t.deleted_at))
const entryPointLabels: Record<string, string> = {
  portal: '门户',
  floating_assistant: '浮动助手',
  ai_office: 'AI 办公室',
  settings: 'AI 设置',
}
function entryPointLabel(value?: string) {
  return entryPointLabels[value || ''] || value || '—'
}
const threadColumns = [
  { title: '类型', key: 'thread_kind', width: 100 },
  { title: 'AI 角色', key: 'colleague_name', width: 120 },
  { title: '标题 / 最近消息', key: 'title', width: 240 },
  { title: '入口', key: 'entry_point', width: 90 },
  { title: '创建人', dataIndex: 'created_by_name', key: 'created_by_name', width: 120 },
  { title: '消息数', dataIndex: 'msg_count', key: 'msg_count', width: 80 },
  { title: '最后活跃', dataIndex: 'updated_at', key: 'updated_at', width: 170 },
  { title: '操作', key: 'action', width: 150 },
]
const trashColumns = [
  { title: '类型', key: 'thread_kind', width: 100 },
  { title: 'AI 角色', key: 'colleague_name', width: 120 },
  { title: '标题 / 最近消息', key: 'title', width: 240 },
  { title: '入口', key: 'entry_point', width: 90 },
  { title: '创建人', dataIndex: 'created_by_name', key: 'created_by_name', width: 120 },
  { title: '消息数', dataIndex: 'msg_count', key: 'msg_count', width: 80 },
  { title: '删除时间', dataIndex: 'deleted_at', key: 'deleted_at', width: 170 },
  { title: '操作', key: 'action', width: 220 },
]

function resetThreadFilters() {
  threadKindFilter.value = undefined
  roleKeyFilter.value = undefined
  keywordFilter.value = ''
  loadThreads()
}
async function loadThreads() {
  threadsLoading.value = true
  activeSelected.value = []
  trashSelected.value = []
  try {
    threads.value = await assistantApi.threads.listAll({
      thread_kind: threadKindFilter.value || undefined,
      role_key: roleKeyFilter.value || undefined,
      keyword: keywordFilter.value.trim() || undefined,
    })
  } catch (err) {
    console.error('加载会话失败:', err)
    message.error('加载会话失败')
  } finally {
    threadsLoading.value = false
  }
}
async function viewThread(t: AssistantThread) {
  const kindLabel = t.thread_kind === 'office_colleague' ? 'AI Office' : '方案助手'
  const roleLabel = t.colleague_name || t.colleague_role_key || '总助手'
  viewThreadTitle.value = `${kindLabel} · ${roleLabel} · ${t.title || t.thread_id}`
  viewThreadMeta.value = t
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
// ── AI 工具目录（只读 · 数据源 GET /api/assistant/tools ← agent_tools._TOOL_SPECS）──
const tools = ref<AssistantToolInfo[]>([])
const toolsLoading = ref(false)
const toolColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 170 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 100 },
  { title: '说明', dataIndex: 'description', key: 'description' },
  { title: '参数', dataIndex: 'parameters', key: 'parameters', width: 300 },
  { title: '默认启用', dataIndex: 'default_enabled', key: 'default_enabled', width: 100 },
]
const CATEGORY_LABELS: Record<string, string> = {
  selection: '选型决策',
  data: '数据查询',
  cost: '成本核算',
  quote: '报价生成',
}
function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || category
}
function summarizeParams(parameters: Record<string, any> | undefined): string {
  if (!parameters || !parameters.properties) return ''
  const required: string[] = Array.isArray(parameters.required) ? parameters.required : []
  return Object.entries(parameters.properties)
    .map(([key, prop]) => {
      const p = (prop || {}) as Record<string, any>
      const enums = Array.isArray(p.enum) && p.enum.length ? p.enum.join('|') : ''
      const type = p.type ? String(p.type) : ''
      return `${key}${required.includes(key) ? '' : '?'}:${enums || type || ''}`
    })
    .join('，')
}
async function loadTools() {
  toolsLoading.value = true
  try {
    tools.value = await assistantApi.tools.catalog()
  } catch (err) {
    console.error('加载 AI 工具目录失败:', err)
  } finally {
    toolsLoading.value = false
  }
}

watch(activeTab, (k) => {
  if (k === 'threads') loadThreads()
  if (k === 'audit') loadAudit()
  if (k === 'access') loadAccessRoles()
})

watch(publicTab, (k) => {
  if (k === 'capabilities') loadCapabilities()
})

watch(section, (value) => {
  if (value === 'model' || value === 'tools') {
    activeTab.value = 'public'
    publicTab.value = value === 'tools' ? 'tools' : 'api'
  } else if (value === 'access') {
    activeTab.value = 'access'
  } else if (value === 'threads') {
    activeTab.value = 'threads'
  } else if (value === 'audit') {
    activeTab.value = 'audit'
  } else {
    activeTab.value = 'public'
    publicTab.value = 'api'
  }
})

onMounted(async () => { await loadConfig(); loadCapabilities() })
onMounted(loadTools)
onMounted(loadColleagueOptions)
onMounted(loadAccessRoles)
</script>

<style scoped>
.ai-settings-page {
  padding: 24px;
  max-width: 1100px;
}

.ai-settings-page.is-embedded {
  padding: 0;
  max-width: none;
}

.ai-settings-page.is-embedded-section :deep(.ai-settings-outer-tabs > .ant-tabs-nav) {
  display: none;
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

.colleague-layout { display: flex; gap: 16px; align-items: flex-start; }
.colleague-list { width: 260px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; }
.colleague-item { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--cpq-border-secondary); border-radius: var(--cpq-radius-md); cursor: pointer; background: var(--cpq-bg-container, transparent); }
.colleague-item.active { border-color: var(--cpq-accent-primary, #1677ff); }
.colleague-avatar-wrap {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.colleague-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; display: block; }
.colleague-initial {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}
.colleague-meta { flex: 1; min-width: 0; }
.colleague-name { font-weight: 600; font-size: 14px; color: var(--cpq-text-primary); }
.colleague-role { font-size: 12px; color: var(--cpq-text-muted); }
.colleague-detail { flex: 1; min-width: 0; }

.form-section {
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-md);
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

.audit-kpis {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.audit-kpi {
  flex: 1;
  min-width: 150px;
  padding: 14px 16px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-md);
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--cpq-bg-container, transparent);
}
.audit-kpi span {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.audit-kpi strong {
  font-size: 24px;
  line-height: 1;
  color: var(--cpq-text-primary);
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
.threads-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.thread-meta-line { display: flex; flex-wrap: wrap; gap: 10px; padding: 8px 10px; margin-bottom: 10px; border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; color: var(--cpq-text-secondary); font-size: 12px; }
.thread-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; display: inline-block; vertical-align: bottom; }
.thread-msg-empty { color: var(--cpq-text-muted); }
.tool-params { font-size: 12px; color: var(--cpq-text-secondary); word-break: break-all; }
.thread-msgs { max-height: 60vh; overflow: auto; display: flex; flex-direction: column; gap: 8px; }
.thread-msg { border: 1px solid var(--cpq-overlay-w10); border-radius: 8px; padding: 8px 10px; }
.thread-msg.role-user { border-left: 3px solid var(--cpq-accent-primary); }
.thread-msg.role-assistant { border-left: 3px solid var(--cpq-color-success); }
.thread-msg-head { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; color: var(--cpq-text-muted); }
.thread-msg-content { margin: 4px 0 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; font-family: inherit; color: var(--cpq-text-primary); }
.dispatch-rule {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding: 8px;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-md);
  margin: 8px 0;
}
</style>
