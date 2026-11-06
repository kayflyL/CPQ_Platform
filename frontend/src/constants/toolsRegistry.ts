/**
 * 工具注册表 —— 工具中心/工具页的结构单一来源（2026-11-06 原型批准）。
 * 只管结构：key / 路由 / 页签组件懒加载 / 图标；展示文案不在这里（走 rules.tool_contents 表，
 * 默认文案在这里只作 DB 故障降级，与后端 tool_content_repo 种子同源，改文案两处同步）。
 * 加新工具 = 注册表登记 + 后端 repo 种子加默认文案，后台编辑器即出现可编辑。
 */
import {
  AppstoreOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import type { Component } from 'vue'

export interface ToolDocItem {
  title: string
  formula: string
  text: string
}

/** 工具内容 blob（后端整存整取；编辑器编辑的就是这份结构） */
export interface ToolContent {
  /* 工具中心卡片 */
  name: string
  desc: string
  category: string
  tags: string[]
  order: number
  visible: boolean
  /* 工具页 */
  page_title: string
  page_sub: string
  doc_visible: boolean
  doc_title: string
  doc_items: ToolDocItem[]
  cta_visible: boolean
  cta_text: string
  cta_button: string
  /** 站内路由（编辑器下拉预设：/servers /catalog /strategies） */
  cta_target: string
}

/** 图标名 → antd 图标组件（工具中心卡片徽标；新图标在这里登记） */
export const TOOL_ICONS: Record<string, Component> = {
  chip: ThunderboltOutlined,
  appstore: AppstoreOutlined,
}

export interface ToolDef {
  key: string
  /** 站内路由（/tools/<key>） */
  path: string
  /** 图标名（TOOL_ICONS 里的 key） */
  icon: string
  /** 工具页页签（首期 GPU 工具=推理配置+模型与参数库；单页签工具不显示页签条） */
  tabs: { key: string; label: string; comp: () => Promise<Component> }[]
  /** 默认文案（DB 故障/空值降级；权威源=rules.tool_contents） */
  defaultContent: ToolContent
}

/** 工具清单：首期只有 GPU 显存计算器（现有页面组件零改动迁入双页签） */
export const TOOLS: ToolDef[] = [
  {
    key: 'gpu-sizing',
    path: '/tools/gpu-sizing',
    icon: 'chip',
    tabs: [
      { key: 'infer', label: '推理配置', comp: () => import('@/components/solution/AiInferConfigurator.vue') },
      { key: 'catalog', label: '模型与参数库', comp: () => import('@/views/admin/strategy/LlmCatalogAdmin.vue') },
    ],
    defaultContent: {
      name: 'GPU 显存计算器',
      desc: '按大模型、量化精度、推理框架与并发估算显存需求；哪些卡装得下、装几张，一目了然。配套「模型与参数库」维护模型/框架/场景参数。',
      category: 'AI 算力选型',
      tags: ['推理配置', '模型与参数库'],
      order: 100,
      visible: true,
      page_title: 'GPU 显存计算器',
      page_sub: '选大模型与部署方式，估显存需求、匹配可用的卡。',
      doc_visible: true,
      doc_title: '公式是怎么算的',
      doc_items: [
        { title: '权重显存', formula: '参数量(B) × 字节系数 × 框架系数', text: '字节系数由量化精度决定（4bit≈0.5、8bit≈1、16bit≈2），框架系数取自推理框架库，可在「模型与参数库」中调整。' },
        { title: 'KV 缓存', formula: '2 × 层数 × KV头数 × 头维 × 上下文 × 并发 × 字节', text: '随上下文长度与并发数线性增长；注意力结构（GQA/MHA/MLA）决定 KV 头数。' },
        { title: '卡型匹配', formula: '可用显存 = 单卡容量 × 张数 − 框架开销 ≥ 需求总量', text: '需求侧先算准、再对卡型批量试算；每张卡给出推荐张数与最低张数，可在卡砖上直接调张数重算。' },
    ],
      cta_visible: true,
      cta_text: '显存算准了？挑一台能装下这些卡的服务器，直接进配置向导。',
      cta_button: '去配置服务器 →',
      cta_target: '/servers',
    },
  },
]
