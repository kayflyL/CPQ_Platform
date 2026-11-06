/**
 * 部件类型注册表 — parts/ 工厂可用类型的单一来源。
 * 三处消费:①模型编辑页分区绑定下拉(按槽位类型过滤部件行) ②部件行「部件类型」编辑
 * ③管理页部件库标签。新部件类型(如 gpu/psu)部件化后:本表加一行 + stage.ts 分支即可,
 * 模型编辑页与管理页的 UI 零改动。
 */
/** 部件类型→显示名(选项来源=有工厂能渲染的类型,防止选了画布画不出) */
export const PART_TYPE_LABELS: Record<string, string> = {
  cpu: 'CPU',
  fan: '风扇墙',
}

/** 整机分区键→部件槽位类型:该分区有对应类型的部件行时,编辑页分区组内出现「绑定部件」下拉 */
export const REGION_SLOT_TYPES: Record<string, string> = {
  cpu: 'cpu',
  fans: 'fan',
}
