<script setup lang="ts">
import { CloseOutlined, SaveOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { RULE_TYPE_OPTIONS, RULE_OP_OPTIONS } from '@/constants/ruleMeta'

defineProps<{
  open: boolean
  isNew: boolean
  saving: boolean
  form: any
  fieldOpts: { value: string; label: string }[]
  /** excludes 候选谓词字段(part. 前缀寻址候选件) */
  partFieldOpts?: { value: string; label: string }[]
  /** KP 类目清单(同类一致多选 / excludes 目标) */
  kpCatOptions?: { value: string; label: string }[]
  categoryOpts: { value: string; label: string }[]
  filterFn: (input: string, option: any) => boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
  (e: 'save'): void
  (e: 'add-cond'): void
  (e: 'del-cond', index: number | string): void
  (e: 'add-ex-cond'): void
  (e: 'del-ex-cond', index: number | string): void
}>()

/** excludes 候选谓词操作符:比 WHEN 多一个 not_exists(缺属性=命中即排除) */
const EX_OP_OPTIONS = [...RULE_OP_OPTIONS, { value: 'not_exists', label: '无值' }]
</script>

<template>
  <a-modal
    :open="open"
    :title="isNew ? '新建规则' : '编辑规则'"
    width="1180px"
    :footer="null"
    :mask-closable="false"
    wrap-class-name="cre-edit-modal"
    @update:open="(v: boolean) => emit('update:open', v)"
    @cancel="emit('close')"
  >
    <div class="cre-edit-grid">
      <div class="cre-edit-form glass-light">
        <a-form layout="vertical" size="small">
          <a-row :gutter="16">
            <a-col :span="9">
              <a-form-item label="规则名称">
                <a-input v-model:value="form.name" placeholder="如：选 GPU 需配 GPU 线缆" />
              </a-form-item>
            </a-col>
            <a-col :span="5">
              <a-form-item label="规则类型">
                <a-select v-model:value="form.type" :options="RULE_TYPE_OPTIONS" />
              </a-form-item>
            </a-col>
            <a-col :span="5">
              <a-form-item label="业务分类">
                <a-auto-complete
                  :value="form.category"
                  :options="categoryOpts"
                  placeholder="如：背板与线缆"
                  :filter-option="filterFn"
                  @update:value="(v: any) => form.category = String(v || '')"
                />
              </a-form-item>
            </a-col>
            <a-col :span="5">
              <a-form-item label="优先级">
                <a-input v-model:value="form.priority" placeholder="数值小者先判（空=0）" />
              </a-form-item>
            </a-col>
          </a-row>

          <a-divider orientation="left">触发条件 WHEN</a-divider>
          <a-form-item label="全部满足">
            <div v-for="(c, i) in form.whenAll" :key="i" class="cre-cond-row">
              <a-auto-complete :value="c.field" :options="fieldOpts" placeholder="字段 kp.GPU.qty" style="width: 210px" :filter-option="filterFn" @update:value="(v: any) => c.field = String(v || '')" />
              <a-select :value="c.op" style="width: 88px" :options="RULE_OP_OPTIONS" @change="(v: any) => c.op = v" />
              <a-input :value="String(c.value ?? '')" placeholder="值（兆芯 / 1 / NVMe）" style="flex: 1; min-width: 140px" @change="(e: any) => c.value = e.target.value" />
              <a-button type="text" danger size="small" @click="emit('del-cond', i)"><DeleteOutlined /></a-button>
            </div>
            <a-button type="dashed" size="small" block @click="emit('add-cond')"><PlusOutlined /> 增加条件</a-button>
          </a-form-item>

          <a-divider orientation="left">执行动作 THEN</a-divider>
          <a-form-item>
            <template v-if="form.type === 'require'">
              <div class="cre-cond-row">
                <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.GPU供电线" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
                <a-input :value="form.min_qty" placeholder="最少数量（字段或数字）" style="flex: 1" @change="(e: any) => form.min_qty = e.target.value" />
              </div>
              <div class="cre-cond-row">
                <a-input :value="form.specKey" placeholder="规格约束键（可选）" style="flex: 1" @change="(e: any) => form.specKey = e.target.value" />
                <a-input :value="form.specVal" placeholder="规格值" style="flex: 1" @change="(e: any) => form.specVal = e.target.value" />
              </div>
            </template>
            <template v-else-if="form.type === 'exclude'">
              <div class="cre-cond-row">
                <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="目标 kp.Memory" style="width: 230px" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
                <a-input :value="form.unique_field" placeholder="唯一字段（默认 pn）" style="flex: 1" @change="(e: any) => form.unique_field = e.target.value" />
              </div>
            </template>
            <template v-else-if="form.type === 'derive'">
              <a-radio-group :value="form.deriveMode" @change="(e: any) => form.deriveMode = e.target.value" style="margin-bottom: 8px">
                <a-radio value="assign">赋值（条件→固定值）</a-radio>
                <a-radio value="calc">算术（basis÷per→数量）</a-radio>
              </a-radio-group>
              <template v-if="form.deriveMode === 'assign'">
                <div class="cre-cond-row">
                  <a-auto-complete :value="form.assignField" :options="fieldOpts" placeholder="赋值字段 config.bp_type" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.assignField = String(v || '')" />
                  <a-input :value="String(form.assignValue ?? '')" placeholder="值（如 tri / dc）" style="width: 160px" @change="(e: any) => form.assignValue = e.target.value" />
                </div>
              </template>
              <template v-else>
                <div class="cre-cond-row">
                  <a-auto-complete :value="form.basis" :options="fieldOpts" placeholder="依据 config.sata_qty" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.basis = String(v || '')" />
                  <a-input-number :value="form.per" :min="1" placeholder="每 N" style="width: 120px" @change="(v: any) => form.per = v" />
                  <a-select :value="form.round" style="width: 110px" :options="[{ value: 'ceil', label: '向上取整' }, { value: 'floor', label: '向下取整' }]" @change="(v: any) => form.round = v" />
                </div>
                <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="派生目标" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
              </template>
            </template>
            <template v-else-if="form.type === 'filter'">
              <div class="cre-cond-row">
                <a-select :value="form.fScope" style="width: 130px" :options="[{ value: 'server_model', label: '候选机型' }, { value: 'kp', label: 'KP 配件' }]" @change="(v: any) => form.fScope = v" />
                <a-input :value="form.fField" placeholder="字段 series" style="flex: 1" @change="(e: any) => form.fField = e.target.value" />
                <a-select :value="form.fOp" style="width: 88px" :options="RULE_OP_OPTIONS" @change="(v: any) => form.fOp = v" />
                <a-input :value="form.fValue" placeholder="值（字段或字面）" style="flex: 1" @change="(e: any) => form.fValue = e.target.value" />
              </div>
            </template>
            <template v-else-if="form.type === 'recommend'">
              <a-auto-complete :value="form.target" :options="fieldOpts" placeholder="推荐目标 kp.GPU" style="width: 100%" :filter-option="filterFn" @update:value="(v: any) => form.target = String(v || '')" />
            </template>
            <template v-else-if="form.type === 'homogeneous'">
              <a-form-item label="同类一致类目（勾选类目内出现多种即冲突）">
                <a-select v-model:value="form.homoCats" mode="multiple" :options="kpCatOptions || []" placeholder="如：Memory / CPU / GPU" />
              </a-form-item>
              <div class="cre-cond-row">
                <span style="color: var(--cpq-text-secondary); font-size: 12px">判同字段</span>
                <a-input v-model:value="form.homoField" placeholder="pn（默认）" style="width: 220px" />
              </div>
            </template>
            <template v-else-if="form.type === 'resource'">
              <div class="cre-cond-row">
                <a-auto-complete :value="form.resLhsField" :options="fieldOpts" placeholder="左侧 config.tdp_sum" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.resLhsField = String(v || '')" />
                <span style="color: var(--cpq-text-secondary); font-size: 12px">×</span>
                <a-input :value="form.resLhsScale" placeholder="倍率(可空)" style="width: 110px" @change="(e: any) => form.resLhsScale = e.target.value" />
                <a-select :value="form.resOp" style="width: 88px" :options="RULE_OP_OPTIONS.filter(o => ['<=','>=','<','>','=='].includes(o.value))" @change="(v: any) => form.resOp = v" />
                <a-auto-complete :value="form.resRhsField" :options="fieldOpts" placeholder="右侧 config.psu_capacity" style="flex: 1" :filter-option="filterFn" @update:value="(v: any) => form.resRhsField = String(v || '')" />
                <span style="color: var(--cpq-text-secondary); font-size: 12px">×</span>
                <a-input :value="form.resRhsScale" placeholder="倍率(可空)" style="width: 110px" @change="(e: any) => form.resRhsScale = e.target.value" />
              </div>
              <p style="margin: 4px 0 0; color: var(--cpq-text-muted); font-size: 12px">约束不满足 = 硬违规；两侧缺数据（如 PSU 容量未录）时引擎跳过并记模型告警，不误报。</p>
            </template>
            <template v-else-if="form.type === 'excludes'">
              <a-form-item label="被排除的类目（该类目下命中条件的候选件不出现）">
                <a-auto-complete :value="form.exTarget" :options="kpCatOptions || []" placeholder="如：Raid card" style="width: 260px" :filter-option="filterFn" @update:value="(v: any) => form.exTarget = String(v || '')" />
              </a-form-item>
              <a-form-item label="候选排除条件（part. 前缀寻址候选件；命中即排除）">
                <div v-for="(c, i) in form.exConds" :key="i" class="cre-cond-row">
                  <a-auto-complete :value="c.field" :options="partFieldOpts || []" placeholder="part.spec.电容" style="width: 220px" :filter-option="filterFn" @update:value="(v: any) => c.field = String(v || '')" />
                  <a-select :value="c.op" style="width: 96px" :options="EX_OP_OPTIONS" @change="(v: any) => c.op = v" />
                  <a-input :value="String(c.value ?? '')" placeholder="值（无值型可空）" style="flex: 1; min-width: 120px" @change="(e: any) => c.value = e.target.value" />
                  <a-button type="text" danger size="small" @click="emit('del-ex-cond', i)"><DeleteOutlined /></a-button>
                </div>
                <a-button type="dashed" size="small" block @click="emit('add-ex-cond')"><PlusOutlined /> 增加排除条件</a-button>
              </a-form-item>
            </template>
          </a-form-item>

          <a-divider orientation="left">说明</a-divider>
          <a-form-item><a-input v-model:value="form.desc" placeholder="规则描述（可选）" /></a-form-item>
        </a-form>
      </div>
    </div>
    <div class="cre-edit-foot">
      <a-button @click="emit('close')"><CloseOutlined /> 取消</a-button>
      <a-button type="primary" :loading="saving" @click="emit('save')"><SaveOutlined /> 保存</a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.cre-edit-grid { display: grid; grid-template-columns: 1fr; gap: 16px; height: min(620px, 66vh); }
.cre-edit-form { padding: 18px 22px; border-radius: var(--cpq-radius-md); overflow-y: auto; }
.cre-edit-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.cre-cond-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }

@media (max-width: 980px) {
  .cre-edit-grid { grid-template-columns: 1fr; height: auto; }
}
</style>
