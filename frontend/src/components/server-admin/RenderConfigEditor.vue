<script setup lang="ts">
/** 渲染参数编辑器 — 编辑 3D 展示的灯光、色调映射、曝光度等参数。
 *  支持浅色/深色主题分别配置。 */
import { computed } from 'vue'
import { Slider } from 'ant-design-vue'
import type { RenderConfig } from '@/components/server-config/showcase-config'

const props = defineProps<{
  config: RenderConfig
  theme: 'light' | 'dark'
}>()

const emit = defineEmits<{
  (e: 'update:config', value: RenderConfig): void
}>()

const localConfig = computed({
  get: () => props.config,
  set: (val) => emit('update:config', val),
})

function updateField(key: keyof RenderConfig, value: any) {
  emit('update:config', { ...props.config, [key]: value })
}

function handleColorChange(key: keyof RenderConfig, event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:config', { ...props.config, [key]: target.value })
}

const toneMappingOptions = [
  { label: '无色调映射', value: 'NoToneMapping' },
  { label: '线性色调映射', value: 'LinearToneMapping' },
  { label: 'ACES 电影级色调映射', value: 'ACESFilmicToneMapping' },
]
</script>

<template>
  <div class="render-config-editor">
    <div class="config-group">
      <h4>灯光强度</h4>

      <div class="field-row">
        <label>环境光</label>
        <Slider
          :value="localConfig.ambient_intensity"
          @change="(v: number | [number, number]) => updateField('ambient_intensity', v as number)"
          :min="0"
          :max="2"
          :step="0.1"
          :marks="{ 0: '0', 0.6: '默认', 2: '2' }"
        />
      </div>

      <div class="field-row">
        <label>主光源</label>
        <Slider
          :value="localConfig.key_light_intensity"
          @change="(v: number | [number, number]) => updateField('key_light_intensity', v as number)"
          :min="0"
          :max="3"
          :step="0.1"
          :marks="{ 0: '0', 1.45: '默认', 3: '3' }"
        />
      </div>

      <div class="field-row">
        <label>补光</label>
        <Slider
          :value="localConfig.fill_light_intensity"
          @change="(v: number | [number, number]) => updateField('fill_light_intensity', v as number)"
          :min="0"
          :max="1"
          :step="0.05"
          :marks="{ 0: '0', 0.35: '默认', 1: '1' }"
        />
      </div>
    </div>

    <div class="config-group">
      <h4>灯光颜色</h4>

      <div class="field-row color-row">
        <label>主光源颜色</label>
        <input
          type="color"
          :value="localConfig.key_light_color || '#ffffff'"
          @change="(e) => handleColorChange('key_light_color', e)"
          class="color-picker"
        />
      </div>

      <div class="field-row color-row">
        <label>补光颜色</label>
        <input
          type="color"
          :value="localConfig.fill_light_color || '#bfd4ff'"
          @change="(e) => handleColorChange('fill_light_color', e)"
          class="color-picker"
        />
      </div>

      <div class="field-row color-row">
        <label>背景颜色</label>
        <input
          type="color"
          :value="localConfig.background_color || '#000000'"
          @change="(e) => handleColorChange('background_color', e)"
          class="color-picker"
        />
        <span class="field-hint">可选，留空使用透明背景</span>
      </div>
    </div>

    <div class="config-group">
      <h4>色调与曝光</h4>

      <div class="field-row">
        <label>色调映射</label>
        <a-select
          :value="localConfig.tone_mapping || 'NoToneMapping'"
          @change="(v: string) => updateField('tone_mapping', v)"
          :options="toneMappingOptions"
          style="width: 200px"
        />
      </div>

      <div class="field-row">
        <label>曝光度</label>
        <Slider
          :value="localConfig.exposure"
          @change="(v: number | [number, number]) => updateField('exposure', v as number)"
          :min="0"
          :max="3"
          :step="0.1"
          :marks="{ 0: '0', 1: '默认', 3: '3' }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.render-config-editor {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-group {
  border: 1px solid var(--cpq-overlay-w10);
  border-radius: 8px;
  padding: 12px;
}

.config-group h4 {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--cpq-text-secondary, #9BA1AA);
}

.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.field-row:last-child {
  margin-bottom: 0;
}

.field-row label {
  width: 100px;
  font-size: 13px;
  color: var(--cpq-text-primary, #E8ECEF);
  flex-shrink: 0;
}

.field-row .ant-slider {
  flex: 1;
}

.color-row {
  align-items: flex-start;
}

.color-row .vc-compact {
  flex-shrink: 0;
}

.field-hint {
  font-size: 11px;
  color: var(--cpq-text-muted, #6E7582);
  font-style: italic;
}
</style>