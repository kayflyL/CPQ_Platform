<template>
  <Teleport :disabled="embedded || inset" to="body">
    <transition name="assistant-panel">
      <div v-if="embedded || open" class="assistant-panel" :class="{ 'assistant-panel--embedded': embedded, 'assistant-panel--inset': inset, 'ap-two-pane': showContacts, 'ap-mobile': isMobile && !embedded, 'ap-fullscreen': apFullscreen }" :style="panelStyle">
        <!-- 左栏：消息中心（原型 conv-list）：筛选签 + 房间/同事分组 + 预览/时间/未读/presence -->
        <aside
          v-if="showContacts"
          class="ap-contacts"
          :class="{ 'is-collapsed': contactsCollapsed }"
          @mousedown.stop
        >
          <div class="ap-contacts-head">
            <div class="ap-contacts-title">CPQ 配置团队</div>
            <button v-if="isMobile" type="button" class="ap-contacts-close" title="关闭团队抽屉" @click="contactsCollapsed = true">✕</button>
          </div>
          <div class="ap-contact-scroll">
            <div class="ap-cgroup">房间</div>
            <button
              v-for="r in roomThreads"
                :key="r.thread_id"
                type="button"
                class="ap-contact"
                :class="{ active: view === 'group' && currentThreadId === r.thread_id }"
                @click="openRoom(r)"
              >
                <span class="ap-contact-avatar ap-contact-avatar--group">群</span>
                <span class="ap-contact-main">
                  <span class="ap-contact-namerow">
                    <span class="ap-contact-name">{{ roomName(r) }}</span>
                    <span class="ap-contact-time">{{ fmtChatTime(r.updated_at) }}</span>
                  </span>
                  <span class="ap-contact-preview">{{ previewOf(r) }}</span>
                </span>
                <span v-if="unreadOfThread(r)" class="ap-unread-dot"></span>
              </button>
              <input
                v-if="roomCreating"
                v-model="roomNameDraft"
                class="ap-room-input"
                placeholder="房间名，回车创建"
                @keydown.enter.prevent="createRoom"
                @keydown.esc.prevent="roomCreating = false"
              />
              <button v-else type="button" class="ap-room-add" @click="roomCreating = true">＋ 新建房间</button>
            <div class="ap-cgroup">同事</div>
            <button
              v-for="c in contacts"
                :key="c.role_key"
                type="button"
                class="ap-contact"
                :class="{ active: view === 'dm' && activeRoleKey === c.role_key }"
                @click="openDm(c)"
              >
                <span class="ap-contact-avatar" :style="roleAvatarStyle(c)">
                  <img v-if="c.avatar_url" :src="c.avatar_url" alt="" />
                  <span v-else>{{ avatarInitial(c.name) }}</span>
                  <i class="ap-presence" :class="{ on: isPresenceOn(c.role_key) }"></i>
                </span>
                <span class="ap-contact-main">
                  <span class="ap-contact-namerow">
                    <span class="ap-contact-name">{{ c.name || c.role_key }}</span>
                    <span class="ap-contact-time">{{ fmtChatTime(contactThread(c.role_key)?.updated_at) }}</span>
                  </span>
                  <span class="ap-contact-preview">{{ contactPreview(c.role_key) }}</span>
                </span>
                <span v-if="contactUnread(c.role_key)" class="ap-unread-dot"></span>
              </button>
          </div>
        </aside>

        <!-- 主区：当前会话（群聊或 1:1） -->
        <div class="ap-main" @click="onMainAreaClick">
        <!-- 顶栏：仅留拖动手柄 + 团队/联系人开关（角色信息已在左侧选中行体现，去掉重复）。
             试运行预览：单线程单角色，无团队/联系人侧栏，隐藏开关（2026-09-06 用户指正） -->
        <div class="ap-header" @mousedown="startDrag">
          <button
            v-if="!props.preview"
            type="button"
            class="ap-contacts-toggle"
            :title="contactsCollapsed ? '展开团队' : '收起团队'"
            @mousedown.stop
            @click="contactsCollapsed = !contactsCollapsed"
          >
            <MenuUnfoldOutlined v-if="contactsCollapsed" />
            <MenuFoldOutlined v-else />
          </button>
          <!-- 聊天头身份区（原型 chat-head）：头像+presence、名字+私聊/房间 chip、副标 -->
          <div v-if="!props.preview" class="ap-head-id">
            <span
              class="ap-head-avatar ap-head-avatar--click"
              :class="{ 'ap-head-avatar--group': view === 'group' }"
              :style="view === 'dm' ? roleAvatarStyle(activeColleague) : undefined"
              title="查看名片"
              @click.stop="openHeadPersona($event)"
            >
              {{ view === 'group' ? '群' : avatarInitial(activeColleagueName) }}
              <i class="ap-presence" :class="{ on: isPresenceOn(view === 'group' ? 'assistant' : (activeRoleKey || '')) }"></i>
            </span>
            <div class="ap-head-main">
              <div class="ap-head-name">
                {{ view === 'group' ? (groupThread?.title?.trim() || '全员大厅') : activeColleagueName }}
                <span class="ap-head-chip">{{ view === 'group' ? '房间' : '私聊' }}</span>
              </div>
              <div class="ap-head-sub">{{ view === 'group' ? `${contacts.length} 位成员 · 可 @ 点名` : colleagueDescription(activeColleague) }}</div>
            </div>
          </div>
          <div class="ap-header-spacer"></div>
          <!-- 手机端动作组：右竖条(ap-right)在手机全屏下破坏对称,动作收进顶栏;桌面保持竖条 -->
          <div v-if="isMobile && !props.preview" class="ap-header-actions" @mousedown.stop>
            <button
              class="ap-icon-btn"
              type="button"
              title="新对话（归档当前会话）"
              :disabled="sending || running"
              @click="startNewConversation"
            >
              <PlusOutlined />
            </button>
            <button class="ap-icon-btn" type="button" title="会话记录（含归档）" @click="toggleHistory">
              <HistoryOutlined />
            </button>
            <button class="ap-icon-btn ap-close" type="button" title="收起" @click="emit('update:open', false)">
              <CloseOutlined />
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <div class="ap-messages" ref="messagesEl">
          <a-spin v-if="loading" size="small" class="ap-spin" />
          <a-empty
            v-else-if="!messages.length && !streamingText && !waitingAI"
            :image-style="{ height: '48px' }"
            :description="`和${activeColleagueName}聊聊？直接描述服务器配置需求，AI 会自动判断是否进入分析。`"
          />
          <div v-else class="ap-msg-list">
            <template v-for="m in messages" :key="m.message_id">
              <!-- 转接标记：leader 请专家进场（可见交接，而非无声换头像） -->
              <div v-if="m.kind === 'handoff'" class="ap-handoff">
                <span class="ap-handoff-line"></span>
                <span class="ap-handoff-text">{{ m.content }}</span>
                <span class="ap-handoff-line"></span>
              </div>
              <!-- 真实业务产出（需求单/BOM 方案草稿）：文本气泡 + 产出物卡片 -->
              <div v-else-if="m.kind === 'business_artifact'" class="ap-msg role-assistant ap-msg-result">
                <div class="ap-msg-head">
                  <div
                    class="ap-avatar"
                    :class="{ 'ap-avatar-has-img': !!colleagueForRole(m.colleague_role_key).avatar_url }"
                    :style="{ background: colleagueForRole(m.colleague_role_key).color || 'var(--cpq-accent-primary, #1677ff)' }"
                  >
                    <img v-if="colleagueForRole(m.colleague_role_key).avatar_url" :src="colleagueForRole(m.colleague_role_key).avatar_url" alt="" />
                    <span v-else class="ap-avatar-initial">{{ avatarInitial(colleagueForRole(m.colleague_role_key).name) }}</span>
                  </div>
                  <span class="ap-author">{{ colleagueForRole(m.colleague_role_key).name }}</span>
                </div>
                <div v-if="m.content" class="ap-bubble">{{ m.content }}</div>
                <BusinessArtifactView
                  v-if="artifactFor(m)"
                  :entity-type="artifactFor(m)!.entityType"
                  :entity="artifactFor(m)!.entity"
                  :target="artifactFor(m)!.target"
                  :thread-id="currentThreadId"
                  class="ap-artifact-card"
                />
              </div>
              <!-- 文件产物（输出节点 artifacts 渲染的 PDF 报告等）：文件卡 -->
              <div v-else-if="m.kind === 'file'" class="ap-msg role-assistant ap-msg-result">
                <div class="ap-msg-head">
                  <div
                    class="ap-avatar"
                    :class="{ 'ap-avatar-has-img': !!colleagueForRole(m.colleague_role_key).avatar_url }"
                    :style="{ background: colleagueForRole(m.colleague_role_key).color || 'var(--cpq-accent-primary, #1677ff)' }"
                  >
                    <img v-if="colleagueForRole(m.colleague_role_key).avatar_url" :src="colleagueForRole(m.colleague_role_key).avatar_url" alt="" />
                    <span v-else class="ap-avatar-initial">{{ avatarInitial(colleagueForRole(m.colleague_role_key).name) }}</span>
                  </div>
                  <span class="ap-author">{{ colleagueForRole(m.colleague_role_key).name }}</span>
                </div>
                <div class="ap-file-card">
                  <span class="ap-file-icon">PDF</span>
                  <span class="ap-file-main">
                    <span class="ap-file-title">{{ fileOf(m).title || fileOf(m).filename || '报告文件' }}</span>
                    <span class="ap-file-meta">{{ fileOf(m).filename }}{{ fileSizeText(fileOf(m).size) ? ' · ' + fileSizeText(fileOf(m).size) : '' }}</span>
                  </span>
                  <span class="ap-file-actions">
                    <button type="button" class="ap-file-btn" @click="onDownloadFile(fileOf(m))">下载</button>
                    <button type="button" class="ap-file-btn" @click="onPreviewFile(fileOf(m))">预览</button>
                  </span>
                </div>
              </div>
              <!-- 工作流发起确认卡（suggest_workflow 产物）：一键以需求原文发起工作流 -->
              <div v-else-if="m.kind === 'workflow_suggestion'" class="ap-msg role-assistant ap-msg-result">
                <div class="ap-msg-head">
                  <div
                    class="ap-avatar"
                    :class="{ 'ap-avatar-has-img': !!colleagueForRole(m.colleague_role_key).avatar_url }"
                    :style="{ background: colleagueForRole(m.colleague_role_key).color || 'var(--cpq-accent-primary, #1677ff)' }"
                  >
                    <img v-if="colleagueForRole(m.colleague_role_key).avatar_url" :src="colleagueForRole(m.colleague_role_key).avatar_url" alt="" />
                    <span v-else class="ap-avatar-initial">{{ avatarInitial(colleagueForRole(m.colleague_role_key).name) }}</span>
                  </div>
                  <span class="ap-author">{{ colleagueForRole(m.colleague_role_key).name }}</span>
                </div>
                <div v-if="m.content" class="ap-bubble">{{ m.content }}</div>
                <div class="ap-wf-card">
                  <div class="ap-wf-title">发起工作流：{{ wfOf(m).name || wfOf(m).workflow_key || '—' }}</div>
                  <div v-if="wfOf(m).reason" class="ap-wf-reason">{{ wfOf(m).reason }}</div>
                  <div class="ap-wf-req">{{ wfOf(m).requirement_text }}</div>
                  <button
                    type="button"
                    class="ap-wf-btn"
                    :disabled="sending || running || wfUsed.has(String(m.message_id || ''))"
                    @click="onLaunchSuggestion(m)"
                  >
                    {{ wfUsed.has(String(m.message_id || '')) ? '已发起' : '一键发起' }}
                  </button>
                </div>
              </div>
              <!-- 普通消息：与 AI 办公室角色聊天共用公共消息组件 -->
              <AssistantMessageItem
                v-else
                :message="m"
                :author="colleagueForRole(m.colleague_role_key)"
                :option-interactive="optionInteractive(m)"
                :option-answered="optionAnswered(m)"
                :thread-id="currentThreadId || ''"
                :pick-role="m.colleague_role_key || ''"
                :presence-on="isPresenceOn(m.colleague_role_key)"
                :self-avatar="selfIdentity"
                @select-option="onSelectOption"
                @submit-selections="onSubmitSelections"
                @submit-form="onSubmitForm"
                @answer-query="onAnswerQuery"
                @reply="onReplyMsg"
                @persona="(ev: MouseEvent) => openRoomPersona(colleagueForRole(m.colleague_role_key), ev)"
              />
            </template>
            <AssistantMessageItem
              v-if="streamingText || waitingAI"
              :message="{ role: 'assistant', content: streamingText || '' }"
              :author="activeColleague || { name: '方案助手', avatar_url: '', color: '' }"
              :traces="toolTraces"
              :streaming="!!streamingText"
              :typing="!streamingText && !thinkingActive"
              :status-text="statusText"
              :thinking="thinkingText"
              :thinking-active="thinkingActive"
              :idle-text="idleText"
              @persona="openHeadPersona($event)"
              :show-author="view === 'group'"
            />
          </div>
        </div>

        <!-- 快捷指令：按当前页 provider 条件渲染（需求分析由绑定 Skill 的 AI 角色判断进入） -->
        <div class="ap-quick">
          <button
            v-for="a in visibleQuickActions"
            :key="a.key"
            class="ap-quick-chip"
            :disabled="sending"
            @click="onQuickAction(a)"
          >
            <span>{{ a.label }}</span>
          </button>
        </div>

        <!-- 任务计步器（Claude Code 式）：任务执行中收起胶囊，点击展开步骤明细 -->
        <TaskStepper :traces="nodeTraces" :title="taskTitle" :phase="taskPhase" :pause="taskPause" />

        <!-- 引用回复（原型 composer-quote）：悬停消息 ↩ 后挂在这里，随下一条消息发出 -->
        <div v-if="quoted" class="ap-quote-bar">
          <span class="ap-quote-text">↩ 引用 <b>{{ quoted.name }}</b>：{{ quoted.text }}</span>
          <button type="button" class="ap-quote-x" @click="quoted = null">✕</button>
        </div>

        <!-- 工作流装填条：「+」选中后不发占位消息，输入需求发送即工作流首回合 -->
        <div v-if="armedWorkflow" class="ap-quote-bar">
          <span class="ap-quote-text">▶ 待发起 <b>【{{ armedWorkflow.name }}】</b> ·
            {{ armedWorkflow.launchForm?.fields?.length && !launchFormSkipped ? '填写开工单或直接发送' : '输入需求，发送后开始' }}</span>
          <button type="button" class="ap-quote-x" title="取消发起" @click="cancelArmedWorkflow">✕</button>
        </div>
        <!-- 试运行预览：画布当前工作流常驻同款装填条。与正式聊天同一操作逻辑——
             不自动弹表单，点「填写开工单」才弹；跳过表单直接打字发送同义（首条发送后条隐去） -->
        <div v-else-if="previewLaunch && !previewLaunched" class="ap-quote-bar">
          <span class="ap-quote-text">▶ 待发起 <b>【{{ previewLaunch.name }}】</b> · 填写开工单或直接发送</span>
          <button type="button" class="ap-launch-btn" @click="openPreviewLaunch">填写开工单</button>
        </div>

        <!-- 启动表单：schema 来自流配置（配置者可编辑）。居中弹窗（PC 640 / 手机全屏），
             提交=拼装结构化首条消息；关闭弹窗=自由对话（装填态保留，行为与现状一致）。
             试运行预览：按画布当前工作流自动挂同一张开工单（previewLaunchOpen） -->
        <a-modal
          :open="launchModalOpen"
          :title="'开工单 · ' + (previewLaunchOpen ? previewLaunch?.name || '' : armedWorkflow?.name || '')"
          :width="launchModalWidth"
          :footer="null"
          destroy-on-close
          :z-index="2000"
          :wrap-class-name="'launch-modal-wrap ' + (launchModalFull ? 'launch-modal-full' : '')"
          @cancel="closeLaunchModal"
        >
          <LaunchFormPanel
            :schema="launchModalSchema"
            :defaults="launchFormDefaults"
            @submit="onLaunchModalSubmit"
            @skip="closeLaunchModal"
          />
        </a-modal>

        <!-- 输入：聊天/自然进入需求分析（由 AI 角色判断调用需求分析 Skill）；群聊窗口才有 @ 点名。
             试运行预览：单线程单角色，无点名对象，隐藏 @（2026-09-06 用户指正）；
             附件与正式聊天同机制（会话暂存 → attachment_ids 随消息引用）——交付工作流
             试运行靠它传成本表/方案表，预览线程是真线程，上传/绑定与入口无关 -->
        <AssistantComposer
          v-model="draft"
          :placeholder="composerPlaceholder"
          :disabled="sending || running"
          :sending="sending"
          :running="running"
          :queued="queuedCount"
          :members="preview ? [] : (view === 'group' ? contacts : [])"
          :skills="composerSkills"
          :show-skills="!preview"
          :context-usage="contextUsage"
          :hint="view === 'group' && !preview ? '@ = 指定该同事接话 · Enter 发送 · 悬停消息可引用' : ''"
          allow-attach
          :attachments="stagedFiles"
          @send="onSend"
          @stop="onStop"
          @pick-skill="onPickSkill"
          @files-picked="onFilesPicked"
          @remove-attachment="onRemoveStaged"
        />
        </div>

        <!-- 移动端团队抽屉遮罩：点遮罩关闭 -->
        <transition name="ap-fade">
          <div v-if="isMobile && !contactsCollapsed" class="ap-contacts-scrim" @mousedown.stop @click="contactsCollapsed = true"></div>
        </transition>

        <!-- 右栏：新增对话 / 会话记录 / 收起（扣子式窄条，随视口伸缩）；手机端不渲染（动作在顶栏） -->
        <aside v-if="showRightBar && !isMobile" class="ap-right" @mousedown.stop>
          <!-- 全屏 ⇄ 浮动切换：仅桌面浮动面板出现；Esc 退出 -->
          <button
            v-if="canToggleFullscreen"
            class="ap-icon-btn"
            type="button"
            :title="apFullscreen ? '退出全屏（Esc）' : '全屏'"
            @click="apFullscreen = !apFullscreen"
          >
            <FullscreenExitOutlined v-if="apFullscreen" />
            <FullscreenOutlined v-else />
          </button>
          <!-- 收起：右上方固定位置（门户/浮动一致） -->
          <button class="ap-icon-btn ap-close" type="button" title="收起" @click="emit('update:open', false)">
            <CloseOutlined />
          </button>
          <button
            class="ap-icon-btn"
            type="button"
            title="新对话（归档当前会话）"
            :disabled="sending || running"
            @click="startNewConversation"
          >
            <PlusOutlined />
          </button>
          <button class="ap-icon-btn" type="button" title="会话记录（含归档）" @click="toggleHistory">
            <HistoryOutlined />
          </button>
        </aside>

        <!-- 缩放手柄：仅桌面浮动面板（全屏态隐藏） -->
        <template v-if="!embedded && !preview && !isMobile && !inset && !apFullscreen">
          <span class="ap-resize ap-resize--e" @mousedown.prevent="startResize('e', $event)"></span>
          <span class="ap-resize ap-resize--s" @mousedown.prevent="startResize('s', $event)"></span>
          <span class="ap-resize ap-resize--se" @mousedown.prevent="startResize('se', $event)"></span>
        </template>

        <!-- 同事名片：房间头名册头像点开（Teleport 到 body，不受面板 transform/拖拽影响） -->
        <ColleaguePersonaCard ref="personaRef" :task-action="false" @dm="onPersonaDm" />
        <transition name="ap-drawer">
          <div v-if="historyOpen" class="ap-history-drawer" @mousedown.stop>
            <div class="ap-history-mask" @click="historyOpen = false"></div>
            <aside class="ap-history-panel">
              <div class="ap-history-head">
                <div class="ap-history-title">会话历史 · {{ view === 'group' ? '团队群' : activeColleagueName }}</div>
                <div class="ap-history-actions">
                  <a-popconfirm
                    v-if="clearableHistoryCount > 0"
                    title="彻底删除除当前会话外的全部历史会话？连消息一起清，不可恢复。"
                    ok-text="清空"
                    ok-type="danger"
                    cancel-text="取消"
                    @confirm="clearAllHistory"
                  >
                    <button class="ap-history-clear" type="button" :disabled="historyClearing">
                      {{ historyClearing ? '清理中…' : '清空' }}
                    </button>
                  </a-popconfirm>
                  <button class="ap-history-new" type="button" :disabled="sending || running" @click="startNewConversation">
                    <PlusOutlined />
                    新对话
                  </button>
                </div>
              </div>
              <div class="ap-history-list">
                <button
                  v-for="t in historyItems"
                  :key="t.thread_id"
                  type="button"
                  class="ap-hist-item"
                  :class="{ 'is-current': t.thread_id === currentThreadId }"
                  @click="openHistoryThread(t)"
                >
                  <span class="ap-hist-main">
                    <span class="ap-hist-title">{{ t.title || t.thread_id.slice(0, 18) }}</span>
                    <span class="ap-hist-meta">{{ t.deleted_at ? '已归档' : '进行中' }} · {{ (t.updated_at || '').slice(0, 16).replace('T', ' ') }}</span>
                  </span>
                  <span v-if="t.thread_id === currentThreadId" class="ap-hist-badge">当前</span>
                  <span class="ap-hist-del" title="删除该会话" @click.stop="removeHistoryThread(t)">✕</span>
                </button>
                <div v-if="!historyItems.length" class="ap-hist-empty">暂无历史会话</div>
              </div>
            </aside>
          </div>
        </transition>

        <!-- 文件预览：PDF 报告 objectURL iframe（鉴权由 blob 拉取承担） -->
        <transition name="ap-fade">
          <div v-if="filePreviewUrl" class="ap-file-preview-mask" @click="closeFilePreview">
            <div class="ap-file-preview" @click.stop>
              <div class="ap-file-preview-head">
                <span>报告预览</span>
                <button type="button" title="关闭" @click="closeFilePreview">✕</button>
              </div>
              <iframe :src="filePreviewUrl" class="ap-file-preview-frame" title="报告预览"></iframe>
            </div>
          </div>
        </transition>
      </div>
    </transition>

  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined, CloseOutlined, HistoryOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
} from '@ant-design/icons-vue'
import { useAssistant } from '@/composables/useAssistant'
import { useAssistantContext, type QuickAction } from '@/composables/assistantContext'
import { useAssistantFab, anchorPanel } from '@/composables/useAssistantFab'
import { useChatAutoScroll } from '@/composables/useChatAutoScroll'
import AssistantComposer from '@/components/assistant/AssistantComposer.vue'
import BusinessArtifactView from '@/components/assistant/BusinessArtifactView.vue'
import AssistantMessageItem from '@/components/assistant/AssistantMessageItem.vue'
import TaskStepper from '@/components/assistant/TaskStepper.vue'
import ColleaguePersonaCard from '@/components/assistant/ColleaguePersonaCard.vue'
import { useOfficeSocket } from '@/composables/useOfficeSocket'
import { fmtChatTime } from '@/utils/chatTime'
import { useAuthStore } from '@/store/auth'
import { assistantApi, type AssistantQueryAnswer, type AssistantThread } from '@/api/assistant'
import { officeApi } from '@/api/office'
import { usePetModelStore } from '@/store/petModel'
import { downloadOfficeFile, previewOfficeFileUrl } from '@/utils/fileDownload'

