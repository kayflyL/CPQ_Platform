/** 商机详情各节点弹窗的统一口径：宽度四档 + body 高度上限，全部配合 centered 使用。
 *  antd 居中后去掉默认 top:100px / paddingBottom:24px，header + 内容边距约 95px，
 *  -120px 一并扣住，body 拉满时弹窗整体距视口仍留 ~25px，不再出现底缘被裁必须滚动。
 *
 *  手机端（≤768）口径：full/sheet/viewer 三档经 components/common/ResponsiveModal.vue
 *  转【全屏页】（左上角返回按钮 + 系统返回手势同步），action 档保持居中小窗。 */
export const MODAL_WIDTH = {
  /** 三栏工具型（解析预览） */
  full: 'min(1560px, 96vw)',
  /** 工作台级（需求单/方案/成本表/附件归档/分享） */
  sheet: 'min(1200px, 96vw)',
  /** 只读明细（配置明细） */
  viewer: 'min(760px, 92vw)',
  /** 小操作表单（转交/发送/重命名/选人/状态变更/上传） */
  action: 'min(560px, 92vw)',
} as const

export type ModalWidthTier = keyof typeof MODAL_WIDTH

/** 工作台级弹窗 body 的高度上限（配合 overflowY:auto 内滚） */
export const MODAL_BODY_MAX_HEIGHT = 'calc(100vh - 120px)'

/** 同上，适用于 body 之外还有 footer 按钮条的弹窗（footer 约 53px） */
export const MODAL_BODY_MAX_HEIGHT_WITH_FOOTER = 'calc(100vh - 180px)'
