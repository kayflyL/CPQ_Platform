<script setup lang="ts">
/**
 * 公开线索登记表（LeadSubmitForm）—— 商机详情页线索登记表（RequirementForm）的公开宿主。
 * 复用同一组件（publicMode：下拉走公开白名单 API），只加：
 * 客户信息段（置首）+ 需求附件（嵌需求原文与配置之间，同商机详情页）+ 蜜罐 + 隐私提示；提交走 multipart（附件随表单）。
 */
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import RequirementForm from '@/components/flow/RequirementForm.vue'
import DeliveryRegionSelect from '@/components/common/DeliveryRegionSelect.vue'
import { publicLeadApi } from '@/api/publicIntake'
import { NOT_LISTED_REGION_VALUE } from '@/constants/regions'

const props = withDefaults(defineProps<{
  source?: 'catalog_model' | 'catalog_general'
  /** 配置完成页带入：机型/配置意向（RequirementSlots 子集），fromSlots 回填 */
  initialSlots?: Record<string, any> | null
}>(), {
  source: 'catalog_general',
  initialSlots: null,
})

const emit = defineEmits<{ (e: 'submitted', res: { ok: boolean; lead_id: string | null; merged: boolean }): void }>()

const reqForm = ref<InstanceType<typeof RequirementForm> | null>(null)
const reqText = ref('')
const company = ref('')
const contactName = ref('')
const contactPhone = ref('')
const contactEmail = ref('')
const deliveryRegion = ref('')
const website = ref('')          // 蜜罐：真实用户不可见必为空
const files = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const submitting = ref(false)
const done = ref<{ merged: boolean } | null>(null)

function addFiles(e: Event) {
  const input = e.target as HTMLInputElement
  for (const f of Array.from(input.files || [])) {
    if (files.value.length >= 5) { message.warning('附件最多 5 个'); break }
    if (f.size > 20 * 1024 * 1024) { message.warning(`单个附件过大（>20MB）：${f.name}`); continue }
    files.value.push(f)
  }
  input.value = ''
}
function removeFile(i: number) { files.value.splice(i, 1) }

function extOk(name: string) {
  return /\.(xlsx|xls|csv|pdf|docx|doc|png|jpg|jpeg|gif|bmp|txt)$/i.test(name)
}

// 配置完成页带入的选型快照：回填登记表（机型/配置意向/KP 行）
onMounted(() => {
  if (props.initialSlots) reqForm.value?.fromSlots(props.initialSlots as any)
})

