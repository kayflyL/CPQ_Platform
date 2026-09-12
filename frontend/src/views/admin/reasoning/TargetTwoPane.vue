<script setup lang="ts">
/** 节点目标层双栏面板（公共组件）：凡输出物是表格/表单的节点统一调用。
 * 左栏 = 该节点输出给下游的字段契约：字段名只读（权威在表单定义/节点配置），
 *        可配「必填」开关与候选来源；字段与开关状态均由父组件持有，本组件零状态。
 * 右栏 = 输出物实时预览（具名插槽注入，预览即真实页，不造演示皮）。
 * 统一大脑原则：每个节点的执行者都是同一个 AI 角色，节点 prompt 驱动——
 * 「必填」是所有节点字段共有的策略位，不只是登记节点特权。 */
export interface TargetFieldRow {
  key: string
  label: string
  hint?: string
  /** 分组标题（组名变化处渲染分组条，如「部件清单 · KP 大类」） */
  group?: string
  ask?: boolean
  askDisabled?: boolean
  /** 可选：字段候选来源（登记策略用），不传则不渲染 */
  source?: { value: string; options: { value: string; label: string }[] }
}
defineProps<{
  fields: TargetFieldRow[]
  leftTitle?: string
  leftHint?: string
  rightTitle?: string
  rightHint?: string
}>()
const emit = defineEmits<{
  'ask-change': [key: string, val: boolean]
  'source-change': [key: string, val: string]
}>()
</script>

<template>
  <div class="ttp">
    <div class="ttp-pane ttp-left">
      <h4 class="ttp-title">{{ leftTitle || '输出字段' }}<span v-if="leftHint" class="ttp-hint">{{ leftHint }}</span></h4>
      <div class="ttp-row ttp-head"><span>字段</span><span>说明 / 来源</span><span>必填</span></div>
      <template v-for="(f, i) in fields" :key="f.key">
        <div v-if="f.group && f.group !== fields[i - 1]?.group" class="ttp-group">{{ f.group }}</div>
        <div class="ttp-row">
          <span class="ttp-name">{{ f.label }}</span>
          <span class="ttp-mid">
            <span v-if="f.hint" class="ttp-desc">{{ f.hint }}</span>
            <a-select v-if="f.source" size="small" style="width: 118px" :value="f.source.value"
                      :options="f.source.options"
                      @change="(v: any) => emit('source-change', f.key, String(v))" />
          </span>
          <a-switch :checked="!!f.ask" size="small" :disabled="f.askDisabled"
                    @change="(v: any) => emit('ask-change', f.key, !!v)" />
        </div>
      </template>
      <slot name="left-foot" />
    </div>
    <div class="ttp-pane ttp-right">
      <h4 class="ttp-title">{{ rightTitle || '预览' }}<span v-if="rightHint" class="ttp-hint">{{ rightHint }}</span></h4>
      <slot name="preview" />
    </div>
  </div>
</template>

<style scoped>
.ttp { display: grid; grid-template-columns: 378px 1fr; gap: 16px; align-items: start; }
.ttp-pane { border: 1px solid var(--cpq-overlay-w08, rgba(255, 255, 255, .08)); border-radius: 10px; padding: 12px 14px; background: var(--cpq-overlay-w02, rgba(255, 255, 255, .02)); }
.ttp-left { max-height: 62vh; overflow-y: auto; }
.ttp-right { min-height: 320px; max-height: 62vh; overflow-y: auto; }
.ttp-title { margin: 0 0 8px; font-size: 13px; font-weight: 700; color: var(--cpq-text-primary); }
.ttp-hint { margin-left: 8px; font-size: 11px; font-weight: 400; color: var(--cpq-text-muted); }
.ttp-row { display: grid; grid-template-columns: 104px 1fr 40px; gap: 8px; align-items: center; padding: 5px 2px; font-size: 12px; }
.ttp-row .ant-switch { width: 36px; min-width: 36px; justify-self: start; }
.ttp-head { font-size: 11px; color: var(--cpq-text-muted); border-bottom: 1px solid var(--cpq-overlay-w06, rgba(255, 255, 255, .06)); padding-bottom: 6px; }
.ttp-group { margin-top: 10px; padding: 5px 8px; border-radius: 6px; background: var(--cpq-overlay-w04, rgba(255, 255, 255, .04)); font-size: 11px; color: var(--cpq-text-muted); }
.ttp-name { color: var(--cpq-text-primary); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ttp-mid { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.ttp-desc { color: var(--cpq-text-secondary); font-size: 11px; line-height: 1.4; }
</style>