const props = withDefaults(defineProps<{
  open: boolean
  embedded?: boolean
  preview?: boolean
  initialRoleKey?: string
  entryPoint?: string
  workflowKey?: string
  inset?: boolean
  assistant?: ReturnType<typeof useAssistant> | null
}>(), {
  embedded: false,
  preview: false,
  initialRoleKey: '',
  entryPoint: 'floating_assistant',
  workflowKey: '',
  inset: false,
  assistant: null,
})
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

// 外部传入 useAssistant 实例（门户复用同一会话状态、线程连续）则直接用；否则本组件自建。
const ownAssistant = !props.assistant
  ? useAssistant(props.entryPoint || 'floating_assistant', {
      preview: props.preview,
      initialRoleKey: props.initialRoleKey || null,
    })
  : null
const chat = props.assistant || ownAssistant!
const petModel = usePetModelStore()

const {
  currentThreadId, messages, loading, sending, running, streamingText, thinkingText, waitingAI, statusText, queuedCount, nodeTraces, taskTitle, taskPhase, taskPause,
  toolTraces,
  loadThreads, selectThread, send, contextUsage, disconnectWs,
  armedWorkflow, armWorkflow, cancelArmedWorkflow, launchWorkflowNow,
  activeRoleKey, switchRole, createPreviewThread, destroyPreview, resetPreview: resetChatPreview, stop,
} = chat

