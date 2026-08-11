/** 服务器可视化公共模块：浏览态 Viewer + 编辑态 Editor（PixiJS 渲染底座，数据驱动）。 */
export { default as ServerAnatomyViewer } from './ServerAnatomyViewer.vue'
export { default as ServerAnatomyEditor } from './ServerAnatomyEditor.vue'
export type { DrawingRegion, DrawingView, DrawingViewBox, DrawingViewType } from '@/api/serverDrawing'