/** 机型目录页 3D 展示区配置：按分类名匹配 GLB 路径与介绍文案。无映射返回 null。 */

export interface ShowcaseConfig {
  src: string
  title: string
  desc: string
  bullets: string[]
}

const CONFIGS: Record<string, ShowcaseConfig> = {
  // 仅映射已提供 GLB 文件的分类；新增 GLB 时在此加一条即可点亮对应分类页
  ai: {
    src: '/models/ai-server.glb',
    title: 'AI 加速计算服务器',
    desc: '面向大模型训练与高密度推理，多 GPU 并行扩展，提供超高算力与高带宽互联。',
    bullets: [
      '多路 GPU 并行，支撑大规模训练与推理',
      '高速互联，跨卡低延迟通信',
      '高功率散热设计，稳定满载运行',
    ],
  },
}

/** 按分类名关键字匹配；未命中返回 null（页面据此不渲染该区块）。 */
export function matchShowcase(typeName: string): ShowcaseConfig | null {
  if (!typeName) return null
  if (/AI|加速/.test(typeName)) return CONFIGS.ai ?? null
  return null
}
