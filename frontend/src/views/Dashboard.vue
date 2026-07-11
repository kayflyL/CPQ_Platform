<template>
  <div class="dashboard-page">
    <!-- Page Header with Search -->
    <div class="page-header glass">
      <div class="header-content">
        <h2>📊 工作台</h2>
        <div class="search-bar">
          <a-input-search
            v-model:value="searchQuery"
            placeholder="搜索商机..."
            allow-clear
            class="search-input"
          />
        </div>
      </div>
    </div>

    <!-- Row 1: Quick Actions -->
    <div class="quick-actions">
      <div class="action-card glass" @click="showCreateModal = true">
        <div class="action-icon">➕</div>
        <div class="action-title">新建商机</div>
        <div class="action-desc">创建商机，自由编辑配置</div>
      </div>
    </div>

    <!-- Row 2: Statistics -->
    <div class="stats-row">
      <div class="stat-card glass">
        <div class="stat-value">{{ stats.total_projects }}</div>
        <div class="stat-label">总商机数</div>
      </div>
      <div class="stat-card glass">
        <div class="stat-value">{{ stats.total_configs }}</div>
        <div class="stat-label">总配置数</div>
      </div>
      <div class="stat-card glass">
        <div class="stat-value">{{ stats.new_projects_this_week }}</div>
        <div class="stat-label">本周新增商机</div>
      </div>
      <div class="stat-card glass">
        <div class="stat-value">{{ stats.new_configs_this_week }}</div>
        <div class="stat-label">本周新增配置</div>
      </div>
    </div>

    <!-- Row 3: Trend Chart -->
    <div class="trend-section glass">
      <div class="trend-header">
        <h3>近 30 天趋势</h3>
      </div>
      <div class="trend-chart">
        <Line :data="chartData" :options="chartOptions" />
      </div>
    </div>

    <!-- Create Empty Project Modal -->
    <a-modal
      v-model:open="showCreateModal"
      title="新建商机"
      @ok="handleCreateProject"
      :confirmLoading="creating"
      ok-text="创建"
      cancel-text="取消"
    >
      <div class="create-form">
        <div class="form-row">
          <label>商机名称 <span class="required">*</span></label>
          <a-input v-model:value="newProject.project_name" placeholder="如：XX客户服务器报价" />
        </div>
        <div class="form-row">
          <label>客户名称</label>
          <a-input v-model:value="newProject.customer_name" placeholder="客户名称（可选）" />
        </div>
        <div class="form-row">
          <label>备注</label>
          <a-textarea v-model:value="newProject.notes" :rows="2" placeholder="备注信息（可选）" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import axios from 'axios'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const router = useRouter()

// =================== Search ===================
const searchQuery = ref('')

// =================== Stats ===================
const stats = ref({
  total_projects: 0,
  total_configs: 0,
  new_projects_this_week: 0,
  new_configs_this_week: 0,
})

const loadStats = async () => {
  try {
    const res = await axios.get('/api/dashboard/stats')
    stats.value = res.data
  } catch (e: any) {
    console.error('Failed to load stats:', e)
  }
}

// =================== Trend Data ===================
const trendData = ref<Array<{ date: string; projects: number; configs: number }>>([])

const loadTrend = async () => {
  try {
    const res = await axios.get('/api/dashboard/trend?days=30')
    trendData.value = res.data
  } catch (e: any) {
    console.error('Failed to load trend:', e)
  }
}

