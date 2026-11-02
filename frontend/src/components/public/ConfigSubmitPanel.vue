<script setup lang="ts">
/**
 * 提交配置面板（ConfigSubmitPanel）—— 公开配置向导的完成动作 overlay。
 * 设计定调：机器能推出来的（机型/平台/机箱/电源/部件清单）全部自动带出只读展示，
 * 用户只补「台数 / 维保年限（业务字段）+ 需求补充选填 + 联系信息」。
 * slots 产出与 /lead 登记表（RequirementForm.toSlots）完全同构 → 同一条线索管道，业务侧零改造。
 * 「查看规格书」通过向导 expose 的 openSpecSheet() 复用组件内规格书 overlay（打印/PDF 链路）。
 */
import { ref, computed } from 'vue'
import { message } from 'ant-design-vue'
import { publicLeadApi } from '@/api/publicIntake'

const props = defineProps<{
  /** 快照.meta：机型/平台/机箱形态/建议电源（来自向导自动带出） */
  meta: Record<string, any>
  /** 快照.kp_rows：部件清单行（category/part_category/catalogue/description/qty/note） */
  kpRows: Array<Record<string, any>>
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'view-spec'): void
  (e: 'submitted', res: { ok: boolean; lead_id: string | null; merged: boolean }): void
}>()

const qty = ref(1)
const warrantyYears = ref('3')
const reqText = ref('')
const company = ref('')
const contactName = ref('')
const contactPhone = ref('')
const contactEmail = ref('')
const website = ref('') // 蜜罐：真实用户不可见必为空
const submitting = ref(false)
const done = ref<{ merged: boolean } | null>(null)

const metaRows = computed(() => [
  { label: '机型型号', value: props.meta?.server_model || '—' },
  { label: '平台类型', value: props.meta?.platform_type || '—' },
  { label: '机箱形态', value: props.meta?.chassis_form ? `${props.meta.chassis_form}${props.meta?.chassis_bays ? ` · ${props.meta.chassis_bays} 盘位` : ''}` : '—' },
  { label: '建议电源', value: props.meta?.psu_text || '—' },
])

const hasParts = computed(() => (props.kpRows || []).length > 0)

