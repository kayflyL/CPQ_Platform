<script setup lang="ts">
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { feedApi } from '@/api/feed'
import type { FeedAttachment } from '@/api/feed'

const props = withDefaults(defineProps<{
  opportunityId: string
  category: string
  label?: string
  accept?: string
}>(), {
  label: '上传附件',
  accept: '.xlsx,.xls,.pdf,.doc,.docx,.png,.jpg,.jpeg',
})

const emit = defineEmits<{
  (e: 'uploaded', attachment: FeedAttachment): void
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

function pick() {
  inputRef.value?.click()
}

async function onPicked(e: Event) {
  const target = e.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ''
  if (!files.length) return
  uploading.value = true
  let ok = 0
  let fail = 0
  for (const f of files) {
    try {
      const att = await feedApi.attachments.upload(props.opportunityId, f, { category: props.category })
      ok++
      emit('uploaded', att)
    } catch {
      fail++
    }
  }
  uploading.value = false
  if (ok) message.success(`已上传 ${ok} 个文件`)
  if (fail) message.error(`${fail} 个文件上传失败`)
}
</script>

<template>
  <span class="attachment-upload-btn">
    <a-button size="small" :loading="uploading" @click="pick">{{ label }}</a-button>
    <input ref="inputRef" type="file" multiple hidden :accept="accept" @change="onPicked" />
  </span>
</template>

<style scoped>
.attachment-upload-btn {
  display: inline-flex;
}
</style>
