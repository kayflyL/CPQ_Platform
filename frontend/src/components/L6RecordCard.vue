<template>
  <div class="l6-record-card" :class="{ matched }">
    <!-- Card Header: Chassis + Actions -->
    <div class="card-header">
      <div class="chassis-display">{{ record.chassis || '—' }}</div>
      <div v-if="showActions" class="record-actions">
        <slot name="actions">
          <a-button type="text" size="small" class="action-btn" @click.stop="$emit('edit')">✏️</a-button>
          <a-popconfirm
            title="确定删除这条记录？"
            ok-text="删除"
            cancel-text="取消"
            @confirm="$emit('delete')"
          >
            <a-button type="text" size="small" class="action-btn delete-btn" @click.stop>🗑️</a-button>
          </a-popconfirm>
        </slot>
      </div>
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

    <!-- Footer: Price + Date + Note -->
    <div class="record-footer">
      <span class="footer-price">¥ {{ formatPrice(record.price) }}</span>
      <span v-if="record.update_date" class="footer-date">📅 {{ record.update_date }}</span>
      <span v-if="record.note" class="footer-note" :title="record.note">{{ record.note }}</span>
    </div>

    <!-- Pricing Footer (for Workspace) -->
    <div v-if="showPricing" class="pricing-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
interface L6Record {
  id: number
  model: string
  chassis: string
  motherboard?: string
  psu?: string
  drive_bays?: string
  backplane?: string
  gpu_expansion?: string
  rail_kit?: string
  power_cord?: string
  price: number
  update_date?: string
  note?: string
}

const props = withDefaults(defineProps<{
  record: L6Record
  showActions?: boolean
  showPricing?: boolean
  matched?: boolean
}>(), {
  showActions: false,
  showPricing: false,
  matched: false
})

defineEmits<{
  edit: []
  delete: []
}>()

const formatPrice = (price: number) => {
  return price?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l6-record-card {
  background: var(--cpq-overlay-b20);
  border: 1px solid var(--cpq-overlay-w6);
  border-radius: 10px;
  padding: 16px;
  transition: all var(--cpq-transition-fast, 0.2s);
  position: relative;
}

.l6-record-card:hover {
  border-color: var(--cpq-accent-primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px var(--cpq-overlay-a15);
}

.l6-record-card.matched {
  border-color: var(--cpq-accent-success, #52c41a);
  box-shadow: 0 0 16px var(--cpq-overlay-success15);
}

/* Card Header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.chassis-display {
  font-size: 24px;
  font-weight: 700;
  color: var(--cpq-accent-primary);
  line-height: 1;
}

.record-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity var(--cpq-transition-fast, 0.2s);
}

.l6-record-card:hover .record-actions {
  opacity: 1;
}

.action-btn {
  padding: 4px 8px !important;
  font-size: 14px;
  color: var(--cpq-text-secondary) !important;
}

.action-btn:hover {
  color: var(--cpq-accent-primary) !important;
}

.delete-btn:hover {
  color: var(--cpq-accent-danger, #ff4d4f) !important;
}

/* Highlighted Specs */
.highlighted-specs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.spec-item {
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 4px;
  position: relative;
}

.spec-item.motherboard {
  background: rgba(250, 140, 22, 0.12);
  border-left: 2px solid var(--cpq-color-orange);
}

.spec-item.psu {
  background: rgba(114, 46, 209, 0.12);
  border-left: 2px solid var(--cpq-color-purple-dark);
}

.spec-item.motherboard .spec-value,
.spec-item.psu .spec-value {
  color: var(--cpq-text-primary);
  font-weight: 500;
}

/* Spec Pills */
.spec-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.spec-pill {
  padding: 3px 10px;
  background: var(--cpq-overlay-w5);
  color: var(--cpq-text-muted);
  border-radius: 12px;
  font-size: 11px;
}

/* Record Footer */
.record-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--cpq-text-muted);
  border-top: 1px solid var(--cpq-overlay-w6);
  padding-top: 10px;
  margin-top: 8px;
}

.footer-price {
  font-size: 14px;
  font-weight: 600;
  color: var(--cpq-accent-primary);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.footer-date {
  color: var(--cpq-text-muted);
  flex-shrink: 0;
}

.footer-note {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
  color: var(--cpq-text-muted);
  font-size: 13px;
}

/* Pricing Footer */
.pricing-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--cpq-overlay-w6);
}
</style>