const { summarize, visibleQuickActions } = useAssistantContext()

function artifactFor(m: { kind?: string; data?: string }): { entityType: string; entity: any; target?: string } | null {
  if (m.kind !== 'business_artifact' || !m.data) return null
  try {
    const d = JSON.parse(m.data)
    const entity = d?.entity || d?.bom_scheme
    if (!entity || !d?.entity_type) return null
    return { entityType: String(d.entity_type), entity, target: d.target ? String(d.target) : undefined }
  } catch {
    return null
  }
}

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)

const composerPlaceholder = computed(() => {
  if (armedWorkflow.value) return `描述需求，发送后开始【${armedWorkflow.value.name}】…`
  return view.value === 'group' && !props.preview ? '输入消息…（@ 可点名同事）' : '输入消息…'
})

// ── 工作流发起确认卡（kind=workflow_suggestion：一键以需求原文发起） ──
function wfOf(m: { kind?: string; data?: string }): Record<string, any> {
  try {
    const d = typeof m.data === 'string' ? JSON.parse(m.data) : (m.data || {})
    const wf = d && typeof d === 'object' ? d.workflow_suggestion : null
    return wf && typeof wf === 'object' ? wf : {}
  } catch {
    return {}
  }
}
const wfUsed = ref<Set<string>>(new Set())
async function onLaunchSuggestion(m: any) {
  const wf = wfOf(m)
  const id = String(m?.message_id || '')
  if (!wf?.workflow_key || !wf?.requirement_text || sending.value || running.value) return
  await launchWorkflowNow(String(wf.workflow_key), String(wf.requirement_text),
                          m?.colleague_role_key || activeRoleKey.value || null)
  if (id) {
    const next = new Set(wfUsed.value)
    next.add(id)
    wfUsed.value = next
  }
}

// ── 文件产物（kind=file 消息卡：PDF 报告等）──
function fileOf(m: { kind?: string; data?: string }): Record<string, any> {
  try {
    const d = typeof m.data === 'string' ? JSON.parse(m.data) : (m.data || {})
    return d && typeof d === 'object' ? d : {}
  } catch {
    return {}
  }
}
function fileSizeText(size: any): string {
  const n = Number(size)
  if (!n || n <= 0) return ''
  return n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
}
const filePreviewUrl = ref('')
async function onDownloadFile(f: Record<string, any>) {
  if (!f?.url) return
  try {
    await downloadOfficeFile(String(f.url), String(f.filename || '报告.pdf'))
  } catch {
    message.error('文件下载失败')
  }
}
async function onPreviewFile(f: Record<string, any>) {
  if (!f?.url) return
  try {
    closeFilePreview()
    filePreviewUrl.value = await previewOfficeFileUrl(String(f.url))
  } catch {
    message.error('文件加载失败')
  }
}
function closeFilePreview() {
  if (filePreviewUrl.value) window.URL.revokeObjectURL(filePreviewUrl.value)
  filePreviewUrl.value = ''
}

const { scrollToBottom } = useChatAutoScroll(messagesEl)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth <= 760)
const contactsCollapsed = ref(typeof window !== 'undefined' && isMobile.value)

// ── 桌面全屏形态：浮动面板的整屏展示形态（浮动/内嵌/预览之外的整屏聊天）。
// 仅浮动面板可切；全屏时禁拖拽/缩放，Esc 或再点一次退出，回浮动不丢会话（同一实例）。
const apFullscreen = ref(false)
const canToggleFullscreen = computed(() =>
  !props.embedded && !props.inset && !props.preview && !isMobile.value)
const exitFullscreenOnEsc = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && apFullscreen.value && props.open) apFullscreen.value = false
}
watch(() => props.open, (v) => {
  if (!v) apFullscreen.value = false
})
watch([activeRoleKey, () => chat.colleagues?.value], () => {
  const c = (chat.colleagues?.value || []).find((x: any) => x?.role_key === activeRoleKey.value)
  petModel.setActive(activeRoleKey.value ?? null, c?.pet_model)
}, { immediate: true })

// ── 桌宠气泡：回复中的流式摘录喂给悬浮宠物（面板关着也能看到进度）──
watch(streamingText, (t) => { petModel.setStreamTail(t || '') })

// 技能流程是否运行中（用于画布 input 节点「运行」状态）
const busy = computed(() => waitingAI.value || !!statusText.value || !!streamingText.value)
const thinkingActive = computed(() => waitingAI.value && (!!thinkingText.value || !streamingText.value))

// ── 静默心跳：waiting 且思考/正文/状态三条流全空超 5s → 「模型思考中 Ns…」 ──
// 纯前端兜底：后端首字节看门狗/重试状态会以 statusText 到位，这里只兜「什么事件都没来」的空窗。
const silentSec = ref(0)
let silentTimer: ReturnType<typeof setInterval> | null = null
const idleText = computed(() =>
  silentSec.value >= 5 ? `模型思考中 ${silentSec.value}s…` : '')

// ── AI 同事身份：群聊式头像/昵称 + 发送前转接确认 ──
// 联系人/同事名单：复用共享 useAssistant 实例的 colleagues（门户挂载时已加载，左栏首帧即现，不再闪）；
// 自建实例则由 useAssistant 的 loadThreads() 内部 loadColleagues() 填充。
const colleaguePool = computed<any[]>(() => (chat.colleagues?.value ? chat.colleagues.value : []))
const activeColleague = computed(
  () => colleaguePool.value.find((c) => c.role_key === activeRoleKey.value) || null,
)
const activeColleagueName = computed(() =>
  activeColleague.value?.name || '方案助手',
)

// ── 输入区「+」工作流菜单：工作流库随库自动增减，只显示当前角色绑定项 ──
const skillCatalog = ref<any[]>([])
async function loadSkillCatalog() {
  try {
    const skills = await officeApi.listSkills()
    skillCatalog.value = Array.isArray(skills) ? skills : []
  } catch {
    skillCatalog.value = []
  }
}
function resolveColleagueSkills(colleague: any): { key: string; name: string; description: string }[] {
  const refs = [
    ...(Array.isArray(colleague?.workflows) ? colleague.workflows : []),
    ...(Array.isArray(colleague?.skills) ? colleague.skills : []),
  ]
  const keys = new Set(
    refs
      .map((r: any) => (typeof r === 'string' ? r : r?.key || r?.skill_key || ''))
      .filter(Boolean)
      .map((k: any) => String(k).trim()),
  )
  if (!keys.size) return []
  return skillCatalog.value
    .filter((sk: any) => keys.has(String(sk?.key || '').trim()))
    .filter((sk: any) => sk?.type === 'workflow')
    .map((sk: any) => ({
      key: String(sk.key || '').trim(),
      name: String(sk.name || sk.key || '').trim(),
      description: String(sk.description || sk.input_contract || '').trim(),
      launchForm: (sk as any).launch_form || null,
    }))
}
const boundSkills = computed<any[]>(() => resolveColleagueSkills(activeColleague.value))
const groupSkills = computed<any[]>(() => {
  const seen = new Set<string>()
  const out: any[] = []
  for (const c of contacts.value) {
    for (const s of resolveColleagueSkills(c)) {
      if (!seen.has(s.key)) {
        seen.add(s.key)
        // 带上归属同事：群聊装填后发送要钉住这位角色（防判官把 launcher 消息路由给别人）
        out.push({ ...s, ownerRoleKey: c?.role_key || '', ownerName: c?.name || '' })
      }
    }
  }
  return out
})
const composerSkills = computed<any[]>(() => (view.value === 'group' ? groupSkills.value : boundSkills.value))
function onPickSkill(skill: any) {
  if (!skill?.key) return
  launchFormSkipped.value = false
  armWorkflow(skill.key, skill.name || skill.key, skill.ownerRoleKey || activeRoleKey.value || null,
              (skill as any).launchForm || null)
}

/* ── 启动表单提交：文件走既有聊天附件通道，参数拼装结构化首条消息 ── */
const launchFormSkipped = ref(false)
/** 弹窗两用：正式聊天=装填态的启动表单；试运行预览=画布当前工作流的开工单。 */
const launchModalOpen = computed(() =>
  previewLaunchOpen.value ||
  (!!(armedWorkflow.value?.launchForm?.fields?.length) && !launchFormSkipped.value))
const launchModalSchema = computed(() =>
  previewLaunchOpen.value ? previewLaunch.value!.schema : (armedWorkflow.value?.launchForm || null))
