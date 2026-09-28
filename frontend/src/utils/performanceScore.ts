/** 性能六维打分引擎（纯函数，无框架依赖）。
 *  分层铁律：锚点数值住 DB（system_config performance_score_config，管理面可调零发版）；
 *  本文件只写形状 = 聚合结果→分数的分段线性插值与缺数据策略，不含任何拍脑袋分数。
 *  原始值由 ConfigWizard 从 kpLines×specs / 机箱能力档案确定性聚合后传入；
 *  缺数据的维度 score=null（雷达顶点缩心+灰标「未维护」），不编造。 */

export interface ScoreAnchor { score: number; value: number }

export interface PerfDimConfig {
  label?: string
  unit?: string
  enabled?: boolean
  anchors?: ScoreAnchor[]
  /** 副锚点（内存维度：容量为主锚点 + 带宽按 sub_weight 混合；带宽未维护→只按主锚点计分） */
  sub_anchors?: ScoreAnchor[]
  sub_weight?: number
}

export interface PerfScoreConfig {
  version?: number
  dims?: Record<string, PerfDimConfig>
}

/** 内置默认锚点：60=主流线 / 100=旗舰线。DB 未配置或某维缺省时回落此表。 */
export const DEFAULT_PERF_SCORE_CONFIG: PerfScoreConfig = {
  version: 1,
  dims: {
    cpu_compute: { label: 'CPU 算力', unit: '核', anchors: [{ score: 0, value: 0 }, { score: 60, value: 128 }, { score: 100, value: 192 }] },
    memory: {
      label: '内存能力', unit: 'GB',
      anchors: [{ score: 0, value: 0 }, { score: 60, value: 512 }, { score: 100, value: 2048 }],
      sub_anchors: [{ score: 0, value: 0 }, { score: 60, value: 200 }, { score: 100, value: 800 }],
      sub_weight: 0.45,
    },
    storage_io: { label: '存储 IO', unit: '加权盘位', anchors: [{ score: 0, value: 0 }, { score: 60, value: 12 }, { score: 100, value: 24 }] },
    network: { label: '网络吞吐', unit: 'Gbps', anchors: [{ score: 0, value: 0 }, { score: 60, value: 200 }, { score: 100, value: 800 }] },
    gpu_compute: { label: 'GPU 算力', unit: 'TFLOPS(FP16)', anchors: [{ score: 0, value: 0 }, { score: 60, value: 300 }, { score: 100, value: 800 }] },
    reliability: { label: '系统可靠性', unit: '冗余项', anchors: [{ score: 0, value: 0 }, { score: 60, value: 2 }, { score: 100, value: 3 }] },
  },
}

/** 分段线性插值（锚点按 value 升序；低于首锚取首锚分，超出末锚封顶末锚分） */
export function interpolateScore(value: number, anchors: ScoreAnchor[]): number {
  const pts = [...anchors].sort((a, b) => a.value - b.value)
  if (!pts.length) return 0
  if (value <= pts[0].value) return pts[0].score
  const last = pts[pts.length - 1]
  if (value >= last.value) return last.score
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]
    const b = pts[i]
    if (value <= b.value) {
      const t = (value - a.value) / (b.value - a.value)
      return Math.round(a.score + t * (b.score - a.score))
    }
  }
  return last.score
}

export interface PerfRawInput {
  cpuCores: number
  memCapacityGb: number
  memBandwidthGbs: number | null
  storageWeighted: number | null
  networkGbps: number | null
  gpuFp16Tflops: number | null
  reliabilityCount: number | null
  /** 各维行级构成文本（如 "2×25G + 2×100G"），拼进打分明细增强可解释性 */
  cpuText?: string
  memText?: string
  storageText?: string
  networkText?: string
  gpuText?: string
  reliabilityText?: string
}

export interface PerfDimResult {
  key: string
  label: string
  /** null = 原始值未维护（不编造，雷达缩心+灰标） */
  score: number | null
  rawText: string
  /** 打分依据（锚点 + 行级构成），维度 popover 展示 */
  detail: string
}

const fmtNum = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(1))
const anchorsText = (anchors: ScoreAnchor[], unit?: string): string =>
  anchors.map(a => `${a.score}→${fmtNum(a.value)}${unit || ''}`).join(' / ')

