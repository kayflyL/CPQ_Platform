<template>
  <div class="comment-panel">
    <div class="comment-header" v-if="showTitle">
      <span class="comment-title">💬 评论</span>
      <a-badge :count="comments.length" :numberStyle="{ backgroundColor: 'var(--cpq-accent-primary)' }" />
    </div>
    
    <!-- 评论列表 -->
    <div class="comment-list">
      <div v-if="comments.length === 0" class="empty-state">
        <a-empty description="暂无评论" :image-style="{ height: '40px' }" />
      </div>
      <div v-else class="comments-scroll">
        <div v-for="comment in comments" :key="comment.id" class="comment-item">
          <div class="comment-header-row">
            <span class="user-name">{{ comment.user_name }}</span>
            <span class="comment-time">{{ formatTime(comment.created_at) }}</span>
            <a-button type="text" size="small" danger @click="handleDelete(comment.id)">
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
          <div class="comment-content">{{ comment.content }}</div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="comment-input">
      <a-textarea
        v-model:value="newComment"
        placeholder="输入评论..."
        :autoSize="{ minRows: 2, maxRows: 4 }"
        @pressEnter="handleKeyPress"
      />
      <a-button type="primary" block size="small" @click="handleAdd" :loading="loading">
        发送
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import axios from 'axios'

interface Comment {
  id: number
  opportunity_id: string
  user_name: string
  content: string
  created_at: string
}

const props = defineProps<{
  opportunityId: string
  visible: boolean
  showTitle?: boolean
}>()

const comments = ref<Comment[]>([])
const newComment = ref('')
const loading = ref(false)

// 加载评论
const loadComments = async () => {
  if (!props.opportunityId) return
  
  try {
    const res = await axios.get(`/api/comments/${props.opportunityId}`)
    comments.value = res.data || []
  } catch (error) {
    console.error('加载评论失败:', error)
  }
}

// 添加评论
const handleAdd = async () => {
  if (!newComment.value.trim()) {
    message.warning('请输入评论内容')
    return
  }
  
  loading.value = true
  try {
    await axios.post('/api/comments/', {
      opportunity_id: props.opportunityId,
      content: newComment.value,
      user_name: '当前用户' // TODO: 从登录状态获取
    })
    
    newComment.value = ''
    await loadComments()
    message.success('评论已添加')
  } catch (error) {
    console.error('添加评论失败:', error)
    message.error('添加评论失败')
  } finally {
    loading.value = false
  }
}

// 删除评论
const handleDelete = async (commentId: number) => {
  try {
    await axios.delete(`/api/comments/${commentId}`)
    await loadComments()
    message.success('评论已删除')
  } catch (error) {
    console.error('删除评论失败:', error)
    message.error('删除评论失败')
  }
}

// 格式化时间
const formatTime = (timeStr: string) => {
  if (timeStr === '刚刚') return timeStr
  
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  
  return date.toLocaleDateString('zh-CN')
}

// Enter 发送（Shift+Enter 换行）
const handleKeyPress = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleAdd()
  }
}

// 监听 opportunityId 变化
watch(() => props.opportunityId, () => {
  if (props.visible) {
    loadComments()
  }
})

// 监听 visible 变化
watch(() => props.visible, (val) => {
  if (val) {
    loadComments()
  }
})

onMounted(() => {
  if (props.visible) {
    loadComments()
  }
})
</script>

<style scoped>
.comment-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--cpq-bg-secondary);
}

.comment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--cpq-border-primary);
  background: var(--cpq-bg-tertiary);
}

.comment-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
}

.comment-list {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.comments-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.comment-item {
  background: var(--cpq-bg-tertiary);
  border: 1px solid var(--cpq-border-primary);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.comment-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.user-name {
  font-weight: 600;
  color: var(--cpq-text-primary);
  font-size: 13px;
}

.comment-time {
  flex: 1;
  font-size: 11px;
  color: var(--cpq-text-muted);
}

.comment-content {
  color: var(--cpq-text-primary);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.comment-input {
  border-top: 1px solid var(--cpq-border-primary);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--cpq-bg-tertiary);
}
</style>