async function submit() {
  if (!website.value.trim()) {
    if (!company.value.trim()) { message.warning('请填写公司名称'); return }
    if (!/^1\d{10}$/.test(contactPhone.value.trim())) { message.warning('请填写 11 位手机号'); return }
    if (!deliveryRegion.value) { message.warning('请选择交付地区'); return }
    if (files.value.some((f) => !extOk(f.name))) { message.warning('附件格式不支持'); return }
  }
  const slots = reqForm.value?.toSlots() || {}
  submitting.value = true
  try {
    const res = await publicLeadApi.submit({
      requirement_text: reqText.value,
      company: company.value,
      contact_name: contactName.value,
      contact_phone: contactPhone.value,
      contact_email: contactEmail.value,
      delivery_region: deliveryRegion.value,
      source: props.source,
      config_slots: JSON.stringify(slots),
      files: files.value,
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
  <div class="lead-submit">
    <!-- 客户信息置首：先留联系方式，再填需求 -->
    <section class="ls-sec">
      <h4 class="ls-sec-title">客户信息</h4>
      <div class="contact-grid">
        <div class="cg-item"><label>公司名称<em>*</em></label><input v-model="company" placeholder="客户全称"></div>
        <div class="cg-item"><label>联系人姓名<em>*</em></label><input v-model="contactName" placeholder="怎么称呼您"></div>
        <div class="cg-item"><label>手机号<em>*</em></label><input v-model="contactPhone" placeholder="11 位手机号"></div>
        <div class="cg-item"><label>工作邮箱</label><input v-model="contactEmail" placeholder="name@company.com（选填）"></div>
        <div class="cg-item cg-region">
          <label>交付地区<em>*</em></label>
          <DeliveryRegionSelect v-model:value="deliveryRegion" />
          <p class="cg-hint">硬件仅配送至下拉列表所列地区，软件与维保服务全球交付。</p>
          <p v-if="deliveryRegion === NOT_LISTED_REGION_VALUE" class="region-tip">
            该地区暂不支持硬件交付——软件与维保服务仍全球供货。欢迎提交需求，我们将与您确认可行的方案。
          </p>
        </div>
      </div>
      <!-- 蜜罐：隐藏字段，机器人填写即静默丢弃 -->
      <input v-model="website" name="website" tabindex="-1" autocomplete="off" class="hp-field">
      <p class="privacy-line">提交即表示同意我们仅将以上信息用于本次咨询联系，不做其他用途。</p>
    </section>

    <!-- 需求信息：与商机详情页线索登记表同构（RequirementForm 复用）；附件嵌在需求原文与配置之间（同商机详情页） -->
    <RequirementForm ref="reqForm" v-model:req-text="reqText" :public-mode="true">
      <template #after-req-text>
        <section class="ls-sec">
          <h4 class="ls-sec-title">需求附件<span class="ls-hint">选填 · 招标书 / 配置清单 / 现场照片，随线索一起转给业务</span></h4>
          <div class="att-chips">
            <span v-for="(f, i) in files" :key="f.name + i" class="att-chip">
              <b>{{ f.name }}</b><span class="sz">{{ (f.size / 1024).toFixed(0) }} KB</span>
              <button type="button" @click="removeFile(i)">✕</button>
            </span>
          </div>
          <div class="att-upload">
            <button class="att-btn" type="button" @click="fileInput?.click()">＋ 上传附件</button>
            <span>Word / Excel / PDF / 图片 · 单个 ≤ 20MB · 最多 5 个</span>
            <input ref="fileInput" type="file" multiple hidden accept=".xlsx,.xls,.csv,.pdf,.docx,.doc,.png,.jpg,.jpeg,.gif,.bmp,.txt" @change="addFiles">
          </div>
        </section>
      </template>
    </RequirementForm>

    <button class="submit-btn" type="button" :disabled="submitting" @click="submit">
      {{ submitting ? '提交中…' : '提交需求登记 →' }}
    </button>

    <div v-if="done" class="done-pane">
      <div class="done-ico">✓</div>
      <h4>{{ done.merged ? '您的信息已并入之前的提交' : '已收到您的需求登记' }}</h4>
      <p>{{ done.merged ? '检测到您此前已提交过，本次内容已合并给同一负责人跟进。' : '我们会在 1 个工作日内与您联系，请保持手机畅通。' }}</p>
    </div>
  </div>
</template>

<style scoped>
.lead-submit { display: flex; flex-direction: column; gap: 18px; }
.ls-sec-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: var(--cpq-text-secondary); }
.ls-hint { margin-left: 8px; font-size: var(--cpq-font-size-xs); font-weight: 400; color: var(--cpq-text-muted); }
.att-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.att-chip {
  display: inline-flex; align-items: center; gap: 8px; padding: 5px 12px;
  font-size: var(--cpq-font-size-sm); border-radius: var(--cpq-radius-md);
  background: var(--cpq-overlay-a5); border: 1px solid var(--cpq-border-primary);
}
.att-chip b { color: var(--cpq-text-primary); font-weight: 600; }
.att-chip .sz { color: var(--cpq-text-muted); font-size: var(--cpq-font-size-xs); }
.att-chip button { background: none; border: none; color: var(--cpq-text-muted); cursor: pointer; }
.att-chip button:hover { color: var(--cpq-accent-danger); }
.att-upload { display: flex; align-items: center; gap: 10px; margin-top: 8px; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); flex-wrap: wrap; }
.att-btn {
  padding: 5px 14px; font-size: var(--cpq-font-size-sm); cursor: pointer;
  border: 1px dashed var(--cpq-border-light); border-radius: var(--cpq-radius-sm);
  background: transparent; color: var(--cpq-text-secondary);
}
.att-btn:hover { border-color: var(--cpq-accent-primary); color: var(--cpq-accent-primary); }
.contact-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item label { font-size: var(--cpq-font-size-sm); color: var(--cpq-text-muted); }
.cg-item label em { color: var(--cpq-accent-danger); font-style: normal; margin-left: 2px; }
.cg-item input {
  padding: 8px 12px; font-size: var(--cpq-font-size-base); font-family: inherit;
  color: var(--cpq-text-primary); background: var(--cpq-glass-2-bg);
  border: 1px solid var(--cpq-glass-border); border-radius: var(--cpq-radius-sm); outline: none;
}
.cg-item input:focus { border-color: var(--cpq-accent-primary); box-shadow: 0 0 0 2px var(--cpq-overlay-a15); }
.cg-hint { margin: 2px 0 0; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); line-height: 1.6; }
.region-tip {
  margin: 6px 0 0; padding: 8px 12px; font-size: var(--cpq-font-size-xs); line-height: 1.7;
  color: var(--cpq-text-secondary); border-radius: var(--cpq-radius-sm);
  background: var(--cpq-warn-surface); border: 1px solid var(--cpq-warn-border);
}
.hp-field { position: absolute; left: -9999px; opacity: 0; height: 0; overflow: hidden; }
.privacy-line { margin: 10px 0 0; font-size: var(--cpq-font-size-xs); color: var(--cpq-text-muted); line-height: 1.6; }
.submit-btn {
  align-self: flex-start; padding: 10px 28px; font-size: 15px; font-weight: 600;
  color: #fff; background: var(--cpq-accent-primary); border: none; border-radius: var(--cpq-radius-md);
  cursor: pointer; transition: background 0.2s;
}
.submit-btn:hover { background: var(--cpq-accent-primary-light); }
.submit-btn:disabled { opacity: 0.6; cursor: default; }
.done-pane { padding: 20px; border-radius: var(--cpq-radius-lg); background: var(--cpq-overlay-success15); border: 1px solid rgba(82, 201, 160, 0.4); text-align: center; }
.done-ico { font-size: 26px; color: var(--cpq-color-success); }
.done-pane h4 { margin: 8px 0 4px; }
.done-pane p { margin: 0; color: var(--cpq-text-secondary); font-size: var(--cpq-font-size-sm); }
@media (max-width: 640px) {
  .contact-grid { grid-template-columns: 1fr; }
  .submit-btn { align-self: stretch; }
}
</style>
