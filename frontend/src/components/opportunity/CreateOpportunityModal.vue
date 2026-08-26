<template>
  <a-modal
    v-model:open="open"
    title="新建商机"
    ok-text="创建并进入详情"
    cancel-text="取消"
    :confirm-loading="saving"
    :mask-style="{ background: 'rgba(2, 6, 23, 0.62)', 'backdrop-filter': 'blur(2px)' }"
    :body-style="{ background: 'var(--cpq-bg-secondary)' }"
    wrap-class-name="portal-modal"
    @ok="submit"
  >
    <a-form layout="vertical">
      <a-form-item label="客户名称" required>
        <a-input v-model:value="form.customer_name" placeholder="请输入客户名称" @keydown.enter="submit" />
      </a-form-item>
      <a-form-item label="业务">
        <a-input v-if="!canViewAll" v-model:value="form.sales_person" disabled />
        <a-auto-complete
          v-else
          v-model:value="form.sales_person"
          :options="candidates"
          placeholder="输入或搜索业务名（可自由输入）"
          allow-clear
          :default-active-first-option="false"
          style="width: 100%"
          @focus="loadCandidates"
          @keydown.enter="submit"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { projectApi } from '@/api'
import { useAuthStore } from '@/store/auth'

const open = defineModel<boolean>('open', { default: false })
const props = withDefaults(defineProps<{ from?: string }>(), { from: '' })
const emit = defineEmits<{ (e: 'created', res: { opportunity_id: string }): void }>()

const auth = useAuthStore()
const router = useRouter()
const canViewAll = computed(() => auth.can('page.opportunities_all'))
const saving = ref(false)
const candidates = ref<{ value: string; label: string }[]>([])
const form = reactive({ customer_name: '', sales_person: '' })

watch(open, (v) => {
  if (!v) return
  form.customer_name = ''
  form.sales_person = canViewAll.value ? '' : (auth.user?.name || '')
  if (canViewAll.value) void loadCandidates()
})

async function loadCandidates() {
  if (!canViewAll.value) return
  if (candidates.value.length) return
  try {
    const items = (await projectApi.businessOptions()) || []
    candidates.value = items.map((u: any) => ({ label: u.name, value: u.name }))
  } catch {
    candidates.value = []
  }
}

async function submit() {
  if (!form.customer_name.trim()) {
    message.warning('请输入客户名称')
    return
  }
  saving.value = true
  try {
    const salesPerson = canViewAll.value ? form.sales_person.trim() : (auth.user?.name || '')
    const res = await projectApi.create({ customer_name: form.customer_name.trim(), sales_person: salesPerson })
    message.success('创建成功')
    emit('created', res)
    open.value = false
    router.push({
      path: `/opportunities/${res.opportunity_id}`,
      query: props.from ? { from: props.from } : undefined,
    })
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '创建失败，请稍后重试')
  } finally {
    saving.value = false
  }
}
</script>
