/** BOM 模板品类中英别名 —— 唯一数据源 system_config.bom_category_aliases（可配置、有前端入口）。
 * 前端不再写死 CATEGORY_CN_EN；未加载/失败时返回空对象，bomRuleEngine 退化为品类精确/子串匹配。 */
import { systemConfigApi } from '@/api/systemConfig'

export type BomCategoryAliases = Record<string, string[]>

let _aliases: BomCategoryAliases = {}
let _promise: Promise<BomCategoryAliases> | null = null

/** 幂等加载（模块级缓存）；失败返回 {}，不抛错。 */
export async function loadBomCategoryAliases(): Promise<BomCategoryAliases> {
  if (_promise) return _promise
  _promise = systemConfigApi.getValue<BomCategoryAliases>('bom_category_aliases')
    .then(v => { _aliases = (v && typeof v === 'object') ? (v as BomCategoryAliases) : {}; return _aliases })
    .catch(() => { _aliases = {}; return _aliases })
  return _promise
}

/** 同步读取已加载的别名表；未加载/失败时为空对象。 */
export function getBomCategoryAliases(): BomCategoryAliases {
  return _aliases
}

/** 置缓存失效（配置被编辑后调用，下次 load 重新拉取）。 */
export function invalidateBomCategoryAliases(): void {
  _aliases = {}
  _promise = null
}
