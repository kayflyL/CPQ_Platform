/**
 * 统一字段服务 API
 * 替代各页面硬编码的字段定义
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

/**
 * 按业务域获取字段
 * @param scope opportunity / config / pricing / export / parse / system
 */
export function getFieldsByScope(scope: string) {
  return api.get(`/fields/scope/${scope}`).then(res => res.data.data)
}

/**
 * 按页面获取字段（基于 used_in_pages 字段）
 * @param page opportunity_detail / export_template / workbench / parse_template / ...
 */
export function getFieldsByPage(page: string) {
  return api.get(`/fields/page/${page}`).then(res => res.data.data)
}

/**
 * 获取动态数据源子字段
 * @param sourceKey l6_details / kp_details / warranty_details / config_summary
 * 如果不传 sourceKey，返回所有数据源的所有字段（按数据源分组）
 */
export function getDynamicSources(sourceKey?: string) {
  const params = sourceKey ? { source_key: sourceKey } : {}
  return api.get('/fields/dynamic-sources', { params }).then(res => res.data.data)
}

/**
 * 获取部件类型关键词映射
 * 用于替代 template_filler.py 和 pricing_engine.py 的硬编码
 */
export function getTypeKeywords() {
  return api.get('/fields/type-keywords').then(res => res.data.data)
}

/**
 * 获取组件映射
 * 用于替代 template_filler.py 的硬编码
 */
export function getComponentMapping() {
  return api.get('/fields/component-mapping').then(res => res.data.data)
}