function closeLaunchModal() {
  launchFormSkipped.value = true
  previewFormRequested.value = false
  previewLaunchSkipped.value = true
}
function onLaunchModalSubmit(payload: { values: Record<string, string>; files: File[] }) {
  return previewLaunchOpen.value ? onPreviewLaunchSubmit(payload) : onLaunchFormSubmit(payload)
}
const launchModalWidth = computed(() => (window.innerWidth < 768 ? '100vw' : '640px'))
const launchModalFull = computed(() => window.innerWidth < 768)
const launchFormDefaults = computed(() => ({
  当前用户姓名: auth.user?.name || '',
}))
async function onLaunchFormSubmit(payload: { values: Record<string, string>; files: File[] }) {
  if (!armedWorkflow.value) return
  if (payload.files.length) await onFilesPicked(payload.files)
  if (stagedFiles.value.some((c) => c.status === 'uploading')) {
    message.warning('附件上传中，请稍候')
    return
  }
  const lines = Object.entries(payload.values).map(([label, v]) => `· ${label}：${v}`)
  if (payload.files.length) lines.push(`· 附件：${payload.files.map((f) => f.name).join('、')}`)
  const text = '【开工单】\n' + lines.join('\n')
  const attachmentIds = stagedFiles.value.filter((c) => c.status === 'done' && c.attachment_id)
    .map((c) => c.attachment_id!)
  launchFormSkipped.value = true
  await sendText(text, null, null, null, attachmentIds)
}

/* ── 试运行开工单：预览面板按画布当前工作流常驻「待发起」装填条（与正式聊天同款）。
 *    同一操作逻辑：不自动弹表单，点「填写开工单」才弹（previewFormRequested）；
 *    跳过表单直接打字 sendText 同义（首条 sendText 后 previewLaunched 隐条，重置测试恢复）。 ── */
const previewLaunchSkipped = ref(false)
const previewFormRequested = ref(false)
const previewLaunched = ref(false)
const previewLaunch = computed(() => {
  if (!props.preview || !props.workflowKey) return null
  const sk = skillCatalog.value.find((s: any) => String(s?.key || '') === String(props.workflowKey || ''))
  const schema = (sk as any)?.launch_form || null
  return schema?.fields?.length ? { schema, name: String(sk?.name || sk?.key || '') } : null
})
const previewLaunchOpen = computed(() =>
  !!previewLaunch.value && previewFormRequested.value && !previewLaunchSkipped.value)
function openPreviewLaunch() {
  previewLaunchSkipped.value = false
  previewFormRequested.value = true
}
async function onPreviewLaunchSubmit(payload: { values: Record<string, string>; files: File[] }) {
  if (payload.files.length) await onFilesPicked(payload.files)
  if (stagedFiles.value.some((c) => c.status === 'uploading')) {
    message.warning('附件上传中，请稍候')
    return
  }
  const lines = Object.entries(payload.values).map(([label, v]) => `· ${label}：${v}`)
  if (payload.files.length) lines.push(`· 附件：${payload.files.map((f) => f.name).join('、')}`)
  const attachmentIds = stagedFiles.value.filter((c) => c.status === 'done' && c.attachment_id)
    .map((c) => c.attachment_id!)
  previewLaunchSkipped.value = true
  previewFormRequested.value = false
  previewLaunched.value = true
  await sendText('【开工单】\n' + lines.join('\n'), null, null, null, attachmentIds)
}
function colleagueForRole(roleKey?: string): {
  name: string
  avatar_url: string
  color?: string
} {
  if (!roleKey) return { name: '方案助手', avatar_url: '', color: '' }
  const found = colleaguePool.value.find((c) => c?.role_key === roleKey)
  if (found) return found
  return { name: roleKey, avatar_url: '', color: '' }
}
function avatarInitial(name?: string): string {
  const text = (name || 'AI').trim()
  return Array.from(text)[0] || 'AI'
}
function colleagueDescription(c?: any): string {
  if (!c) return 'AI 同事'
  if (typeof c.description === 'string' && c.description.trim()) return c.description.trim()
  const caps = Array.isArray(c.capabilities) ? c.capabilities : []
  const capText = caps
    .map((x: any) => (typeof x === 'string' ? x : x?.label || x?.name || ''))
    .filter(Boolean)
    .join('、')
  if (capText) return capText
  const skills = Array.isArray(c.skills) ? c.skills : []
  const skillText = skills
    .map((x: any) => (typeof x === 'string' ? x : x?.name || x?.key || ''))
    .filter(Boolean)
    .join('、')
  if (skillText) return skillText
  return 'AI 同事'
}
function roleAvatarStyle(c?: any) {
  return { background: c?.color || 'var(--cpq-accent-primary, #1677ff)' }
}
// ── 房间头名片：名册头像 → 同事名片浮层（发私聊切 DM；聊天窗口里没有任务板，不显「看任务」）──
const personaRef = ref<InstanceType<typeof ColleaguePersonaCard> | null>(null)
function openRoomPersona(c: any, ev: MouseEvent) {
  personaRef.value?.openFor(c, officeStatus.value?.[c?.role_key] || null, null, ev.currentTarget as HTMLElement)
}
function openHeadPersona(ev: MouseEvent) {
  const c = view.value === 'group'
    ? contacts.value.find((x) => x.role_key === 'assistant') || contacts.value[0] || null
    : (activeColleague.value || null)
  if (c) openRoomPersona(c, ev)
}
function onPersonaDm(roleKey?: string) {
  personaRef.value?.close()
  if (!roleKey) return
  const c = contacts.value.find((x) => x.role_key === roleKey)
  if (c) void openDm(c)
}

// ── 引用回复：悬停消息 ↩ → composer 上方引用条 → 随下一条用户消息发出（快照落库）──
const quoted = ref<{ name: string; text: string } | null>(null)
function onReplyMsg(q: { name: string; text: string }) {
  quoted.value = q
}
watch(currentThreadId, (id) => { quoted.value = null; markSeen(id) })

// ── 消息中心侧栏（原型 conv-list）：presence / 筛选签 / 房间 / 预览 / 未读 ──
const office = useOfficeSocket()
const officeStatus = office.statusMap
/** 登录用户身份（人类侧消息：右侧小头像 + 「你 · 人类」meta） */
const auth = useAuthStore()
const selfIdentity = computed(() => ({
  name: String((auth.user as any)?.name || '你'),
  avatar_url: String((auth.user as any)?.avatar_url || ''),
}))
onMounted(() => {
  office.connect()
  void refreshThreadIndex(true)
  // 默认落到默认房间（全员大厅）：原型进入即有选中会话，别停在空态
  if (view.value === 'group' && !currentThreadId.value) void openGroup()
})
onBeforeUnmount(() => { office.disconnect() })
function isPresenceOn(roleKey?: string | null): boolean {
  const st = String((roleKey || '').trim() ? officeStatus.value?.[roleKey!]?.status || '' : '')
  return !!st && st !== 'idle'
}

/** 全量会话索引（带 last_message/updated_at meta）：侧栏预览与未读的唯一数据源 */
const threadIndex = ref<AssistantThread[]>([])
let indexRefreshTimer: ReturnType<typeof setTimeout> | null = null
async function refreshThreadIndex(initial = false) {
  try {
    // allKinds：群线程(assistant) + 同事线程(office_colleague) 一起拿；预览线程不算会话
    const list = ((await assistantApi.threads.list({ includeDeleted: false, withMeta: true, allKinds: true })) || [])
      .filter((t) => t.entry_point !== 'skill_studio_preview')
    // 首次点亮：存量会话记到各自 updated_at（同源格式），此后新动静才计未读
    if (initial && !localStorage.getItem(SEEN_KEY)) {
      for (const t of list) seenMap[t.thread_id] = String(t.updated_at || localStamp())
      persistSeen()
    }
    threadIndex.value = list
  } catch { /* 侧栏索引刷新失败保留旧数据 */ }
}
function scheduleIndexRefresh() {
  if (indexRefreshTimer) clearTimeout(indexRefreshTimer)
  indexRefreshTimer = setTimeout(() => { indexRefreshTimer = null; void refreshThreadIndex() }, 800)
}

// ── 未读：本地 lastSeen 时间戳（打开即记已读；首次点亮存量全记已读）──
// v2：v1 存过 UTC toISOString 戳，与后端本地时间串比大小全错（红点清不掉的根因），弃用
const SEEN_KEY = 'ap-thread-seen-v2'
const seenMap = reactive<Record<string, string>>(readSeen())
function readSeen(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(SEEN_KEY) || '{}') || {} } catch { return {} }
}
function persistSeen() {
  try { localStorage.setItem(SEEN_KEY, JSON.stringify(seenMap)) } catch { /* 隐私模式等存不了就弃 */ }
}
function markSeen(threadId?: string | null) {
  if (!threadId) return
  // 戳必须与后端 now_iso 同格式同钟（本地时间 ISO），否则字符串比大小全错（UTC 坑已踩）
  seenMap[threadId] = localStamp()
  persistSeen()
}
function localStamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function unreadOfThread(t: AssistantThread): boolean {
  if (t.thread_id === currentThreadId.value) return false
  const seen = String(seenMap[t.thread_id] || '')
  return !!String(t.updated_at || '') && String(t.updated_at) > seen
}