async function submit() {
  if (website.value.trim()) return // 蜜罐命中：静默丢弃
  if (!company.value.trim()) { message.warning('请填写公司名称'); return }
  if (!contactName.value.trim()) { message.warning('请填写联系人姓名'); return }
  if (!/^1\d{10}$/.test(contactPhone.value.trim())) { message.warning('请填写 11 位手机号'); return }
  const n = Math.max(1, Math.floor(Number(qty.value) || 1))
  // slots 与 RequirementForm.toSlots 同构：configs[0] + 顶层冗余键，后端白名单键重建
  const cfg = {
    name: 'CFG1',
    server_model: props.meta?.server_model || '',
    platform_type: props.meta?.platform_type || '',
    server_type: '',
    chassis_form: props.meta?.chassis_form || '',
    qty: n,
    warranty_years: String(Math.max(1, Math.floor(Number(warrantyYears.value) || 1))),
    kp_rows: props.kpRows || [],
  }
  const slots: Record<string, any> = {
    configs: [cfg],
    config_relation: 'compose',
    purchase_qty: n,
    server_model: cfg.server_model,
    platform_type: cfg.platform_type,
    chassis_form: cfg.chassis_form,
    warranty_years: cfg.warranty_years,
    kp_rows: cfg.kp_rows,
  }
  submitting.value = true
  try {
    const res = await publicLeadApi.submit({
      requirement_text: reqText.value,
      company: company.value,
      contact_name: contactName.value,
      contact_phone: contactPhone.value,
      contact_email: contactEmail.value,
      source: 'catalog_model',
      config_slots: JSON.stringify(slots),
    })
    done.value = { merged: res.merged }
    emit('submitted', res)
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '提交失败，请重试')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="csp-wrap" @click.self="emit('close')">
    <div class="csp-panel glass">
      <div class="csp-head">
        <div>
          <div class="csp-title">确认配置并提交</div>
          <div class="csp-sub">机型信息已自动带出，只需补全数量与联系方式</div>
        </div>
        <button class="csp-x" type="button" aria-label="关闭" @click="emit('close')">✕</button>
      </div>

      <div v-if="done" class="csp-done">
        <div class="csp-done-ico">✓</div>
        <h4>{{ done.merged ? '您的配置已并入之前的提交' : '已收到您的配置需求' }}</h4>
        <p>{{ done.merged ? '检测到您此前已提交过，本次内容已合并给同一负责人跟进。' : '我们会在 1 个工作日内与您联系，请保持手机畅通。' }}</p>
        <button class="csp-btn-ghost" type="button" @click="emit('close')">继续调整配置</button>
      </div>

      <div v-else class="csp-body">
        <!-- 配置确认卡：自动带出，只读 -->
        <section class="csp-sec">
          <h4 class="csp-sec-title">配置确认<span class="csp-hint">来自当前配置 · 自动带出</span></h4>
          <div class="csp-meta">
            <div v-for="r in metaRows" :key="r.label" class="csp-meta-item">
              <span class="csp-meta-k">{{ r.label }}<em class="csp-auto-tag">自动带出</em></span>
              <span class="csp-meta-v">{{ r.value }}</span>
            </div>
          </div>
        </section>

        <!-- 部件清单：来自当前配置，只读 -->
        <section class="csp-sec">
          <h4 class="csp-sec-title">部件清单<span class="csp-hint">来自当前配置 · {{ hasParts ? `${kpRows.length} 行` : '空' }}</span></h4>
          <div v-if="hasParts" class="csp-parts">
            <div v-for="(r, i) in kpRows" :key="(r.catalogue || '') + i" class="csp-part-row">
              <span class="csp-part-cat">{{ r.part_category || '配件' }}</span>
              <span class="csp-part-name">
                <b>{{ r.catalogue }}</b>
                <small v-if="r.description">{{ r.description }}</small>
              </span>
              <span class="csp-part-qty">×{{ r.qty }}</span>
            </div>
          </div>
          <div v-else class="csp-parts-empty">当前配置暂无部件，请回到向导完成选型</div>
        </section>

        <!-- 业务字段：数量 / 维保 + 查看规格书 -->
        <section class="csp-sec">
          <div class="csp-edit-row">
            <div class="csp-field">
              <label>数量<em>*</em></label>
              <a-input-number v-model:value="qty" :min="1" :precision="0" style="width: 100%" />
            </div>
            <div class="csp-field">
              <label>维保年限<em>*</em></label>
              <a-select v-model:value="warrantyYears" style="width: 100%" :options="[{ value: '1', label: '1 年' }, { value: '3', label: '3 年' }, { value: '5', label: '5 年' }]" />
            </div>
            <button class="csp-spec-btn" type="button" @click="emit('view-spec')">📄 查看规格书</button>
          </div>
        </section>

        <!-- 需求补充：选填 -->
        <section class="csp-sec">
          <h4 class="csp-sec-title">需求补充<span class="csp-hint">选填 · 机柜 / 交付时间 / 网络环境等</span></h4>
          <a-textarea v-model:value="reqText" :auto-size="{ minRows: 2, maxRows: 6 }" placeholder="有什么补充？机柜、交付时间、网络环境…" />
        </section>

        <!-- 联系信息 -->
        <section class="csp-sec">
          <h4 class="csp-sec-title">联系信息</h4>
          <div class="csp-contact">
            <div class="csp-field"><label>公司名称<em>*</em></label><a-input v-model:value="company" placeholder="贵司全称" /></div>
            <div class="csp-field"><label>联系人姓名<em>*</em></label><a-input v-model:value="contactName" placeholder="怎么称呼您" /></div>
            <div class="csp-field"><label>手机号<em>*</em></label><a-input v-model:value="contactPhone" placeholder="11 位手机号" :maxlength="11" /></div>
            <div class="csp-field"><label>工作邮箱</label><a-input v-model:value="contactEmail" placeholder="name@company.com（选填）" /></div>
          </div>
          <!-- 蜜罐：隐藏字段，机器人填写即静默丢弃 -->
          <input v-model="website" name="website" tabindex="-1" autocomplete="off" class="csp-hp" />
          <p class="csp-privacy">提交即表示同意我们仅将以上信息用于本次咨询联系，不做其他用途。</p>
        </section>

        <button class="csp-submit" type="button" :disabled="submitting" @click="submit">
          {{ submitting ? '提交中…' : '提交配置，获取报价 →' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.csp-wrap {
  position: fixed; inset: 0; z-index: 1000;
  background: var(--cpq-overlay-b85);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 48px 16px; overflow-y: auto;
}
.csp-panel {
  width: 100%; max-width: 640px;
  border: 1px solid var(--cpq-glass-border);
  border-radius: var(--cpq-radius-lg);
  background: var(--cpq-glass-card-bg);
  backdrop-filter: blur(var(--cpq-glass-card-blur));
  box-shadow: var(--cpq-glass-card-shadow);
  overflow: hidden;
}
.csp-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 18px 22px 14px; border-bottom: 1px solid var(--cpq-glass-border);
  background: var(--cpq-overlay-w4);
}
.csp-title { font-size: var(--cpq-font-size-lg, 16px); font-weight: 700; color: var(--cpq-text-primary); }
.csp-sub { margin-top: 2px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.csp-x {
  width: 30px; height: 30px; flex-shrink: 0; cursor: pointer;
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-sm);
  background: var(--cpq-overlay-w5); color: var(--cpq-text-secondary); font-size: 13px;
}
.csp-x:hover { color: var(--cpq-text-primary); }
.csp-body { padding: 18px 22px 22px; display: flex; flex-direction: column; gap: 18px; }
.csp-sec-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary); }
.csp-hint { margin-left: 8px; font-size: var(--cpq-font-size-xs); font-weight: 400; color: var(--cpq-text-muted); }
/* 配置确认卡 */
.csp-meta {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px;
  padding: 14px; border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-a5); border: 1px solid var(--cpq-border-primary);
}
.csp-meta-item { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.csp-meta-k { display: flex; align-items: center; gap: 6px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); }
.csp-auto-tag {
  font-style: normal; font-size: 10px; padding: 1px 7px; border-radius: var(--cpq-radius-full);
  color: var(--cpq-accent-primary); background: var(--cpq-overlay-a10); border: 1px solid var(--cpq-overlay-a15);
}
.csp-meta-v { font-size: var(--cpq-font-size-base); font-weight: 600; color: var(--cpq-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 部件清单 */
.csp-parts {
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md); overflow: hidden;
  max-height: 240px; overflow-y: auto;
}
.csp-part-row { display: flex; align-items: baseline; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--cpq-overlay-a8, var(--cpq-border-primary)); }
.csp-part-row:last-child { border-bottom: none; }
.csp-part-cat { flex: 0 0 76px; font-size: var(--cpq-font-size-xs); font-weight: 600; color: var(--cpq-text-muted); }
.csp-part-name { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.csp-part-name b { font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-text-primary); }
.csp-part-name small { font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.csp-part-qty { flex-shrink: 0; font-size: var(--cpq-font-size-sm); font-weight: 600; color: var(--cpq-text-secondary); }
.csp-parts-empty { padding: 14px; font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); border: 1px dashed var(--cpq-border-light); border-radius: var(--cpq-radius-md); text-align: center; }
/* 数量/维保/规格书行 */
.csp-edit-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end; }
.csp-field { display: flex; flex-direction: column; gap: 4px; }
.csp-field label { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.csp-field label em { color: var(--cpq-accent-danger); font-style: normal; margin-left: 2px; }
.csp-spec-btn {
  padding: 7px 16px; font-size: var(--cpq-font-size-sm); cursor: pointer; white-space: nowrap;
  border: 1px dashed var(--cpq-border-light); border-radius: var(--cpq-radius-sm);
  background: transparent; color: var(--cpq-text-secondary);
}
.csp-spec-btn:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
/* 联系信息 */
.csp-contact { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.csp-hp { position: absolute; left: -9999px; opacity: 0; height: 0; overflow: hidden; }
.csp-privacy { margin: 10px 0 0; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); line-height: 1.6; }
/* 提交 */
.csp-submit {
  padding: 11px 26px; font-size: 15px; font-weight: 600; cursor: pointer;
  color: #fff; background: var(--cpq-accent-primary); border: none; border-radius: var(--cpq-radius-md);
  transition: background 0.2s;
}
.csp-submit:hover { background: var(--cpq-accent-primary-light); }
.csp-submit:disabled { opacity: 0.6; cursor: default; }
/* 成功态 */
.csp-done { padding: 40px 22px 30px; text-align: center; }
.csp-done-ico { font-size: 26px; color: var(--cpq-color-success); }
.csp-done h4 { margin: 10px 0 6px; color: var(--cpq-text-primary); }
.csp-done p { margin: 0 0 18px; color: var(--cpq-text-secondary); font-size: var(--cpq-font-size-sm); }
.csp-btn-ghost {
  padding: 8px 20px; font-size: var(--cpq-font-size-sm); cursor: pointer;
  border: 1px solid var(--cpq-border-primary); border-radius: var(--cpq-radius-md);
  background: transparent; color: var(--cpq-text-secondary);
}
.csp-btn-ghost:hover { color: var(--cpq-accent-primary); border-color: var(--cpq-accent-primary); }
@media (max-width: 640px) {
  .csp-meta, .csp-contact { grid-template-columns: 1fr; }
  .csp-edit-row { grid-template-columns: 1fr 1fr; }
  .csp-spec-btn { grid-column: 1 / -1; justify-self: stretch; }
  .csp-submit { width: 100%; }
}
</style>
