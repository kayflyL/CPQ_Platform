<template>
  <div class="aom-root">
    <header class="aom-header">
      <div class="aom-heading">
        <h2>AI 办公室管理</h2>
        <span class="aom-subtitle">员工、团队、空间、Skill Studio、模型与运行治理</span>
      </div>
      <nav class="aom-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="aom-nav-item"
          :class="{ active: activeNav === item.key }"
          @click="activeNav = item.key"
        >
          {{ item.label }}
        </button>
      </nav>
      <div class="aom-actions">
        <a-button v-if="canSaveCurrent" type="primary" @click="saveCurrent">保存当前</a-button>
        <a-button type="text" @click="emit('close')">关闭</a-button>
      </div>
    </header>

    <div class="aom-body" :class="{ 'aom-body--editor': activeNav === 'capability' && editingSkill }">
      <template v-if="activeNav === 'employee'">
        <a-tabs v-model:activeKey="employeeTab" class="aom-inner-tabs">
          <a-tab-pane key="profile" tab="员工配置">
            <EmployeeManager
              ref="employeeManagerRef"
              :colleagues="colleagues"
              :initial-role-key="initialRoleKey"
              @saved="emit('saved')"
            />
          </a-tab-pane>
          <a-tab-pane key="behavior" tab="行为配置">
            <OfficeBehaviorEditor
              ref="behaviorEditorRef"
              :behavior-config="behaviorConfig"
              :office-config="officeConfig"
              @saved="emit('saved')"
            />
          </a-tab-pane>
        </a-tabs>
      </template>

      <TeamManager
        v-else-if="activeNav === 'team'"
        ref="teamManagerRef"
        embedded
        :initial-editor-tab="'team'"
        :colleagues="colleagues"
        :rooms="rooms"
        :team-meta="teamMeta"
        :layout-nodes="layoutNodes"
        :layout-edges="layoutEdges"
        :office-config="officeConfig"
        :behavior-config="behaviorConfig"
        :initial-role-key="initialRoleKey"
        :lead-role-key="leadRoleKey"
        @saved="emit('saved')"
      />

      <div v-else-if="activeNav === 'capability'" class="aom-panel">
        <div v-if="editingSkill" class="aom-legacy-editor">
          <div class="aom-legacy-head">
            <a-button size="small" @click="editingSkill = null">← 返回 Skill Studio</a-button>
            <span>{{ editingSkill.name || editingSkill.key }}</span>
          </div>
          <div class="aom-legacy-body">
            <SkillStudio :skill="editingSkill" />
          </div>
        </div>
        <a-tabs v-else v-model:activeKey="capabilityTab" class="aom-inner-tabs">
          <a-tab-pane key="skills" tab="Skills">
            <div class="aom-section-head">
              <div>
                <h3>Skills</h3>
                <span class="aom-hint">能力包：静默增强 AI 角色，模型按描述判断调用；无节点画布。</span>
              </div>
            </div>
            <a-spin :spinning="skillsLoading">
              <div class="aom-skill-grid">
                <div v-for="skill in capabilitySkills" :key="skill.key" class="aom-skill-cell">
                  <CapabilityCard :skill="skill" @detail="openSkill" />
                  <div class="aom-skill-actions">
                    <a-button type="text" size="small" @click="openPolicy(skill)">调用策略</a-button>
                    <a-button type="text" size="small" @click="openSkill(skill)">编辑</a-button>
                    <a-button type="text" size="small" danger @click="removeSkill(skill)">删除</a-button>
                  </div>
                </div>
              </div>
            </a-spin>
          </a-tab-pane>
          <a-tab-pane key="workflows" tab="Workflows">
            <div class="aom-section-head">
              <div>
                <h3>Workflows</h3>
                <span class="aom-hint">任务流：可见多步编排，用户通过“+”或模型建议显式发起；点击进入节点画布。</span>
              </div>
            </div>
            <a-spin :spinning="skillsLoading">
              <div class="aom-skill-grid">
                <div v-for="skill in workflowSkills" :key="skill.key" class="aom-skill-cell">
                  <CapabilityCard :skill="skill" @detail="openSkill" />
                  <div class="aom-skill-actions">
                    <a-button type="text" size="small" @click="openPolicy(skill)">调用策略</a-button>
                    <a-button type="text" size="small" @click="openSkill(skill)">编辑</a-button>
                    <a-button type="text" size="small" danger @click="removeSkill(skill)">删除</a-button>
                  </div>
                </div>
              </div>
            </a-spin>
          </a-tab-pane>
          <a-tab-pane v-if="canAdmin" key="tools" tab="工具目录">
            <AiSettingsPanel embedded section="tools" />
          </a-tab-pane>
        </a-tabs>
      </div>

      <div v-else-if="activeNav === 'model'" class="aom-panel">
        <AiSettingsPanel embedded section="model" />
      </div>

      <div v-else-if="activeNav === 'runtime'" class="aom-panel">
        <a-tabs v-model:activeKey="runtimeTab" class="aom-inner-tabs">
          <a-tab-pane key="audit" tab="审计 / 绩效">
            <AiSettingsPanel embedded section="audit" />
          </a-tab-pane>
          <a-tab-pane key="threads" tab="会话记录">
            <AiSettingsPanel embedded section="threads" />
          </a-tab-pane>
          <a-tab-pane key="access" tab="账户与权限">
            <AiSettingsPanel embedded section="access" />
          </a-tab-pane>
        </a-tabs>
      </div>

      <SkillRoutePolicyModal
        :open="policySkill !== null"
        :skill="policySkill"
        @close="policySkill = null"
        @saved="onPolicySaved"
      />
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { officeApi, type BehaviorConfig, type OfficeConfig } from '@/api/office'
import { useAuthStore } from '@/store/auth'
import TeamManager from './TeamManager.vue'
import EmployeeManager from './EmployeeManager.vue'
import OfficeBehaviorEditor from './OfficeBehaviorEditor.vue'
import AiSettingsPanel from './AiSettingsPanel.vue'
import CapabilityCard from '@/components/office/CapabilityCard.vue'
import SkillRoutePolicyModal from '@/components/office/SkillRoutePolicyModal.vue'
import SkillStudio from '../admin/reasoning/SkillStudio.vue'

