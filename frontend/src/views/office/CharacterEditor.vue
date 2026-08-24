<template>
  <div class="character-editor">
    <div class="ce-toolbar">
      <div>
        <h3>角色人格</h3>
        <p>编辑 AI 同事的人格、记忆、情绪、日程、关系和偏好，全部写入团队配置。</p>
      </div>
    </div>

    <div class="ce-layout">
      <aside class="ce-list">
        <div class="ce-list-title">AI 同事</div>
        <button
          v-for="colleague in colleagues"
          :key="colleague.role_key"
          class="ce-member"
          :class="{ active: colleague.role_key === selectedRoleKey }"
          type="button"
          @click="selectColleague(colleague.role_key)"
        >
          <span class="ce-member-dot" :style="{ background: colleague.color || '#1677ff' }"></span>
          <span class="ce-member-name">{{ colleague.name || colleague.role_key }}</span>
          <span class="ce-member-role">{{ colleague.role_key }}</span>
        </button>
      </aside>

      <section class="ce-form">
        <template v-if="draft">
          <div class="ce-card">
            <div class="ce-card-title">人格</div>
            <label class="ce-field">
              <span>System Prompt</span>
              <a-textarea v-model:value="draft.system_prompt" :auto-size="{ minRows: 4, maxRows: 10 }" placeholder="例如：耐心、擅长澄清需求" />
            </label>
          </div>

          <div class="ce-card">
            <div class="ce-card-title">行为偏好</div>
            <div class="ce-grid">
              <label class="ce-check">
                <a-switch v-model:checked="draft.behavior_profile.wander_enabled" />
                允许自主走动
              </label>
              <label class="ce-field">
                <span>最短空闲秒</span>
                <a-input-number v-model:value="draft.behavior_profile.min_idle_seconds" :min="1" :step="1" />
              </label>
              <label class="ce-field">
                <span>最长空闲秒</span>
                <a-input-number v-model:value="draft.behavior_profile.max_idle_seconds" :min="1" :step="1" />
              </label>
            </div>
            <div class="ce-card-title">偏好区域</div>
            <div v-for="(zone, index) in draft.behavior_profile.preferred_zones" :key="index" class="ce-grid">
              <label class="ce-field">
                <span>区域</span>
                <a-input v-model:value="zone.zone" />
              </label>
              <label class="ce-field">
                <span>权重</span>
                <a-input-number v-model:value="zone.weight" :min="0" :step="5" />
              </label>
              <label class="ce-field">
                <span>活动</span>
                <a-input v-model:value="zone.activity" />
              </label>
              <a-button size="small" danger @click="removePreferredZone(Number(index))">删除</a-button>
            </div>
            <a-button size="small" @click="addPreferredZone">添加偏好区域</a-button>

            <div class="ce-card-title">空闲动作</div>
            <a-select
              v-model:value="draft.behavior_profile.preferred_idle_actions"
              mode="tags"
              :options="idleActionOptions"
              style="width: 100%"
              placeholder="如 sit_idle, look_around"
            />
          </div>

          <div class="ce-card">
            <div class="ce-card-title">记忆</div>
            <div class="ce-grid">
              <label class="ce-field">
                <span>短期记忆 TTL（秒）</span>
                <a-input-number v-model:value="draft.memory.short_term_ttl_seconds" :min="60" :step="60" />
              </label>
              <label class="ce-field">
                <span>长期记忆仓库</span>
                <a-input v-model:value="draft.memory.long_term_store" />
              </label>
            </div>
          </div>

          <div class="ce-card">
            <div class="ce-card-title">情绪</div>
            <div class="ce-grid">
              <label class="ce-check">
                <a-switch v-model:checked="draft.mood.enabled" />
                启用情绪模型
              </label>
              <label class="ce-field">
                <span>当前状态</span>
                <a-input v-model:value="draft.mood.state" />
              </label>
              <label class="ce-field">
                <span>衰减时间（秒）</span>
                <a-input-number v-model:value="draft.mood.decay_seconds" :min="60" :step="60" />
              </label>
            </div>
          </div>

          <div class="ce-card">
            <div class="ce-card-title">日程</div>
            <div class="ce-grid">
              <label class="ce-field">
                <span>时区</span>
                <a-input v-model:value="draft.schedule.timezone" />
              </label>
              <label class="ce-field">
                <span>工作时段</span>
                <a-input v-model:value="draft.schedule.work_hours" />
              </label>
              <label class="ce-field">
                <span>偏好会议时间</span>
                <a-input v-model:value="draft.schedule.preferred_meeting_time" />
              </label>
            </div>
          </div>

          <div class="ce-card">
            <div class="ce-card-title">关系</div>
            <div class="ce-grid">
              <label class="ce-field">
                <span>默认关系</span>
                <a-input v-model:value="draft.relations.default" />
              </label>
              <label class="ce-field">
                <span>协作同事</span>
                <a-input v-model:value="peersText" placeholder="多个角色用逗号分隔" />
              </label>
            </div>
          </div>

          <div class="ce-card">
            <div class="ce-card-title">偏好</div>
            <div class="ce-grid">
              <label class="ce-check">
                <a-switch v-model:checked="draft.preferences.prefers_async" />
                偏好异步协作
              </label>
              <label class="ce-field">
                <span>会议最长分钟</span>
                <a-input-number v-model:value="draft.preferences.meeting_max_minutes" :min="5" :step="5" />
              </label>
            </div>
          </div>
        </template>

        <div v-else class="ce-empty">选择左侧同事进行编辑</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi } from '@/api/office'

const props = defineProps<{
  colleagues: any[]
  initialRoleKey?: string | null
}>()
const emit = defineEmits<{ saved: [] }>()

