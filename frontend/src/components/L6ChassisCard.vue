<template>
  <div class="l6-chassis-card glass" :class="{ 'no-match': !record }">
    <!-- Card Header: Chassis + Actions -->
    <div class="card-header">
      <div class="chassis-display">
        <span v-if="record" class="chassis-name">{{ record.chassis || '—' }}</span>
        <span v-else class="no-match-label">⚠️ 未匹配 L6</span>
      </div>
      <div class="record-actions">
        <a-button type="text" size="small" class="action-btn" @click="$emit('change')" title="更换机箱">
          🔄
        </a-button>
      </div>
    </div>

    <template v-if="record">
      <!-- Match Score Badge -->
      <div v-if="record.match_score !== undefined" class="match-badge" :class="getScoreClass(record.match_score)">
        {{ record.match_score }}% {{ record.match_type || '匹配' }}
      </div>

      <!-- Highlighted Specs -->
      <div class="highlighted-specs">
        <div class="spec-item motherboard" v-if="record.motherboard">
          <span class="spec-value">{{ record.motherboard }}</span>
        </div>
        <div class="spec-item psu" v-if="record.psu">
          <span class="spec-value">{{ record.psu }}</span>
        </div>
      </div>

      <!-- Other Specs -->
      <div class="spec-tags">
        <span v-if="record.drive_bays" class="spec-pill">{{ record.drive_bays }}盘位</span>
        <span v-if="record.backplane" class="spec-pill">{{ record.backplane }}</span>
        <span v-if="record.gpu_expansion" class="spec-pill">GPU:{{ record.gpu_expansion }}</span>
        <span v-if="record.rail_kit" class="spec-pill">{{ record.rail_kit }}</span>
        <span v-if="record.power_cord" class="spec-pill">{{ record.power_cord }}</span>
      </div>

      <!-- Footer: Price + Date -->
      <div class="record-footer">
        <span class="footer-price">¥ {{ formatPrice(record.price) }}</span>
        <span v-if="record.update_date" class="footer-date">📅 {{ record.update_date }}</span>
      </div>
    </template>

    <template v-else>
      <div class="no-match-body">
        <p>点击 🔄 手动选择机箱</p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  record: any
}>()

defineEmits<{
  (e: 'change'): void
}>()

function getScoreClass(score: number): string {
  if (score >= 80) return 'score-high'
  if (score >= 50) return 'score-medium'
  return 'score-low'
}

function formatPrice(price: number | string): string {
  const num = typeof price === 'string' ? parseFloat(price) : price
  if (isNaN(num)) return '—'
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l6-chassis-card {
  padding: 16px;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.l6-chassis-card:hover {
  border-color: var(--cpq-accent-primary, var(--cpq-color-info));
}

.l6-chassis-card.no-match {
  border-style: dashed;
  opacity: 0.7;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.chassis-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
}

.no-match-label {
  font-size: 14px;
  color: var(--cpq-color-warning);
  font-weight: 500;
}

.action-btn {
  color: var(--cpq-text-secondary, #a0a0a0);
  font-size: 16px;
}

.action-btn:hover {
  color: var(--cpq-accent-primary, var(--cpq-color-info));
}

.match-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-bottom: 10px;
  font-weight: 500;
}

.match-badge.score-high {
  background: var(--cpq-overlay-success15);
  color: var(--cpq-color-success);
}

.match-badge.score-medium {
  background: var(--cpq-overlay-warn30);
  color: var(--cpq-color-warning);
}

.match-badge.score-low {
  background: var(--cpq-overlay-danger15);
  color: var(--cpq-accent-danger);
}

.highlighted-specs {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.spec-item {
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--cpq-overlay-w6);
}

.spec-item .spec-value {
  font-size: 13px;
  color: var(--cpq-text-primary, var(--cpq-text-primary));
}

.spec-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.spec-pill {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--cpq-overlay-w4);
  border: 1px solid var(--cpq-overlay-w8);
  border-radius: 4px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.record-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid var(--cpq-overlay-w6);
}

.footer-price {
  font-size: 16px;
  font-weight: 600;
  color: var(--cpq-accent-primary, var(--cpq-color-info));
}

.footer-date {
  font-size: 12px;
  color: var(--cpq-text-secondary, #a0a0a0);
}

.no-match-body {
  text-align: center;
  padding: 20px 0;
  color: var(--cpq-text-secondary, #a0a0a0);
  font-size: 13px;
}
</style>