const chartData = computed(() => {
  const labels = trendData.value.map(d => d.date.slice(5)) // MM-DD
  const projects = trendData.value.map(d => d.projects)
  const configs = trendData.value.map(d => d.configs)

  return {
    labels,
    datasets: [
      {
        label: '新增商机',
        data: projects,
        borderColor: '#00F5D4',
        backgroundColor: 'var(--cpq-overlay-a10)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
        borderWidth: 2
      },
      {
        label: '新增配置',
        data: configs,
        borderColor: '#F4D28A',
        backgroundColor: 'rgba(244, 210, 138, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
        borderWidth: 2
      }
    ]
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: true,
      position: 'top' as const,
      labels: {
        color: '#E8ECEF',
        font: { size: 12 },
        padding: 16
      }
    },
    tooltip: {
      backgroundColor: 'rgba(16, 18, 23, 0.9)',
      titleColor: '#E8ECEF',
      bodyColor: '#E8ECEF',
      borderColor: 'var(--cpq-overlay-w10)',
      borderWidth: 1,
      padding: 12,
      cornerRadius: 8
    }
  },
  scales: {
    x: {
      grid: {
        color: 'var(--cpq-overlay-w5)',
        drawBorder: false
      },
      ticks: {
        color: '#8A9099',
        font: { size: 11 },
        maxRotation: 0,
        autoSkip: true,
        maxTicksLimit: 10
      }
    },
    y: {
      grid: {
        color: 'var(--cpq-overlay-w5)',
        drawBorder: false
      },
      ticks: {
        color: '#8A9099',
        font: { size: 11 },
        precision: 0
      },
      beginAtZero: true
    }
  },
  interaction: {
    mode: 'index' as const,
    intersect: false
  }
}

// =================== Create Empty Project ===================
const showCreateModal = ref(false)
const creating = ref(false)
const newProject = ref({
  project_name: '',
  customer_name: '',
  notes: '',
})

const handleCreateProject = async () => {
  if (!newProject.value.project_name.trim()) {
    message.warning('请输入商机名称')
    return
  }
  creating.value = true
  try {
    const res = await axios.post('/api/opportunities/', newProject.value)
    if (res.data.status === 'success') {
      message.success('商机创建成功')
      showCreateModal.value = false
      newProject.value = { project_name: '', customer_name: '', notes: '' }
      loadStats()
      loadTrend()
      router.push(`/projects`)
    }
  } catch (e: any) {
    message.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

// =================== Init ===================
onMounted(() => {
  loadStats()
  loadTrend()
})
</script>

<style scoped>
.dashboard-page {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
  padding: 20px 24px;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.page-header h2 {
  margin: 0;
  color: var(--cpq-text-primary);
  font-size: 20px;
  font-weight: 600;
}

.search-bar {
  flex: 1;
  max-width: 400px;
}

.search-input :deep(.ant-input) {
  background: var(--cpq-overlay-w5) !important;
  border-color: var(--cpq-overlay-w10) !important;
  color: var(--cpq-text-primary) !important;
}

.search-input :deep(.ant-input:hover),
.search-input :deep(.ant-input:focus) {
  border-color: var(--cpq-accent-primary) !important;
  box-shadow: 0 0 0 2px var(--cpq-overlay-a10) !important;
}

.search-input :deep(.ant-btn-primary) {
  background: var(--cpq-accent-primary) !important;
  border-color: var(--cpq-accent-primary) !important;
}

.search-input :deep(.ant-btn-primary:hover) {
  background: var(--cpq-accent-primary-light) !important;
  border-color: var(--cpq-accent-primary-light) !important;
  box-shadow: 0 0 16px var(--cpq-overlay-a40);
}

/* Row 1: Quick Actions */
.quick-actions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.action-card {
  padding: 24px;
  cursor: pointer;
}

/* Row 2: Statistics */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  margin-bottom: 8px;
}

.stat-label {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

/* Row 3: Trend Chart */
.trend-section {
  padding: 24px;
  margin-bottom: 24px;
}

.trend-header {
  margin-bottom: 20px;
}

.trend-header h3 {
  margin: 0;
  color: var(--cpq-text-primary);
  font-size: 16px;
  font-weight: 600;
}

.trend-chart {
  height: 280px;
  position: relative;
}

.action-icon {
  font-size: 32px;
  margin-bottom: 12px;
}
.action-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  margin-bottom: 8px;
}
.action-desc {
  font-size: 13px;
  color: var(--cpq-text-secondary);
}

/* Create Form */
.create-form .form-row {
  margin-bottom: 16px;
}
.create-form .form-row label {
  display: block;
  margin-bottom: 6px;
  color: var(--cpq-text-primary);
  font-size: 13px;
}
.create-form .required {
  color: var(--cpq-accent-danger);
}
</style>