const selectedRoleKey = ref<string | null>(props.initialRoleKey || props.colleagues[0]?.role_key || null)
const saving = ref(false)
const draft = ref<any>(null)
const peersText = ref('')
const idleActionOptions = ['sit_idle', 'look_around', 'check_notes', 'window', 'stand', 'wave'].map((value) => ({ value, label: value }))

const selectedColleague = computed(() =>
  props.colleagues.find((colleague) => colleague.role_key === selectedRoleKey.value) || null,
)

function cloneDraft(colleague: any) {
  const source = JSON.parse(JSON.stringify(colleague || {}))
  draft.value = {
    role_key: source.role_key,
    name: source.name || source.role_key,
    system_prompt: source.system_prompt || '',
    behavior_profile: {
      wander_enabled: source.behavior_profile?.wander_enabled ?? true,
      min_idle_seconds: source.behavior_profile?.min_idle_seconds ?? 8,
      max_idle_seconds: source.behavior_profile?.max_idle_seconds ?? 20,
      preferred_zones: Array.isArray(source.behavior_profile?.preferred_zones)
        ? JSON.parse(JSON.stringify(source.behavior_profile.preferred_zones))
        : [
            { zone: 'desk_zone', weight: 55, activity: '在工位整理工作' },
            { zone: 'public_zone', weight: 30, activity: '去公共区看看' },
            { zone: 'meeting_room', weight: 15, activity: '去会议室整理资料' },
          ],
      preferred_idle_actions: Array.isArray(source.behavior_profile?.preferred_idle_actions)
        ? [...source.behavior_profile.preferred_idle_actions]
        : ['sit_idle', 'look_around', 'check_notes'],
    },
    memory: {
      short_term_ttl_seconds: source.memory?.short_term_ttl_seconds ?? 3600,
      long_term_store: source.memory?.long_term_store || 'office_memory',
    },
    mood: {
      enabled: source.mood?.enabled ?? true,
      state: source.mood?.state || 'calm',
      decay_seconds: source.mood?.decay_seconds ?? 900,
    },
    schedule: {
      timezone: source.schedule?.timezone || 'Asia/Shanghai',
      work_hours: source.schedule?.work_hours || '09:00-18:00',
      preferred_meeting_time: source.schedule?.preferred_meeting_time || '10:00-11:30',
    },
    relations: {
      default: source.relations?.default || 'colleague',
      peers: Array.isArray(source.relations?.peers) ? source.relations.peers : [],
    },
    preferences: {
      prefers_async: source.preferences?.prefers_async ?? true,
      meeting_max_minutes: source.preferences?.meeting_max_minutes ?? 25,
    },
  }
  peersText.value = draft.value.relations.peers.join(', ')
}

function selectColleague(roleKey: string) {
  selectedRoleKey.value = roleKey
}

watch(selectedColleague, (colleague) => {
  if (!colleague) {
    draft.value = null
    peersText.value = ''
    return
  }
  cloneDraft(colleague)
}, { immediate: true })

watch(
  () => props.colleagues,
  (colleagues) => {
    if (!colleagues.find((colleague) => colleague.role_key === selectedRoleKey.value)) {
      selectedRoleKey.value = colleagues[0]?.role_key || null
    }
  },
  { immediate: true, deep: true },
)

async function save() {
  if (!draft.value?.role_key) return
  saving.value = true
  try {
    await officeApi.updateColleague(draft.value.role_key, {
      name: draft.value.name,
      system_prompt: draft.value.system_prompt,
      behavior_profile: draft.value.behavior_profile,
      memory: draft.value.memory,
      mood: draft.value.mood,
      schedule: draft.value.schedule,
      relations: {
        default: draft.value.relations.default,
        peers: peersText.value
          .split(/[,，]/)
          .map((item) => item.trim())
          .filter(Boolean),
      },
      preferences: draft.value.preferences,
    })
    message.success(`已保存 ${draft.value.role_key}`)
    emit('saved')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '角色人格保存失败')
  } finally {
    saving.value = false
  }
}

function addPreferredZone() {
  draft.value.behavior_profile.preferred_zones.push({ zone: 'public_zone', weight: 20, activity: '去公共区看看' })
}

function removePreferredZone(index: number) {
  draft.value.behavior_profile.preferred_zones.splice(index, 1)
}

defineExpose({ save })
</script>

<style scoped>
.character-editor {
  padding: 16px;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ce-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.ce-toolbar h3 {
  margin: 0;
  font-size: 18px;
}

.ce-toolbar p {
  margin: 4px 0 0;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.ce-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 12px;
}

.ce-list {
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 10px;
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.03));
}

.ce-list-title {
  margin-bottom: 8px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.ce-member {
  width: 100%;
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 9px 8px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--cpq-text-primary);
  text-align: left;
  cursor: pointer;
}

.ce-member:hover {
  background: var(--cpq-overlay-a10, rgba(22,119,255,0.10));
}

.ce-member.active {
  background: var(--cpq-overlay-a15, rgba(22,119,255,0.16));
}

.ce-member-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.ce-member-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ce-member-role {
  font-size: 10px;
  color: var(--cpq-text-muted);
  font-family: ui-monospace, monospace;
}

.ce-form {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ce-card {
  border: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 12px;
  background: var(--cpq-bg-secondary, rgba(255,255,255,0.04));
}

.ce-card-title {
  margin-bottom: 10px;
  color: var(--cpq-text-secondary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.ce-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: 10px;
}

.ce-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--cpq-text-muted);
  font-size: 11px;
}

.ce-check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--cpq-text-secondary);
  font-size: 12px;
}

.ce-empty {
  margin: auto;
  color: var(--cpq-text-muted);
  font-size: 13px;
}
</style>
