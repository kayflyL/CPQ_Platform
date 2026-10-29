<script setup lang="ts">
/**
 * AI 角色访问权限面板（『同事 → 访问权限』页签，页面级配置对全部同事生效）。
 * 1) 价格可见性：按 AI 角色开关（价格机密，默认关闭）；关闭后该角色的对话与产物不出现价格。
 * 2) 角色访问控制：团队隔离 + 角色→AI角色规则 + 未匹配默认 + 用户例外。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { officeApi, type OfficeAccessPolicy } from '@/api/office'

const props = defineProps<{ colleagues: any[] }>()
const emit = defineEmits<{ (e: 'saved'): void }>()

// ── 价格可见性 ──
const priceMap = ref<Record<string, boolean>>({})

function syncPriceMap() {
  const next: Record<string, boolean> = {}
  for (const c of props.colleagues || []) next[c.role_key] = Boolean(c.price_access)
  priceMap.value = next
}
watch(() => props.colleagues, syncPriceMap, { immediate: true, deep: true })

// ── 角色访问控制 ──
const policyEnabled = ref(true)
const defaultKeys = ref<string[]>(['assistant'])
const roleRows = ref<Array<{ role_key: string; colleague_keys: string[] }>>([])
const userRows = ref<Array<{ user_key: string; colleague_keys: string[] }>>([])
const roles = ref<Array<{ role_key: string; name: string }>>([])
const users = ref<any[]>([])
const saving = ref(false)

const roleOptions = computed(() => roles.value.map((r) => ({ value: r.role_key, label: r.name || r.role_key })))
const colleagueOptions = computed(() =>
  (props.colleagues || []).map((c) => ({ value: c.role_key, label: `${c.name || c.role_key} (${c.role_key})` })),
)
const userOptions = computed(() =>
  users.value.map((u) => ({ value: u.user_id, label: `${u.name}${u.role ? ` (${u.role})` : ''}` })),
)

function toKeys(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : []
}

async function load() {
  const [rolesData, usersData, admin] = await Promise.all([
    officeApi.teamRoles().catch(() => ({ roles: [] })),
    officeApi.listUsers().catch(() => ({ users: [] })),
    officeApi.teamConfigAdmin().catch(() => null),
  ])
  roles.value = Array.isArray((rolesData as any)?.roles) ? (rolesData as any).roles : []
  users.value = Array.isArray((usersData as any)?.users)
    ? (usersData as any).users.filter((u: any) => u.is_active !== false)
    : []
  const policy = (admin as any)?.access_policy
  policyEnabled.value = policy?.enabled ?? true
  defaultKeys.value = Array.isArray(policy?.default_chat_role_keys) ? [...policy.default_chat_role_keys] : ['assistant']
  roleRows.value = Object.entries(policy?.role_chat_role_keys || {}).map(([role_key, value]) => ({
    role_key,
    colleague_keys: toKeys(value),
  }))
  userRows.value = Object.entries(policy?.user_chat_role_keys || {}).map(([user_key, value]) => ({
    user_key,
    colleague_keys: toKeys(value),
  }))
}

async function save() {
  saving.value = true
  try {
    const role_chat_role_keys: Record<string, string[]> = {}
    for (const row of roleRows.value) {
      const k = row.role_key.trim()
      if (k) role_chat_role_keys[k] = [...row.colleague_keys]
    }
    const user_chat_role_keys: Record<string, string[]> = {}
    for (const row of userRows.value) {
      const k = row.user_key.trim()
      if (k) user_chat_role_keys[k] = [...row.colleague_keys]
    }
    const payload: OfficeAccessPolicy = {
      enabled: policyEnabled.value,
      default_chat_role_keys: [...defaultKeys.value],
      role_chat_role_keys,
      user_chat_role_keys,
    }
    await officeApi.updateAccessPolicy(payload)
    for (const c of props.colleagues || []) {
      const want = Boolean(priceMap.value[c.role_key])
      if (Boolean(c.price_access) !== want) {
        await officeApi.updateColleague(c.role_key, { price_access: want })
      }
    }
    message.success('AI 角色访问权限已保存')
    emit('saved')
    await load()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="cap-root">
    <div class="cap-head">
      <div class="cap-head-text">
        <span class="cap-title">AI 角色访问权限</span>
        <span class="cap-desc">控制每个 AI 角色能否查看价格，以及哪些账号可以使用各 AI 角色。</span>
      </div>
      <a-button type="primary" size="small" :loading="saving" @click="save">保存权限</a-button>
    </div>

    <div class="set-cards">
      <!-- 价格可见性：每同事一行开关 -->
      <div class="set-card">
        <div class="set-head">
          <div class="set-head-text">
            <span class="set-name">价格可见性</span>
            <span class="set-desc">价格机密，默认关闭；关闭后该角色的对话与产物不出现价格。</span>
          </div>
        </div>
        <div v-for="c in colleagues" :key="c.role_key" class="set-row">
          <span class="set-label" :class="{ 'is-off': !priceMap[c.role_key] }">{{ c.name || c.role_key }}</span>
          <span class="set-inline">
            <span class="set-unit">{{ priceMap[c.role_key] ? '对话中可查看价格' : '全程隐藏价格' }}</span>
            <a-switch v-model:checked="priceMap[c.role_key]" size="small" />
          </span>
        </div>
      </div>

      <!-- 团队隔离：卡头开关 + 规则卡内行 + 添加钮 + 未匹配默认 -->
      <div class="set-card set-card--wide">
        <div class="set-head">
          <a-switch v-model:checked="policyEnabled" size="small" />
          <div class="set-head-text">
            <span class="set-name">启用团队隔离</span>
            <span class="set-desc">开启后，只有下面映射到的 AI 角色会出现在对应用户的门户、浮动窗和 AI 办公室中；关闭后所有人可访问全部 AI 角色。</span>
          </div>
        </div>
        <div class="set-rule" v-for="(row, index) in roleRows" :key="`role-${index}`">
          <div class="set-rule-fields">
            <a-select
              v-model:value="row.role_key"
              size="small"
              :options="roleOptions"
              placeholder="选择系统角色"
              show-search
              class="set-select"
            />
            <a-select
              v-model:value="row.colleague_keys"
              mode="multiple"
              size="small"
              class="set-select set-select--grow"
              :options="colleagueOptions"
              placeholder="选择 AI 角色"
              allow-clear
            />
          </div>
          <a-button class="set-rule-del" size="small" danger type="text" @click="roleRows.splice(index, 1)">删除</a-button>
        </div>
        <div class="set-add">
          <a-button block size="small" type="dashed" @click="roleRows.push({ role_key: '', colleague_keys: [] })">新增角色规则</a-button>
        </div>
        <div class="set-row">
          <span class="set-label">未匹配角色默认</span>
          <a-select
            v-model:value="defaultKeys"
            mode="multiple"
            size="small"
            :options="colleagueOptions"
            placeholder="未匹配到角色规则时可访问的 AI 角色"
            allow-clear
            class="set-select set-select--grow"
          />
        </div>
      </div>

      <!-- 用户例外：低频高级配置，折叠 -->
      <div class="set-card set-card--wide">
        <a-collapse ghost class="cap-user-exceptions">
          <a-collapse-panel key="user" header="用户例外（高级，按需覆盖）">
            <div class="set-rule" v-for="(row, index) in userRows" :key="`user-${index}`">
              <div class="set-rule-fields">
                <a-select
                  v-model:value="row.user_key"
                  size="small"
                  class="set-select"
                  :options="userOptions"
                  show-search
                  option-filter-prop="label"
                  placeholder="选择用户"
                />
                <a-select
                  v-model:value="row.colleague_keys"
                  mode="multiple"
                  size="small"
                  class="set-select set-select--grow"
                  :options="colleagueOptions"
                  placeholder="选择 AI 角色"
                  allow-clear
                />
              </div>
              <a-button class="set-rule-del" size="small" danger type="text" @click="userRows.splice(index, 1)">删除</a-button>
            </div>
            <div class="set-add">
              <a-button block size="small" type="dashed" @click="userRows.push({ user_key: '', colleague_keys: [] })">新增用户例外</a-button>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 外层透明容器：卡片是唯一玻璃层（set-card 样式在全局 styles/settings.css，规范 §5 设置类界面） */
.cap-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cap-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.cap-head-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.cap-title {
  font-size: var(--cpq-font-size-base);
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.cap-desc {
  font-size: var(--cpq-font-size-sm);
  color: var(--cpq-text-muted);
}
.cap-user-exceptions {
  margin-top: 0;
}
.cap-user-exceptions :deep(.ant-collapse-header) {
  padding: 10px 0;
  color: var(--cpq-text-secondary);
  font-size: 12.5px;
}
</style>