const props = defineProps<{
  colleagues: any[]
  rooms: any[]
  teamMeta: { name?: string; description?: string; color?: string }
  layoutNodes: any[]
  layoutEdges: any[]
  officeConfig?: OfficeConfig
  behaviorConfig?: BehaviorConfig
  initialRoleKey?: string | null
  leadRoleKey?: string | null
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

type NavKey = 'employee' | 'team' | 'capability' | 'model' | 'runtime'
const auth = useAuthStore()
const canManage = computed(() => auth.can('ai.office.manage'))
const canAdmin = computed(() => auth.can('ai.office.admin'))
const navItems = computed<Array<{ key: NavKey; label: string }>>(() => {
  const items: Array<{ key: NavKey; label: string }> = []
  if (canManage.value) {
    items.push({ key: 'employee', label: '员工' })
    items.push({ key: 'team', label: '团队' })
    items.push({ key: 'capability', label: 'Skill Studio' })
  }
  if (canAdmin.value) {
    items.push({ key: 'model', label: '模型与接入' })
    items.push({ key: 'runtime', label: '运行与权限' })
  }
  return items
})

const activeNav = ref<NavKey>('employee')
const employeeTab = ref('profile')
const capabilityTab = ref('skills')
const runtimeTab = ref('audit')
const employeeManagerRef = ref<any>(null)
const behaviorEditorRef = ref<any>(null)
const teamManagerRef = ref<any>(null)
const skills = ref<any[]>([])
const skillsLoading = ref(false)
const editingSkill = ref<any | null>(null)
const policySkill = ref<any | null>(null)
const capabilitySkills = computed(() => skills.value.filter((s: any) => s?.type !== 'workflow'))
const workflowSkills = computed(() => skills.value.filter((s: any) => s?.type === 'workflow'))

function openPolicy(skill: any) {
  policySkill.value = skill
}

function onPolicySaved(updated: any) {
  const index = skills.value.findIndex((item) => item.key === updated?.key)
  if (index >= 0) skills.value[index] = { ...skills.value[index], ...updated }
}

function openSkill(skill: any) {
  if (skill?.type === 'workflow' || skill?.workflow_key) {
    editingSkill.value = skill
    return
  }
  message.info('能力包 Skill 无需节点画布：它在角色提示里静默生效，绑定到员工后由模型按描述调用')
}

function removeSkill(skill: any) {
  Modal.confirm({
    title: `删除 Skill“${skill.name || skill.key}”？`,
    content: '删除后将从 Skill Studio 移除，并解除员工侧对它的绑定。',
    okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      try {
        await officeApi.deleteSkill(skill.key)
        if (editingSkill.value?.key === skill.key) editingSkill.value = null
        message.success('已删除')
        await loadSkills()
      } catch (error: any) {
        message.error(error?.response?.data?.detail || '删除失败')
      }
    },
  })
}


const canSaveCurrent = computed(() => activeNav.value === 'employee' || activeNav.value === 'team')

async function loadSkills() {
  skillsLoading.value = true
  try {
    skills.value = await officeApi.listSkills()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || 'Skill Studio 加载失败')
  } finally {
    skillsLoading.value = false
  }
}

function saveCurrent() {
  if (activeNav.value === 'employee') {
    if (employeeTab.value === 'behavior') behaviorEditorRef.value?.save()
    else employeeManagerRef.value?.save()
  } else if (activeNav.value === 'team') {
    teamManagerRef.value?.save()
  }
}

onMounted(loadSkills)
</script>

<style scoped>
.aom-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--cpq-bg-primary);
}

.aom-header {
  min-height: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--cpq-border-secondary, rgba(255,255,255,0.08));
}

.aom-heading h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--cpq-text-primary);
}

.aom-subtitle {
  display: block;
  margin-top: 2px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.aom-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.aom-nav-item {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: var(--cpq-text-secondary);
  padding: 8px 12px;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
}

.aom-nav-item:hover {
  background: var(--cpq-overlay-w6, rgba(255,255,255,0.06));
}

.aom-nav-item.active {
  color: var(--cpq-accent-primary, #1677ff);
  background: var(--cpq-overlay-a12, rgba(22,119,255,0.12));
  font-weight: 700;
}

.aom-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.aom-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px 20px 24px;
}

.aom-body--editor {
  overflow: hidden;
  padding: 12px 20px 20px;
}

.aom-body--editor .aom-panel {
  height: 100%;
}

.aom-legacy-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.aom-legacy-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 10px;
  color: var(--cpq-text-secondary);
}

.aom-legacy-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--cpq-border-secondary);
  border-radius: var(--cpq-radius-md);
  background: var(--cpq-bg-primary);
}

.aom-panel {
  min-height: 0;
}

.aom-inner-tabs {
  height: 100%;
}

.aom-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.aom-section-head h3 {
  margin: 0;
  font-size: 15px;
  color: var(--cpq-text-primary);
}

.aom-hint {
  display: block;
  margin-top: 4px;
  color: var(--cpq-text-muted);
  font-size: 12px;
}

.aom-skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.aom-skill-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.aom-skill-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

.aom-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
</style>