const roomThreads = computed(() => threadIndex.value.filter((t) => !String(t.colleague_role_key || '').trim()))
function roomName(t: AssistantThread): string {
  return String(t.title || '').trim() || '全员大厅'
}
function previewOf(t: AssistantThread): string {
  return String(t.last_message || '').replace(/[*`#_]/g, '').replace(/\s+/g, ' ').trim()
}
function contactThread(roleKey?: string): AssistantThread | undefined {
  const key = String(roleKey || '').trim()
  if (!key) return undefined
  return threadIndex.value.find((t) => String(t.colleague_role_key || '') === key)
}
function contactPreview(roleKey?: string): string {
  const t = contactThread(roleKey)
  if (t && previewOf(t)) return previewOf(t)
  const c = contacts.value.find((x) => x.role_key === roleKey)
  return c ? colleagueDescription(c) : 'AI 同事'
}
function contactUnread(roleKey?: string): boolean {
  const t = contactThread(roleKey)
  return t ? unreadOfThread(t) : false
}

// ── 房间 = 有名字的群线程（title 即房间名，无 colleague_role_key）；切换/新建零迁移 ──
async function openRoom(t: AssistantThread) {
  view.value = 'group'
  if (isMobile.value) contactsCollapsed.value = true
  try {
    let tid = t.thread_id
    if (String(t.deleted_at || '').trim()) {
      const restored = await assistantApi.threads.restore(tid)
      tid = restored.thread_id
      groupThread.value = restored
    } else {
      groupThread.value = t
    }
    await selectThread(tid, { kind: 'group' })
  } catch { /* ignore */ }
}
const roomCreating = ref(false)
const roomNameDraft = ref('')
async function createRoom() {
  const name = roomNameDraft.value.trim()
  if (!name) return
  try {
    const t = await assistantApi.threads.create(undefined, name)
    roomCreating.value = false
    roomNameDraft.value = ''
    await refreshThreadIndex()
    await openRoom(t)
  } catch {
    message.error('创建房间失败')
  }
}

watch(() => props.open, (v) => {
  if (!v) return
  void refreshThreadIndex()
  if (view.value === 'group' && !currentThreadId.value) void openGroup()
})
watch(() => messages.value?.length, () => {
  markSeen(currentThreadId.value)
  scheduleIndexRefresh()
})
// ── 两栏消息中心：view=group（团队群，可@点名/leader调度）| view=dm（1:1，锁定身份）──
const view = ref<'group' | 'dm'>('group')
const groupThread = ref<AssistantThread | null>(null)
const contacts = computed(() => colleaguePool.value)
const showRightBar = computed(() => !props.preview && (props.inset || !props.embedded))
const showContacts = computed(() => !props.preview && (props.inset || !props.embedded) && contacts.value.length >= 2)

async function openGroup(forceNew = false) {
  view.value = 'group'
  if (isMobile.value) contactsCollapsed.value = true
  try {
    if (forceNew && groupThread.value?.thread_id) {
      try {
        await assistantApi.threads.remove(groupThread.value.thread_id)
      } catch {
        /* ignore */
      }
      groupThread.value = null
    }
    if (!groupThread.value) {
      const data = await assistantApi.threads.groupResolve({ entry_point: props.entryPoint })
      groupThread.value = data.thread
    }
    activeRoleKey.value = 'assistant'
    if (currentThreadId.value !== groupThread.value.thread_id) {
      await selectThread(groupThread.value.thread_id, { kind: 'group' })
    }
  } catch {
    /* ignore */
  }
}

async function openDm(c: any) {
  view.value = 'dm'
  if (isMobile.value) contactsCollapsed.value = true
  await switchRole(c.role_key)
}

/** 新对话：归档当前会话（软删，数据库保留），开全新上下文 */
async function startNewConversation() {
  const tid = currentThreadId.value
  if (!tid || sending.value || running.value) return
  try {
    await assistantApi.threads.remove(tid)
  } catch {
    /* ignore */
  }
  historyOpen.value = false
  if (view.value === 'group') {
    groupThread.value = null
    await openGroup()
  } else if (activeRoleKey.value) {
    await switchRole(activeRoleKey.value)
  }
}

// ── 会话记录（含归档）：切换 / 恢复换位 / 删除 ──
const historyOpen = ref(false)
const historyItems = ref<AssistantThread[]>([])

async function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) await loadHistory()
}

/** 桌面「点内容区收起」：历史推出时点击聊天主体空白可关闭，交互控件除外 */
function onMainAreaClick(e: MouseEvent) {
  if (!historyOpen.value || isMobile.value) return
  const t = e.target as HTMLElement
  if (t.closest('button, a, input, textarea, select, [contenteditable="true"], label')) return
  historyOpen.value = false
}

async function loadHistory() {
  try {
    if (view.value === 'group') {
      historyItems.value = ((await assistantApi.threads.list({ includeDeleted: true })) || []).filter(
        (t) => !String(t.colleague_role_key || '').trim(),
      )
    } else if (activeRoleKey.value) {
      historyItems.value = await assistantApi.threads.listOffice(activeRoleKey.value, { includeDeleted: true })
    } else {
      historyItems.value = []
    }
  } catch {
    historyItems.value = []
  }
}

async function openHistoryThread(t: AssistantThread) {
  historyOpen.value = false
  try {
    // 渠道提示：群线程不带 colleague_role_key，必须显式声明 group，路由进群会话而不是 dm
    const hint = view.value === 'group'
      ? { kind: 'group' as const }
      : { kind: 'dm' as const, roleKey: t.colleague_role_key || activeRoleKey.value }
    if (String(t.deleted_at || '').trim()) {
      // 归档会话恢复：后端自动把同角色当前活跃会话归档换位
      const restored = await assistantApi.threads.restore(t.thread_id)
      if (view.value === 'group') groupThread.value = restored
      await selectThread(restored.thread_id, hint)
      return
    }
    if (view.value === 'group') groupThread.value = t
    await selectThread(t.thread_id, hint)
  } catch {
    /* ignore */
  }
}

async function removeHistoryThread(t: AssistantThread) {
  // ✕ = 彻底删除（软删等于再归档一次，用户感知不到区别）；硬删连消息一起物理清
  try {
    await assistantApi.threads.purge(t.thread_id)
  } catch {
    /* ignore */
  }
  if (t.thread_id === currentThreadId.value) {
    // 删的是当前会话：直接开一个全新会话补位
    historyOpen.value = false
    await startNewConversation()
    return
  }
  await loadHistory()
}

const historyClearing = ref(false)
const clearableHistoryCount = computed(
  () => historyItems.value.filter((t) => t.thread_id !== currentThreadId.value).length,
)

async function clearAllHistory() {
  // 批量=逐条 ✕ 同款 purge（硬删连消息），当前会话保留；单条失败不中断
  const targets = historyItems.value.filter((t) => t.thread_id !== currentThreadId.value)
  if (!targets.length) return
  historyClearing.value = true
  try {
    for (const t of targets) {
      try {
        await assistantApi.threads.purge(t.thread_id)
      } catch {
        /* 单条失败继续清 */
      }
    }
  } finally {
    historyClearing.value = false
  }
  await loadHistory()
}

// 面板独立定位：首次打开时按 FAB 附近锚定一次，之后拖动走自己的 panelPos（不再耦合 FAB，
// 避免"只能整块放 FAB 上方/下方"的锚定算法在面板过大时把窗口钉死在屏幕底部）。
const { getFabRect, panelPos, panelSize, movePanelClamped, refitPanelToViewport, persistPanel } = useAssistantFab()
const viewportTick = ref(0)

/** 面板打开时若无自定义位置，按 FAB 附近锚定一次；FAB 不可见时落到右下角默认位。 */
function ensurePanelPos() {
  if (props.embedded || props.inset || panelPos.value) return
  const rect = getFabRect()
  const pos = anchorPanel(rect, window.innerWidth, window.innerHeight)
  persistPanel(pos)
}

// 面板尺寸：桌面下可自由缩放（右/下/右下三向）；大小不持久化，仅内存态。
const PANEL_MIN_W = 360
const PANEL_MIN_H = 420
const RESIZE_MARGIN = 8

/** 按当前视口夹取尺寸：下限 360×420，上限不超视口（留边距）。 */
function clampPanelSize(w: number, h: number) {
  if (typeof window === 'undefined') return { width: Math.max(PANEL_MIN_W, w), height: Math.max(PANEL_MIN_H, h) }
  const vw = window.innerWidth
  const vh = window.innerHeight
  const maxW = Math.max(PANEL_MIN_W, vw - 2 * RESIZE_MARGIN)
  const maxH = Math.max(PANEL_MIN_H, vh - 2 * RESIZE_MARGIN)
  return {
    width: Math.min(Math.max(w, PANEL_MIN_W), maxW),
    height: Math.min(Math.max(h, PANEL_MIN_H), maxH),
  }
}

const initialSize = panelSize(typeof window !== 'undefined' ? window.innerWidth : 1200, typeof window !== 'undefined' ? window.innerHeight : 800)
const panelW = ref(initialSize.width)
const panelH = ref(initialSize.height)

const panelStyle = computed(() => {
  if (props.embedded || props.inset) return {}
  // 依赖 panelPos / viewportTick 触发重算（面板拖动或窗口缩放时跟着挪）
  void viewportTick.value
  // 手机端与桌面全屏共用占满视口的一支：像原生 App 的全屏聊天
  if (apFullscreen.value || (typeof window !== 'undefined' && window.innerWidth <= 760)) {
    // 高度取实时 innerHeight：移动端地址栏伸缩会改可视高度，100vh 会把输入区顶出屏幕；viewportTick 已随 resize 重算
    const h = typeof window !== 'undefined' ? `${window.innerHeight}px` : '100vh'
    return { left: '0px', top: '0px', right: 'auto', bottom: 'auto', width: '100vw', height: h, maxHeight: h }
  }
  // 还没有初始化位置 → 回落 CSS 默认（右下角），避免面板飞到左上角
  if (!panelPos.value) return undefined
  return {
    left: panelPos.value.x + 'px',
    top: panelPos.value.y + 'px',
    right: 'auto',
    bottom: 'auto',
    width: panelW.value + 'px',
    height: panelH.value + 'px',
    maxHeight: panelH.value + 'px',
  }
})
function onResize() {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth <= 760
  if (isMobile.value) contactsCollapsed.value = true
  // 视口变化 → 把当前尺寸/位置夹回新视口，并重夹面板位置（全屏态无自由位，跳过）
  if (!props.embedded && !props.inset && !apFullscreen.value && panelPos.value) {
    const next = clampPanelSize(panelW.value, panelH.value)
    panelW.value = next.width
    panelH.value = next.height
    refitPanelToViewport(panelW.value, panelH.value)
  }
  viewportTick.value++
}
onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', exitFullscreenOnEsc)
  silentTimer = setInterval(() => {
    const silent = waitingAI.value && !thinkingText.value && !streamingText.value && !statusText.value
    silentSec.value = silent ? silentSec.value + 1 : 0
  }, 1000)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', exitFullscreenOnEsc)
  if (silentTimer) {
    clearInterval(silentTimer)
    silentTimer = null
  }
  if (props.embedded && props.preview) {
    destroyPreview()
  }
})

// 拖动逻辑：直接移动面板自身的独立位置（夹进视口），面板始终跟随指针，不再与 FAB 联动。
let dragging = false
let dragStart = { x: 0, y: 0 }
let panelStart = { x: 0, y: 0 }
let panelDragSize = { w: 680, h: 680 }

function startDrag(e: MouseEvent) {
  if (props.embedded || props.inset || apFullscreen.value) return
  // 忽略关闭按钮点击
  if ((e.target as HTMLElement).closest('.ap-close')) return
  if (!panelPos.value) return
  dragging = true
  dragStart = { x: e.clientX, y: e.clientY }
  panelStart = { x: panelPos.value.x, y: panelPos.value.y }
  panelDragSize = { w: panelW.value, h: panelH.value }
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  // 防止选中文字
  e.preventDefault()
}

function onDrag(e: MouseEvent) {
  if (!dragging) return
  const dx = e.clientX - dragStart.x
  const dy = e.clientY - dragStart.y
  movePanelClamped(panelStart.x + dx, panelStart.y + dy, panelDragSize.w, panelDragSize.h)
}

function stopDrag() {
  if (!dragging) return
  dragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

// 缩放逻辑：右缘(宽) / 下缘(高) / 右下角(双向)，固定左/上边，把面板尺寸夹进视口。
let resizing = false
let resizeEdge = ''
let resizeStart = { x: 0, y: 0 }
let resizeSize = { w: 0, h: 0 }
let resizePanel = { x: 0, y: 0 }

function startResize(edge: string, e: MouseEvent) {
  if (props.embedded || props.inset || apFullscreen.value || isMobile.value || !panelPos.value) return
  resizing = true
  resizeEdge = edge
  resizeStart = { x: e.clientX, y: e.clientY }
  resizeSize = { w: panelW.value, h: panelH.value }
  resizePanel = { x: panelPos.value.x, y: panelPos.value.y }
  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
  document.body.style.userSelect = 'none'
  e.preventDefault()
}

function onResizeMove(e: MouseEvent) {
  if (!resizing) return
  const dx = e.clientX - resizeStart.x
  const dy = e.clientY - resizeStart.y
  let w = resizeSize.w
  let h = resizeSize.h
  if (resizeEdge === 'e' || resizeEdge === 'se') w = resizeSize.w + dx
  if (resizeEdge === 's' || resizeEdge === 'se') h = resizeSize.h + dy
  // 固定左/上边不动，右/下边要留在视口内；若摆不下，movePanelClamped 会往回推位置
  const vw = window.innerWidth
  const vh = window.innerHeight
  const maxW = Math.max(PANEL_MIN_W, vw - RESIZE_MARGIN - resizePanel.x)
  const maxH = Math.max(PANEL_MIN_H, vh - RESIZE_MARGIN - resizePanel.y)
  w = Math.min(Math.max(w, PANEL_MIN_W), maxW)
  h = Math.min(Math.max(h, PANEL_MIN_H), maxH)
  panelW.value = w
  panelH.value = h
  movePanelClamped(resizePanel.x, resizePanel.y, w, h)
}

function stopResize() {
  if (!resizing) return
  resizing = false
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.userSelect = ''
}

// 关面板不断在途回合：回合跑完再断 WS（置位后由流结束回调消费）
let closeWhenIdle = false
watch([waitingAI, running, sending], ([a, b, c]) => {
  if (closeWhenIdle && !a && !b && !c) {
    closeWhenIdle = false
    disconnectWs()
  }
})
watch(
  () => props.open,
  async (v) => {
    const active = props.embedded || v
    if (active) {
      closeWhenIdle = false // 重新打开：撤销延迟断连，连接归面板接管
      ensurePanelPos()
      await Promise.all([loadThreads(), loadSkillCatalog()])
      if (props.embedded && props.preview) {
        await createPreviewThread()
      } else if (!currentThreadId.value) {
        // 默认 1:1 找方案助手（私聊=他自己办，系统不转接）；团队群从侧栏显式进入（转接只发生在群里）
        const lead = contacts.value.find((c: any) => c.role_key === 'assistant') || contacts.value[0]
        if (lead) await openDm(lead)
      }
    } else {
      // 关面板不断在途回合的连接：回合还在跑就保持 socket（桌宠实时气泡依赖活性流），跑完自动断
      if (waitingAI.value || running.value || sending.value) {
        closeWhenIdle = true
      } else {
        disconnectWs()
      }
    }
  },
  { immediate: true },
)

watch(() => messages.value.length, () => scrollToBottom(true))
watch(streamingText, () => scrollToBottom())

// ── 聊天附件：选中即传到会话暂存，发送时随 attachment_ids 引用（✕ 仅移除 chip，
// 暂存行等 TTL 懒清理；发送失败不回收——重发同一条消息仍可引用）──
interface StagedChip {
  attachment_id?: string
  localKey: string
  name: string
  size: number
  status: 'uploading' | 'done' | 'error'
  error?: string
}
const stagedFiles = ref<StagedChip[]>([])
let stagedSeq = 0

async function onFilesPicked(files: File[]) {
  for (const f of files) {
    const chip: StagedChip = {
      localKey: `local-${Date.now()}-${stagedSeq++}`,
      name: f.name, size: f.size, status: 'uploading',
    }
    stagedFiles.value.push(chip)
    try {
      if (!currentThreadId.value) await chat.newThread()
      const res = await assistantApi.threads.uploadAttachment(currentThreadId.value!, f)
      chip.attachment_id = res.attachment.attachment_id
      chip.status = 'done'
    } catch (err) {
      chip.status = 'error'
      chip.error = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || `上传失败（${f.name}）`
    }
  }
}

function onRemoveStaged(key: string) {
  stagedFiles.value = stagedFiles.value.filter(
    (c) => (c.attachment_id || c.localKey) !== key)
}

async function onSend() {
  const ready = stagedFiles.value.filter((c) => c.status === 'done' && c.attachment_id)
  if (stagedFiles.value.some((c) => c.status === 'uploading')) return
  let text = draft.value
  if (!text.trim() && ready.length) text = ready.map((c) => c.name).join('、')
  if (!text.trim()) return
  draft.value = ''
  stagedFiles.value = []
  const q = quoted.value
  quoted.value = null
  await sendText(text, null, null, q, ready.map((c) => c.attachment_id!))
}

async function onStop() {
  await stop()
}

// 供父组件（SkillStudio 输入节点「运行」）注入文本到真实 AI 对话
async function sendText(text: string, optionSlot?: string | null,
                        cardSelections?: Array<{ slot: string; value: string; label?: string; qty?: number }> | null,
                        quote?: { name: string; text: string } | null,
                        attachmentIds?: string[] | null) {
  const content = (text || '').trim()
  if (!content || sending.value || running.value) return
  if (props.preview) {
    previewLaunched.value = true
    previewFormRequested.value = false
  }
  if (props.embedded && props.preview && !currentThreadId.value) {
    await createPreviewThread()
  }
  const summary = await summarize()
  await send(content, summary, optionSlot || null, cardSelections || null,
             props.workflowKey ? props.workflowKey : null, quote || null,
             attachmentIds || null)
}

// 结构化选项点击：value 作为消息内容，slot 显式传后端落槽（缺失会导致反问重复）
function onSelectOption(value: string, slot?: string) {
  if (sending.value || running.value) return
  sendText(value, slot || null)
}

// 会话输入卡提交：组装好的「label」=值 文本作为用户消息回流，AI 据此继续
function onSubmitForm(text: string) {
  if (sending.value || running.value) return
  sendText(text, null)
}

// 问答协议：结构化回答按 query_id 回流（POST /answers），答案由轮壳路由
async function onAnswerQuery(payload: AssistantQueryAnswer) {
  const tid = currentThreadId.value || ''
  if (!tid) return
  try {
    await assistantApi.answers.create(tid, payload)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '回答提交失败')
  }
}

// 逐项卡提交：一条消息带 (slot,value,qty)，用户气泡只展示可读文案（数量跟在型号后）
function onSubmitSelections(selections: Array<{ slot: string; value: string; label: string; qty?: number }>) {
  if (sending.value || running.value) return
  sendText('已选：' + selections.map((s) => (s.qty ? `${s.label} ×${s.qty}` : s.label)).join('；'), null, selections)
}

// 问题面板答过判定（Claude Code 语义：答完即收，回合粒度）：本卡之后出现用户消息
// （提交气泡/自由输入）→ 本轮已收，塌成一行静态记录；未答的兄弟卡也一并收起，
// 新一轮会对剩余缺口重发新卡。同轮多卡（S1 缺口一次问全）互不塌——旧版把
// 「更新的选项卡」也当已答条件，同轮第二张卡一落列第一张就秒塌「已处理」
// （2026-09-06 实机复现）。重问卡必有用户消息在前，无需单列该条件。
// 要改选就打字说明，角色按改口覆盖。表单卡本地点选不发消息，不受影响。
// 「已答塌行」与「回合进行中禁点」是两个语义：running 时卡必须可见（AI 已预告
// 选项卡，整卡消失=用户对着三个点等一张不存在的卡，2026-09-05 实测）。
function optionAnswered(m: any): boolean {
  if (m?.kind !== 'input_options') return false
  const arr = messages.value || []
  const idx = arr.indexOf(m)
  if (idx === -1) return true
  for (let j = idx + 1; j < arr.length; j++) {
    if (arr[j]?.role === 'user') return true
  }
  return false
}
function optionInteractive(m: any): boolean {
  if (m?.kind !== 'input_options') return true
  return !optionAnswered(m) && !sending.value && !running.value
}

/** 预览会话重置（工作流画布「重置测试」用）：purge 线程并清空聊天/轨迹/状态；
 *  装填条恢复「待发起」（表单不自动弹，点「填写开工单」再弹）。 */
async function resetPreview() {
  previewFormRequested.value = false
  previewLaunchSkipped.value = false
  previewLaunched.value = false
  await resetChatPreview()
}

defineExpose({ sendText, nodeTraces, busy, resetPreview })

// 快捷指令：prompt 可为函数（动态读配置，如趋势分析）；context 缺省走通用 provider 摘要
async function onQuickAction(action: QuickAction) {
  if (sending.value || running.value) return
  const prompt = typeof action.prompt === 'function' ? await action.prompt() : action.prompt
  const ctx = action.context ? await action.context() : await summarize()
  await send(prompt, ctx)
}
</script>

<style scoped>
.assistant-panel {
  position: fixed;
  right: 24px;
  bottom: 88px;
  width: min(680px, calc(100vw - 32px));
  height: min(680px, calc(100vh - 120px));
  max-height: calc(100vh - 120px);
  /* 纯色实底（2026-10-21 去透明度；底色走 bg-secondary 蓝黑系与全站主题一致——bg-elevated 是中性灰，暗色下发灰不搭） */
  background: var(--cpq-bg-secondary, #ffffff);
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  box-shadow: 0 12px 40px var(--cpq-shadow-color-strong, rgba(0, 0, 0, 0.25));
  z-index: 1600;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

/* 桌面全屏形态：占满视口（panelStyle 内联样式承担定位），只负责去掉浮窗圆角与投影 */
.assistant-panel.ap-fullscreen {
  border-radius: 0;
  box-shadow: none;
}

/* 上下文水位 */
.ap-ctx-usage {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}
.ap-ctx-usage-track {
  width: 72px;
  height: 4px;
  border-radius: var(--cpq-radius-xs);
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.12));
  overflow: hidden;
}
.ap-ctx-usage-fill {
  display: block;
  height: 100%;
  border-radius: var(--cpq-radius-xs);
  background: var(--cpq-accent-primary, #1677ff);
  transition: width 0.3s ease;
}
.ap-ctx-usage-num {
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
}
.ap-ctx-usage--warn .ap-ctx-usage-fill { background: #faad14; }
.ap-ctx-usage--warn .ap-ctx-usage-num { color: #faad14; }
.ap-ctx-usage--high .ap-ctx-usage-fill { background: #ff4d4f; }
.ap-ctx-usage--high .ap-ctx-usage-num { color: #ff4d4f; }

/* 会话记录：桌面=右侧推出的等宽栏，手机=右滑抽屉（视觉与左通讯录一致） */
.ap-history-drawer {
  position: relative;
  flex: none;
  width: 200px;
  min-width: 0;
  border-left: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.ap-history-mask {
  display: none;
}
.ap-history-panel {
  position: relative;
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  background: transparent;
}
.ap-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}
.ap-history-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-muted, #9aa4b2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-history-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}
.ap-history-clear {
  flex: none;
  border: none;
  background: transparent;
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
  cursor: pointer;
  padding: 0;
}
.ap-history-clear:hover { color: #ff4d4f; }
.ap-history-clear:disabled { cursor: default; opacity: 0.6; }
.ap-history-new {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--cpq-accent-primary, #1677ff);
  border-radius: var(--cpq-radius-md);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.10));
  cursor: pointer;
}
.ap-history-new:hover { background: var(--cpq-overlay-a10, rgba(22, 119, 255, 0.16)); }
.ap-history-new:disabled { opacity: 0.55; cursor: not-allowed; }
.ap-history-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 桌面：历史列随宽度推出，内容 flex 让位 */
.ap-drawer-enter-active,
.ap-drawer-leave-active { transition: opacity 0.18s ease, width 0.22s ease; }
.ap-drawer-enter-from,
.ap-drawer-leave-to { width: 0; opacity: 0; }

@media (max-width: 760px) {
  .ap-history-drawer {
    position: absolute;
    inset: 0;
    z-index: 60;
    display: flex;
    flex-direction: row;
    justify-content: flex-end;
    width: auto;
    border-left: none;
    overflow: visible;
  }
  .ap-history-mask {
    display: block;
    position: absolute;
    inset: 0;
    background: rgba(2, 6, 23, 0.30);
  }
  .ap-history-panel {
    position: relative;
    flex: none;
    width: min(260px, 78vw);
    max-width: 320px;
    height: 100%;
    border-left: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
    background: var(--cpq-bg-secondary, #ffffff);
    box-shadow: -12px 0 32px rgba(0, 0, 0, 0.35);
  }
  .ap-drawer-enter-active,
  .ap-drawer-leave-active { transition: opacity 0.18s ease; }
  .ap-drawer-enter-active .ap-history-panel,
  .ap-drawer-leave-active .ap-history-panel { transition: transform 0.18s ease; }
  .ap-drawer-enter-from,
  .ap-drawer-leave-to { width: auto; }
  .ap-drawer-enter-from .ap-history-panel,
  .ap-drawer-leave-to .ap-history-panel { transform: translateX(100%); }
}
.ap-hist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  border-radius: var(--cpq-radius-md);
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.ap-hist-item:hover {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}
.ap-hist-item.is-current {
  background: var(--cpq-overlay-w8, rgba(255, 255, 255, 0.14));
}
.ap-hist-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.ap-hist-title {
  font-size: 13px;
  color: var(--cpq-text-primary, #f5f7fa);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-hist-meta {
  font-size: 11px;
  color: var(--cpq-text-muted, #9aa4b2);
}
.ap-hist-badge {
  flex: none;
  font-size: 10px;
  color: var(--cpq-accent-primary, #1677ff);
  border: 1px solid var(--cpq-accent-primary, #1677ff);
  border-radius: var(--cpq-radius-sm);
  padding: 0 4px;
}
.ap-hist-del {
  flex: none;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--cpq-radius-sm);
  color: var(--cpq-text-muted, #9aa4b2);
  font-size: 11px;
}
.ap-hist-del:hover {
  background: rgba(255, 77, 79, 0.15);
  color: #ff4d4f;
}
.ap-hist-empty {
  font-size: 12px;
  color: var(--cpq-text-muted, #9aa4b2);
  padding: 10px 8px;
}

/* 两栏消息中心：左联系人 + 右会话 */
.assistant-panel.ap-two-pane {
  flex-direction: row;
}
.ap-contacts {
  width: 280px;
  flex: none;
  min-width: 0;
  border-right: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px 14px 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ap-contacts-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 8px 8px;
}
.ap-contacts-title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--cpq-text-muted, #9aa4b2);
  padding: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-contacts-close {
  width: 26px;
  height: 26px;
  flex: none;
  border: none;
  border-radius: var(--cpq-radius-sm);
  background: transparent;
  color: var(--cpq-text-muted, #9aa4b2);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.ap-contacts-close:hover {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  color: var(--cpq-text-primary, #f5f7fa);
}
.ap-contact {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 6px 8px 8px;
  width: 100%;
  border: none;
  border-radius: var(--cpq-radius-md);
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.ap-contact:hover {
  background: var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
}
.ap-contact.active {
  background: var(--cpq-overlay-w8, rgba(255, 255, 255, 0.14));
}
.ap-contact-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 13px;
  flex: none;
  overflow: visible;
}
.ap-contact-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
}
.ap-contact-avatar--group {
  background: linear-gradient(135deg, #1677ff, #36cfc9);
  font-weight: 600;
}
.ap-contact-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.ap-contact-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #f5f7fa);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ap-role-card--static {
  cursor: default;
}
.ap-role-card--static:hover {
  border-color: transparent;
}
/* 左栏折叠开关：PC 与移动端统一，点击顶部按钮展开/收起 */
.ap-contacts-toggle {
  align-self: center;
  width: 30px;
  height: 30px;
  flex: none;
  border: 1px solid var(--cpq-overlay-w8, rgba(255, 255, 255, 0.12));
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  color: var(--cpq-text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}
.ap-contacts-toggle:hover {
  border-color: var(--cpq-accent-primary, #1677ff);
  color: var(--cpq-accent-primary, #1677ff);
}
.ap-contacts {
  transition: width 0.22s ease, padding 0.22s ease, opacity 0.18s ease;
}
.ap-contacts.is-collapsed {
  width: 0;
  max-width: 0;
  min-width: 0;
  padding: 0;
  border-right: none;
  overflow: hidden;
  opacity: 0;
}

/* 右栏：新增对话 / 会话记录 / 收起（窄条，随视口伸缩） */
.ap-right {
  flex: none;
  width: 44px;
  padding: 10px 6px;
  border-left: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
/* 手机端顶栏动作组：取代右竖条 */
.ap-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

/* 移动端团队抽屉：默认完全收起，展开时从左缘滑出覆盖内容 */
.ap-mobile .ap-contacts {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: auto;
  width: min(260px, 78vw);
  max-width: 320px;
  height: 100%;
  padding: 12px 10px;
  background: var(--cpq-bg-secondary, #ffffff);
  border-left: none;
  border-right: 1px solid var(--cpq-overlay-w6, rgba(255, 255, 255, 0.1));
  box-shadow: 12px 0 32px rgba(0, 0, 0, 0.35);
  z-index: 30;
  transform: translateX(-100%);
  transition: transform 0.26s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease;
}
.ap-mobile .ap-contacts:not(.is-collapsed) {
  transform: translateX(0);
}
.ap-mobile .ap-contacts.is-collapsed {
  display: flex;
  width: min(260px, 78vw);
  max-width: 320px;
  padding: 12px 10px;
  opacity: 1;
  overflow: hidden;
}
.ap-contacts-scrim {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 20;
  transition: opacity 0.22s ease;
}
.ap-fade-enter-active,
.ap-fade-leave-active {
  transition: opacity 0.22s ease;
}
.ap-fade-enter-from,
.ap-fade-leave-to {
  opacity: 0;
}

/* 桌面浮动面板缩放手柄：右缘(宽) / 下缘(高) / 右下角(双向) */
.ap-resize {
  position: absolute;
  z-index: 40;
  touch-action: none;
}
.ap-resize--e {
  top: 0;
  right: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
}
.ap-resize--s {
  left: 0;
  right: 0;
  bottom: 0;
  height: 6px;
  cursor: ns-resize;
}
.ap-resize--se {
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
}
.ap-resize--se::after {
  content: '';
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--cpq-text-muted, #9aa4b2);
  border-bottom: 2px solid var(--cpq-text-muted, #9aa4b2);
  border-radius: var(--cpq-radius-xs);
  opacity: 0.7;
}
.ap-resize--e:hover,
.ap-resize--s:hover {
  background: rgba(22, 119, 255, 0.16);
}
.ap-resize--se:hover::after {
  opacity: 1;
  border-color: var(--cpq-accent-primary, #1677ff);
}

.assistant-panel--embedded {
  flex: 1;
  min-height: 0;
  position: static;
  right: auto;
  bottom: auto;
  width: 100%;
  height: 100%;
  max-height: none;
  border-radius: 0;
  box-shadow: none;
  border: 0;
  z-index: auto;
}

.assistant-panel--embedded .ap-header {
  cursor: default;
}
.assistant-panel--embedded .ap-role-card {
  cursor: default;
}
.assistant-panel--embedded .ap-role-card:hover {
  background: transparent;
}

/* 内嵌(inset)模式：占满父容器、去掉 fixed 浮层，但保留左联系人栏 + 右动作栏（门户聊天态复用）。 */
.assistant-panel--inset {
  flex: 1;
  min-height: 0;
  position: relative;
  right: auto;
  bottom: auto;
  width: 100%;
  height: 100%;
  max-height: none;
  border-radius: 0;
  box-shadow: none;
  border: 0;
  z-index: auto;
}
.assistant-panel--inset .ap-header {
  cursor: default;
}

.ap-header {
  padding: 6px 10px;
  min-height: 36px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: move;
  user-select: none;
  flex: none;
}
.ap-header-spacer {
  flex: 1;
}
/* 聊天头头像可点（查看名片）：悬停出现光环提示 */
.ap-head-avatar--click { cursor: pointer; }
.ap-head-avatar--click:hover { box-shadow: 0 0 0 2px var(--cpq-overlay-a15); }
/* ── 引用回复条（composer 上方）── */
.ap-quote-bar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 12px 4px;
  padding: 4px 10px;
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-w4);
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.ap-quote-text {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-quote-x {
  flex: none;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
}
.ap-quote-x:hover { color: #e5484d; }
/* 装填条上的「填写开工单」动作（试运行预览与正式聊天同款装填条） */
.ap-launch-btn {
  flex: none;
  border: 1px solid var(--cpq-text-muted);
  background: transparent;
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.6;
  padding: 0 8px;
  border-radius: var(--cpq-radius-sm);
}
.ap-launch-btn:hover { color: var(--cpq-text-primary); border-color: var(--cpq-text-secondary); }
/* ── 消息中心侧栏（原型 conv-list）：筛选签/分组/预览/未读/presence ── */
.ap-contact-scroll {
  min-width: 0;
}
.ap-cgroup {
  font-size: 11px;
  color: var(--cpq-text-muted);
  font-weight: 600;
  letter-spacing: 1px;
  padding: 10px 8px 5px;
}
.ap-contact-namerow {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.ap-contact-time {
  flex: none;
  font-size: 11px;
  color: var(--cpq-text-disabled);
}
.ap-contact-preview {
  display: block;
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-unread-dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff6b6b;
}
/* 头像 presence 点（侧栏/聊天头共用；面板接办公室状态流） */
.ap-contact-avatar { position: relative; }
.ap-presence {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #c9cdd4;
  border: 2px solid var(--cpq-bg-secondary, #fff);
}
.ap-presence.on { background: #52c9a0; }
/* ＋ 新建房间：内联输入（回车建，Esc 收） */
.ap-room-add {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 10px;
  margin: 2px 0 6px;
  border: 1px dashed var(--cpq-border-light);
  border-radius: var(--cpq-radius-md);
  background: transparent;
  color: var(--cpq-text-muted);
  font-size: 12px;
  cursor: pointer;
}
.ap-room-add:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
.ap-room-input {
  width: 100%;
  padding: 6px 10px;
  margin: 2px 0 6px;
  border-radius: var(--cpq-radius-md);
  border: 1px solid var(--cpq-accent-primary);
  background: var(--cpq-glass-2-bg);
  color: var(--cpq-text-primary);
  font-size: 12px;
  outline: none;
}
/* ── 聊天头身份区（原型 chat-head）── */
.ap-head-id {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  margin-left: 2px;
}
.ap-head-avatar {
  position: relative;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  background: var(--cpq-accent-primary);
}
.ap-head-main { min-width: 0; }
.ap-head-name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-head-chip {
  flex: none;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: var(--cpq-radius-full);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a10);
  border: 1px solid var(--cpq-overlay-a15);
}
.ap-head-sub {
  font-size: 11px;
  color: var(--cpq-text-muted);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-ctx {
  font-size: 11px;
  color: var(--cpq-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-ctx-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-accent-success, #52c41a);
  flex-shrink: 0;
}
.ap-ctx-none {
  color: var(--cpq-text-muted);
}
.ap-ctx-none .ap-ctx-dot {
  background: var(--cpq-text-muted);
}
.ap-close {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--cpq-text-muted);
  cursor: pointer;
  border-radius: var(--cpq-radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.ap-close:hover {
  background: var(--cpq-overlay-w6);
  color: var(--cpq-text-primary);
}

.ap-threads {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cpq-overlay-w4);
  align-items: center;
}
.ap-thread-select {
  flex: 1;
  min-width: 0;
}
.ap-role-select {
  width: 132px;
  flex-shrink: 0;
}
.thread-opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.thread-opt-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.thread-opt-del {
  color: var(--cpq-text-muted);
  font-size: 12px;
  padding: 2px;
  flex-shrink: 0;
  cursor: pointer;
}
.thread-opt-del:hover {
  color: var(--cpq-accent-danger);
}

.ap-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  min-height: 0;
  scroll-behavior: smooth;
}
.ap-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid var(--cpq-overlay-w4);
}
.ap-quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--cpq-overlay-w15);
  border-radius: var(--cpq-radius-full);
  background: var(--cpq-overlay-w4);
  color: var(--cpq-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--cpq-dur-1) var(--cpq-ease-smooth);
}
.ap-quick-chip:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ap-spin {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
.ap-handoff {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0;
}
.ap-handoff-line {
  flex: 1;
  height: 1px;
  background: var(--cpq-border, rgba(15, 23, 42, 0.08));
}
.ap-handoff-text {
  font-size: 12px;
  color: var(--cpq-text-muted, rgba(15, 23, 42, 0.45));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80%;
}
.ap-msg-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ap-msg {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.ap-msg-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ap-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--cpq-accent-primary, #1677ff);
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
}
.ap-avatar-initial {
  line-height: 1;
}
.ap-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ap-author {
  font-size: 12px;
  line-height: 1.2;
  color: var(--cpq-text-muted);
  margin-bottom: 4px;
}
.role-user {
  justify-content: flex-end;
}
.role-assistant,
.role-system {
  justify-content: flex-start;
}
.ap-bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: var(--cpq-radius-lg);
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
  white-space: pre-wrap;
}
.role-assistant .ap-bubble {
  background: var(--cpq-overlay-w3);
  color: var(--cpq-text-primary);
  border: none;
  border-bottom-left-radius: 4px;
}
.ap-cursor {
  display: inline-block;
  animation: ap-blink 1s steps(2, start) infinite;
  color: var(--cpq-accent-primary);
  margin-left: 1px;
}
@keyframes ap-blink {
  to {
    visibility: hidden;
  }
}
.ap-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 2px 0;
}
.ap-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cpq-text-muted);
  animation: ap-typing-bounce 1.2s infinite ease-in-out;
}
.ap-typing i:nth-child(2) {
  animation-delay: 0.15s;
}
.ap-typing i:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes ap-typing-bounce {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* ── 发送前转接确认 ── */

.ap-input {
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
  display: flex;
  gap: 8px;
  align-items: flex-end;
  background: var(--cpq-overlay-w3);
}

/* ── 需求分析：步骤时间线 ── */
.ap-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 2px 0;
}
.ap-step {
  padding: 2px 8px;
  border-radius: var(--cpq-radius-full);
  font-size: 11px;
  color: var(--cpq-text-muted);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
  white-space: nowrap;
}
.ap-step.st-running {
  color: var(--cpq-accent-primary);
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-step.st-done {
  color: var(--cpq-text-secondary);
}
.ap-step.st-error {
  color: var(--cpq-accent-danger);
  border-color: var(--cpq-accent-danger);
}
/* ── AI 工具调用状态条 ── */
.ap-tool-activity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 2px 0 6px;
}
.ap-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border-radius: var(--cpq-radius-sm);
  font-size: 12px;
  color: var(--cpq-text-secondary);
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
}
.ap-tool .anticon {
  color: var(--cpq-accent-primary);
}
.ap-tool.done .anticon {
  color: var(--cpq-accent-success, #52c41a);
}
.ap-tool-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-tool-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.ap-plan-card {
  max-width: 100%;
}
/* 需求分析结果：文本气泡 + 方案卡纵向堆叠（.ap-msg 默认 row-flex 会把两者并排挤成两栏、且等高拉伸把卡片撑得特别长） */
.ap-msg-result {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.ap-bubble.err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10);
  border-color: var(--cpq-overlay-danger15);
}

/* ── 文件产物卡（PDF 报告等）── */
.ap-file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--cpq-border-light, #d9e2f0);
  border-radius: var(--cpq-radius-md);
  /* bg-glass 是幽灵 token（tokens.css 无定义），fallback #fff 在暗色下白卡刺眼——用一级淡玻璃走双主题 */
  background: var(--cpq-glass-1-bg);
}
/* ── 工作流发起确认卡（suggest_workflow）：标题+理由+需求原文+一键发起 ── */
.ap-wf-card {
  margin-top: var(--cpq-space-2, 8px);
  padding: var(--cpq-space-2, 8px) var(--cpq-space-3, 12px);
  border: 1px solid var(--cpq-border-light, #d9e2f0);
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-glass-1-bg);
  display: flex;
  flex-direction: column;
  gap: var(--cpq-space-1, 4px);
  max-width: 560px;
}
.ap-wf-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #1f2329);
}
.ap-wf-reason {
  font-size: 12px;
  color: var(--cpq-text-secondary, #646a73);
}
.ap-wf-req {
  font-size: 12px;
  color: var(--cpq-text-secondary, #646a73);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow: auto;
}
.ap-wf-btn {
  align-self: flex-start;
  margin-top: var(--cpq-space-1, 4px);
  padding: 4px var(--cpq-space-3, 12px);
  border: none;
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-accent-primary, #1677ff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.ap-wf-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ap-file-icon {
  flex: none;
  min-width: 38px;
  height: 30px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #fff;
  background: #d5453c;
  border-radius: var(--cpq-radius-xs);
}
.ap-file-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ap-file-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #1f2430);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-file-meta {
  font-size: 11.5px;
  color: var(--cpq-text-muted, #8a94a6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ap-file-actions {
  flex: none;
  display: flex;
  gap: 6px;
}
.ap-file-btn {
  border: 1px solid var(--cpq-border-light, #c9d6ea);
  background: transparent;
  border-radius: var(--cpq-radius-sm);
  padding: 3px 10px;
  font-size: 12px;
  color: var(--cpq-accent-primary, #1677ff);
  cursor: pointer;
}
.ap-file-btn:hover {
  background: var(--cpq-overlay-a8);
}

/* ── 文件预览（PDF iframe modal）── */
.ap-file-preview-mask {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
}
.ap-file-preview {
  width: min(760px, 92%);
  height: min(86vh, 760px);
  display: flex;
  flex-direction: column;
  border-radius: var(--cpq-radius-md);
  overflow: hidden;
  background: var(--cpq-bg-secondary, #fff);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.28);
}
.ap-file-preview-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary, #1f2430);
  border-bottom: 1px solid var(--cpq-border-light, #e5eaf3);
}
.ap-file-preview-head button {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--cpq-text-muted, #8a94a6);
  font-size: 14px;
  line-height: 1;
}
.ap-file-preview-frame {
  flex: 1;
  width: 100%;
  border: none;
}


/* ── 需求分析：反问回复区 ── */
.ap-reply-footer {
  flex-shrink: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--cpq-overlay-w8);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ap-reply-q {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--cpq-text-primary);
  white-space: pre-wrap;
}
.ap-format {
  white-space: pre-line;
  padding: 6px 8px;
  background: var(--cpq-overlay-w4);
  border: 1px dashed var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  color: var(--cpq-text-secondary);
}
.ap-reply-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ap-reply-opt {
  cursor: pointer;
  margin: 0;
}
.ap-reply-input {
  border-radius: var(--cpq-radius-sm);
}
.ap-reply-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── 需求分析：LLM 确认面板 ── */
.ap-confirm-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--cpq-overlay-w8);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 45%;
  overflow-y: auto;
}
.ap-confirm-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.ap-confirm-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-a4);
}
.ap-confirm-item.accepted {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
}
.ap-confirm-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}
.ap-confirm-label { font-weight: 600; color: var(--cpq-text-primary); }
.ap-confirm-tag { margin-inline-end: 0 !important; }
.ap-confirm-v { color: var(--cpq-text-secondary); }
.ap-confirm-v.llm { color: var(--cpq-accent-primary); }
.ap-confirm-conf { color: var(--cpq-text-muted); }
.ap-confirm-opts { display: flex; gap: 6px; flex-shrink: 0; }
.ap-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

/* ── 网页端增强：BOM 弹窗 ── */
.ap-bom-modal-summary {
  font-size: 12px;
  color: var(--cpq-text-secondary);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--cpq-overlay-w8);
  margin-bottom: 12px;
}
/* 弹窗要在方案助手面板(z-index:1500)之上；内容超高时弹窗内部滚动，不撑破视口 */
.ap-bom-modal :deep(.ant-modal-body) {
  max-height: 70vh;
  overflow-y: auto;
}
.ap-quick-chip.primary {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-accent-soft);
  font-weight: 600;
}
.ap-quick-chip.primary:hover:not(:disabled) {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8);
}
.ap-quick-chip.primary.active {
  border-color: var(--cpq-accent-primary);
  background: var(--cpq-accent-primary);
  color: #fff;
}

/* ── 方案助手改版：角色卡 + 内部角色菜单 + 内部会话抽屉 ── */
.ap-header {
  padding: 12px;
  border-bottom: 1px solid var(--cpq-overlay-w6);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: move;
  user-select: none;
  background: transparent;
}
.ap-role-card {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border: 0;
  border-radius: var(--cpq-radius-lg);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.ap-role-card:hover {
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
}
.ap-role-avatar {
  width: 44px;
  height: 44px;
  border-radius: var(--cpq-radius-lg);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-weight: 700;
  font-size: 17px;
  background: var(--cpq-accent-primary, #1677ff);
}
.ap-role-avatar.sm {
  width: 34px;
  height: 34px;
  border-radius: var(--cpq-radius-md);
  font-size: 13px;
}
.ap-role-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.ap-role-meta {
  min-width: 0;
}
.ap-role-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ap-role-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cpq-accent-success, #22c55e);
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.12);
  flex-shrink: 0;
}
.ap-role-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--cpq-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-role-desc {
  margin-top: 4px;
  font-size: 11px;
  color: var(--cpq-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-role-ctx {
  margin-top: 3px;
  font-size: 11px;
  color: var(--cpq-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-icon-btn {
  width: 34px;
  height: 34px;
  border: 1px solid var(--cpq-overlay-w10, rgba(255, 255, 255, 0.12));
  border-radius: var(--cpq-radius-md);
  display: grid;
  place-items: center;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.08));
  color: var(--cpq-text-muted);
  cursor: pointer;
  font-size: 14px;
}
.ap-icon-btn:hover {
  border-color: var(--cpq-accent-primary);
  color: var(--cpq-accent-primary);
  background: var(--cpq-overlay-a8, rgba(22, 119, 255, 0.10));
}
.ap-close:hover {
  border-color: var(--cpq-accent-danger);
  color: var(--cpq-accent-danger);
  background: var(--cpq-overlay-danger10, rgba(255, 77, 79, 0.10));
}

.assistant-panel-enter-active,
.assistant-panel-leave-active {
  transition: opacity 0.25s ease, transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.assistant-panel-enter-from,
.assistant-panel-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}

<style>
/* 启动表单弹窗 teleport 到 body，需非 scoped：层级压过办公室聊天面板(1800)/方案助手面板(1500) */
.launch-modal-wrap { z-index: 2000; }
.launch-modal-full .ant-modal { max-width: 100vw; top: 0; padding-bottom: 0; }
.launch-modal-full .ant-modal-content { border-radius: 0; min-height: 100vh; }
</style>

<style>
/* BOM 弹窗是 Teleport 到 body 的 a-modal 内部 DOM，scoped 样式覆盖不到，用全局类收口 */
.ap-bom-modal .ant-modal-body {
  max-height: 70vh;
  overflow-y: auto;
}
</style>
