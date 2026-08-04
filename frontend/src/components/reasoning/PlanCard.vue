<template>
  <article class="plan-card">
    <header class="pc-head">
      <div class="pc-namebox">
        <h4 class="pc-name">
          {{ plan.name || plan.model || '(未命名整机)' }}
          <a-tag v-if="plan.use" class="pc-use">{{ plan.use }}</a-tag>
          <a-tag v-if="plan.recommend_level === 'recommend'" color="success">推荐</a-tag>
          <a-tag v-else-if="plan.recommend_level === 'avoid'" color="error">不推荐</a-tag>
        </h4>
        <span class="pc-series">{{ [plan.series, plan.form, plan.bays != null ? `${plan.bays}盘位` : ''].filter(Boolean).join(' · ') }}</span>
      </div>
      <span class="pc-cost">¥{{ fmt(plan.summary.total_cost) }}</span>
    </header>
    <p v-if="plan.over_budget" class="pc-warn">
      <WarningOutlined /> 满足需求但超预算 ¥{{ fmt(plan.over_budget.amount) }}
    </p>
    <p v-else-if="plan.underspend" class="pc-warn info">
      <InfoCircleOutlined /> 方案仅用预算 {{ Math.round(plan.underspend.ratio * 100) }}%，可升级配置（还剩 ¥{{ fmt(plan.underspend.amount) }}）
    </p>
    <!-- AI 校对结论（review 节点，阻塞式：通过/不通过 + 必改项） -->
    <p
      v-if="plan.audit"
      class="pc-warn"
      :class="plan.audit.status === 'ok' ? 'info' : 'error'"
    >
      <InfoCircleOutlined v-if="plan.audit.status === 'ok'" />
      <WarningOutlined v-else />
      {{ plan.audit.status === 'ok' ? '校对通过 ✓' : ('需修改：' + (plan.audit.issues || []).join('；')) }}
    </p>
    <!-- 选型配置规则校验告警（需求分析自动出方案与工作台共用同一套规则） -->
    <p
      v-for="a in plan.selection_alerts"
      :key="(a.ruleId ?? 0) + '-' + a.desc"
      class="pc-warn"
      :class="a.severity === 'info' ? 'info' : ''"
    >
      <WarningOutlined v-if="a.severity !== 'info'" />
      <InfoCircleOutlined v-else />
      {{ a.desc }}
    </p>
    <p v-if="plan.selling_points" class="pc-points">★ {{ plan.selling_points }}</p>
    <p class="pc-meta">底盘 {{ plan.summary.parts_count }} 件 + KP {{ plan.summary.kp_count }} 件 · 含税价以工作台为准</p>
    <footer class="pc-actions">
      <slot name="extra-actions" />
      <a-button size="small" @click="$emit('view-bom', plan)">
        <template #icon><EyeOutlined /></template>
        查看 BOM 详情
      </a-button>
    </footer>
  </article>
</template>

<script setup lang="ts">
/**
 * 整机方案卡（ReasoningPanel 与策略中心试运行面板共用）。
 * 展示机型/系列/总价/预算标注/卖点/件数 + 「查看 BOM 详情」按钮（emit view-bom）。
 * 业务专属动作（如商机详情页的「确认转报价单」）经 #extra-actions slot 注入，保持组件通用。
 */
import { WarningOutlined, InfoCircleOutlined, EyeOutlined } from '@ant-design/icons-vue'
import type { Plan } from '@/api/reasoning'

const props = defineProps<{ plan: Plan }>()
defineEmits<{ (e: 'view-bom', plan: Plan): void }>()

function fmt(n: number | null | undefined) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
/* 整机方案卡 = 主角（左渐变 signature 描边 + 阴影）；样式源自 ReasoningPanel .rp-plan，前缀 pc- */
.plan-card {
  position: relative;
  flex-shrink: 0;
  margin: 4px 0 2px;
  padding: 12px 14px 12px 16px;
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: var(--cpq-radius-md);
  box-shadow: var(--cpq-shadow-sm);
  overflow: hidden;
  animation: pc-in 0.3s var(--cpq-ease-out-expo) both;
  transition: border-color var(--cpq-transition-fast), box-shadow var(--cpq-transition-fast);
}
.plan-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--cpq-accent-gradient);
}
.plan-card:hover {
  border-color: var(--cpq-glass-border-strong);
  box-shadow: var(--cpq-shadow-md);
}
.pc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.pc-namebox {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.pc-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-text-primary);
  word-break: break-word;
  overflow-wrap: anywhere;
}
.pc-series {
  font-size: 11px;
  color: var(--cpq-accent-primary);
}
.pc-cost {
  font-size: 16px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.pc-meta {
  margin: 6px 0 10px;
  font-size: 11px;
  color: var(--cpq-text-muted);
}
.pc-points {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--cpq-text-secondary);
}
.pc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

/* 超预算 / 预算利用不足标注 */
.pc-warn {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--cpq-accent-warning, #faad14);
  background: var(--cpq-overlay-w6);
  border: 1px solid var(--cpq-overlay-w15, var(--cpq-overlay-w10));
  border-radius: var(--cpq-radius-sm, 8px);
}
.pc-warn.info {
  color: var(--cpq-accent-info, #3b82f6);
}
.pc-warn.error {
  color: var(--cpq-accent-danger, #dc2626);
}

@keyframes pc-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
