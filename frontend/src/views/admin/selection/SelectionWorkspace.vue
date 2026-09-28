<script setup lang="ts">
/** 选型配置工作台(/strategies/selection)—— 模块工作台 shell。
 *  头部:← 解决方案 + 选型配置 + [推理配置 | 兼容规则 | BOM案例库 | 模型与参数库] 模式开关。
 *
 *  机箱能力(L0)已并入「设置-服务器管理-基准配置」编辑器(同一 base_config 实体，避免两处编辑)；
 *  配件适配(L1)曾迁「设置-服务器管理」做参考视图，2026-08-03 已移除(specs.chassis 无装配消费)。
 *  本页只剩纯「选型装配」scope：
 *   兼容规则：选型阶段声明式规则 + 编辑弹窗（搜索/分类/状态/命中次数/编辑/删除/停用）。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ThunderboltOutlined, ToolOutlined, FileTextOutlined, DatabaseOutlined } from '@ant-design/icons-vue'
import CompatibilityRuleEditor from '../CompatibilityRuleEditor.vue'
import BomCaseLibrary from './BomCaseLibrary.vue'
import AiInferConfigurator from '@/components/solution/AiInferConfigurator.vue'
import LlmCatalogAdmin from '../strategy/LlmCatalogAdmin.vue'

const router = useRouter()
type Mode = 'infer' | 'engine' | 'cases' | 'catalog'
const mode = ref<Mode>('infer')
</script>

<template>
  <div class="sw">
    <div class="sw-bar glass-light">
      <a class="sw-back" @click="router.push('/strategies')">
        <span class="sw-arrow">←</span> 解决方案
      </a>
      <span class="sw-sep">/</span>
      <span class="sw-title">选型配置</span>
      <div class="sw-toggle">
        <a-radio-group v-model:value="mode" button-style="solid" size="small">
          <a-radio-button value="infer"><ThunderboltOutlined /> 推理配置</a-radio-button>
          <a-radio-button value="engine"><ToolOutlined /> 兼容规则</a-radio-button>
          <a-radio-button value="cases"><FileTextOutlined /> BOM案例库</a-radio-button>
          <a-radio-button value="catalog"><DatabaseOutlined /> 模型与参数库</a-radio-button>
        </a-radio-group>
      </div>
    </div>

    <div class="sw-body">
      <AiInferConfigurator v-if="mode === 'infer'" />
      <CompatibilityRuleEditor v-else-if="mode === 'engine'" />
      <BomCaseLibrary v-else-if="mode === 'cases'" />
      <LlmCatalogAdmin v-else-if="mode === 'catalog'" />
    </div>
  </div>
</template>

<style scoped>
.sw { display: flex; flex-direction: column; padding: 8px 24px 40px; }
.sw-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid var(--cpq-glass-border);
  margin-bottom: 16px;
  position: sticky;
  top: calc(var(--cpq-sticky-top, 0px) + 12px);
  z-index: 5;
}
.sw-back {
  color: var(--cpq-text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: color 0.15s;
  user-select: none;
  white-space: nowrap;
}
.sw-back:hover { color: var(--cpq-accent-primary); }
.sw-arrow { margin-right: 2px; }
.sw-sep { color: var(--cpq-text-disabled); }
.sw-title { font-size: 15px; font-weight: 600; color: var(--cpq-text-primary); }
.sw-toggle { margin-left: auto; }
.sw-toggle :deep(.ant-radio-button-wrapper) { display: inline-flex; align-items: center; gap: 4px; }
.sw-body { flex: 1; min-height: 0; }
</style>
