<script setup lang="ts">
/**
 * AI 角色访问权限面板（『员工 → 访问权限』页签，页面级配置对全部同事生效）。
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
      <div>
        <div class="cap-title">AI 角色访问权限</div>
        <div class="cap-help">控制每个 AI 角色能否查看价格，以及哪些账号可以使用各 AI 角色。</div>
      </div>
      <a-button type="primary" size="small" :loading="saving" @click="save">保存权限</a-button>
    </div>

    <div class="cap-section">价格可见性（价格机密，默认关闭）</div>
    <div class="cap-price-grid">
      <div v-for="c in colleagues" :key="c.role_key" class="cap-price-row">
        <a-switch v-model:checked="priceMap[c.role_key]" size="small" />
        <span class="cap-price-name" :class="{ 'is-off': !priceMap[c.role_key] }">{{ c.name || c.role_key }}</span>
        <span class="cap-price-hint">{{ priceMap[c.role_key] ? '对话中可查看价格' : '全程隐藏价格' }}</span>
      </div>
    </div>

    <a-divider class="cap-divider" />

    <div class="cap-line">
      <span>启用团队隔离</span>
      <a-switch v-model:checked="policyEnabled" size="small" />
    </div>
    <div class="cap-help">
      开启后，只有下面映射到的 AI 角色会出现在对应用户的门户、浮动窗和 AI 办公室中；关闭后所有人可访问全部 AI 角色。
    </div>

    <label class="cap-label">角色 → AI 角色</label>
    <div v-for="(row, index) in roleRows" :key="`role-${index}`" class="cap-row">
      <a-select
        v-model:value="row.role_key"
        size="small"
        :options="roleOptions"
        placeholder="选择系统角色"
        show-search
      />
      <a-select
        v-model:value="row.colleague_keys"
        mode="multiple"
        size="small"
        class="cap-keys"
        :options="colleagueOptions"
        placeholder="选择 AI 角色"
        allow-clear
      />
      <a-button type="text" size="small" danger @click="roleRows.splice(index, 1)">删除</a-button>
    </div>
    <a-button block size="small" type="dashed" @click="roleRows.push({ role_key: '', colleague_keys: [] })">
      新增角色规则
    </a-button>

    <label class="cap-label">未匹配角色默认</label>
    <a-select
      v-model:value="defaultKeys"
      mode="multiple"
      size="small"
      style="width: 100%"
      :options="colleagueOptions"
      placeholder="未匹配到角色规则时可访问的 AI 角色"
      allow-clear
    />

    <a-collapse ghost class="cap-user-exceptions">
      <a-collapse-panel key="user" header="用户例外（高级，按需覆盖）">
        <div v-for="(row, index) in userRows" :key="`user-${index}`" class="cap-row">
          <a-select
            v-model:value="row.user_key"
            size="small"
            class="cap-user"
            :options="userOptions"
            show-search
            option-filter-prop="label"
            placeholder="选择用户"
          />
          <a-select
            v-model:value="row.colleague_keys"
            mode="multiple"
            size="small"
            class="cap-keys"
            :options="colleagueOptions"
            placeholder="选择 AI 角色"
            allow-clear
          />
          <a-button type="text" size="small" danger @click="userRows.splice(index, 1)">删除</a-button>
        </div>
        <a-button block size="small" type="dashed" @click="userRows.push({ user_key: '', colleague_keys: [] })">
          新增用户例外
        </a-button>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<style scoped>
.cap-root {
  border: 1px solid var(--cpq-border-secondary, rgba(255, 255, 255, 0.1));
  border-radius: 14px;
  padding: 16px;
  background: var(--cpq-overlay-w4, rgba(255, 255, 255, 0.04));
}
.cap-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.cap-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}
.cap-help {
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin: 4px 0 8px;
}
.cap-section {
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin: 8px 0;
}
.cap-price-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px 16px;
}
.cap-price-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cap-price-name {
  font-size: 13px;
  color: var(--cpq-text-primary);
}
.cap-price-name.is-off {
  color: var(--cpq-text-muted);
}
.cap-price-hint {
  font-size: 12px;
  color: var(--cpq-text-muted);
}
.cap-divider {
  margin: 14px 0;
}
.cap-line {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--cpq-text-primary);
}
.cap-label {
  display: block;
  font-size: 12px;
  color: var(--cpq-text-muted);
  margin: 12px 0 6px;
}
.cap-row {
  display: grid;
  grid-template-columns: minmax(140px, 180px) minmax(0, 1fr) auto;
  gap: 8px;
  margin-bottom: 8px;
}
.cap-keys {
  min-width: 0;
}
.cap-user-exceptions {
  margin-top: 10px;
}
</style>
