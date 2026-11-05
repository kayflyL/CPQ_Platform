/**
 * 交付地区共享数据（唯一来源）—— /lead 公开线索登记表 与 商机详情页基本信息 两个入口共用。
 *
 * 权威字段 = 商机 delivery_region（extra_fields，分价引擎按关键词分桶：海外/偏远/国内兜底）。
 * 取值带前缀编码，保证分桶关键词必命中：国内省份 = `国内-广东`（偏远省份含 西藏/新疆/青海/
 * 内蒙古/宁夏/甘肃，天然命中偏远桶）；海外 = `海外-日本`（命中「海外」）；
 * 不在列表中 = `海外-不在列表中`（按海外口径入桶）。存量自由文本（国内/海外/偏远…）照旧可读。
 *
 * 海外只列已开通硬件交付的国家（按大洲分组），其余一律「不在列表中」；
 * 新增国家只改 OVERSEAS_GROUPS，两个表单自动同步。
 */

/** 国内省级行政区（34，含港澳台） */
export const DOMESTIC_PROVINCES = [
  '北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江',
  '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南',
  '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州',
  '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆', '香港', '澳门', '台湾',
]

/** 海外已开通国家（按大洲分组） */
export const OVERSEAS_GROUPS: { continent: string; countries: string[] }[] = [
  { continent: '亚洲', countries: ['日本', '新加坡', '越南', '泰国', '马来西亚', '印度尼西亚', '印度', '巴基斯坦', '沙特阿拉伯', '土耳其'] },
  { continent: '欧洲', countries: ['英国', '意大利', '葡萄牙'] },
  { continent: '非洲', countries: ['埃及', '尼日利亚', '南非'] },
  { continent: '南美洲', countries: ['巴西', '秘鲁'] },
]

/** 不在列表中：该地区暂不支持硬件交付（软件与维保全球照常），按海外口径入桶 */
export const REGION_NOT_LISTED = '不在列表中'
export const NOT_LISTED_REGION_VALUE = `海外-${REGION_NOT_LISTED}`

/** a-select 分组 options（国内 + 各大洲 + 不在列表中），两个表单共用 */
export const DELIVERY_REGION_OPTIONS = [
  { label: '国内', options: DOMESTIC_PROVINCES.map((p) => ({ label: p, value: `国内-${p}` })) },
  ...OVERSEAS_GROUPS.map((g) => ({
    label: g.continent,
    options: g.countries.map((c) => ({ label: c, value: `海外-${c}` })),
  })),
  { label: '其他', options: [{ label: REGION_NOT_LISTED, value: NOT_LISTED_REGION_VALUE }] },
]