export function computePerformanceScores(raw: PerfRawInput, cfg?: PerfScoreConfig | null): PerfDimResult[] {
  const userDims = cfg?.dims || {}
  const dim = (key: string): PerfDimConfig => ({ ...(DEFAULT_PERF_SCORE_CONFIG.dims![key]!), ...(userDims[key] || {}) })
  const out: PerfDimResult[] = []

  const push = (key: string, value: number | null, text: string, extraDetail: string) => {
    const d = dim(key)
    if (d.enabled === false) return
    const anchors = d.anchors || []
    out.push({
      key,
      label: d.label || key,
      score: value == null ? null : interpolateScore(value, anchors),
      rawText: text,
      detail: `锚点 ${anchorsText(anchors, d.unit)}${extraDetail ? ' · ' + extraDetail : ''}`,
    })
  }

  // CPU：核数代理（FP64 峰值 specs 覆盖低，明细注明折算方式）
  push('cpu_compute', raw.cpuCores > 0 ? raw.cpuCores : null,
    raw.cpuCores > 0 ? `${fmtNum(raw.cpuCores)} 核` : '',
    (raw.cpuText ? raw.cpuText + ' · ' : '') + '按核数折算（FP64 峰值未维护）')

  // 内存：容量主锚点 + 带宽副锚点混合；带宽未维护→只按容量
  {
    const d = dim('memory')
    if (d.enabled !== false) {
      const anchors = d.anchors || []
      const hasMem = raw.memCapacityGb > 0
      let score: number | null = null
      let text = ''
      let extra = ''
      if (hasMem && raw.memBandwidthGbs != null && d.sub_anchors?.length) {
        const w = d.sub_weight ?? 0.45
        score = Math.round(
          interpolateScore(raw.memCapacityGb, anchors) * (1 - w)
          + interpolateScore(raw.memBandwidthGbs, d.sub_anchors) * w,
        )
        text = `${fmtNum(raw.memCapacityGb)} GB · 带宽约 ${fmtNum(raw.memBandwidthGbs)} GB/s(估)`
        extra = `容量${Math.round((1 - w) * 100)}%+带宽${Math.round(w * 100)}%（带宽=Σ条数×速率×8B）${raw.memText ? ' · ' + raw.memText : ''}`
      } else if (hasMem) {
        score = interpolateScore(raw.memCapacityGb, anchors)
        text = `${fmtNum(raw.memCapacityGb)} GB`
        extra = '带宽未维护，按容量计分'
      }
      out.push({ key: 'memory', label: d.label || 'memory', score, rawText: text, detail: `锚点 ${anchorsText(anchors, d.unit)}${extra ? ' · ' + extra : ''}` })
    }
  }

  // 存储：类型加权盘位（NVMe 1.0 / SAS 0.6 / SATA 0.4 / 其他 0.5）
  push('storage_io', raw.storageWeighted != null && raw.storageWeighted > 0 ? raw.storageWeighted : null,
    raw.storageWeighted != null && raw.storageWeighted > 0 ? `加权 ${fmtNum(raw.storageWeighted)} 盘位` : '',
    (raw.storageText ? raw.storageText + ' · ' : '') + 'NVMe×1.0 / SAS×0.6 / SATA×0.4')

  // 网络：Σ 口数×端口速率
  push('network', raw.networkGbps != null && raw.networkGbps > 0 ? raw.networkGbps : null,
    raw.networkGbps != null && raw.networkGbps > 0 ? `${fmtNum(raw.networkGbps)} Gbps` : '',
    raw.networkText || '')

  // GPU：FP16 峰值（specs 未维护→null，不按显存/瓦数折算）
  push('gpu_compute', raw.gpuFp16Tflops != null && raw.gpuFp16Tflops > 0 ? raw.gpuFp16Tflops : null,
    raw.gpuFp16Tflops != null && raw.gpuFp16Tflops > 0 ? `${fmtNum(raw.gpuFp16Tflops)} TFLOPS(FP16)` : '',
    raw.gpuText || 'FP16 峰值未维护')

  // 可靠性：命中冗余项（PSU≥2 / RAID 卡 / MTBF）；PSU 与 MTBF 全未知→null
  push('reliability', raw.reliabilityCount,
    raw.reliabilityCount != null ? `命中 ${raw.reliabilityCount} 项` : '',
    raw.reliabilityText || '')

  return out
}
