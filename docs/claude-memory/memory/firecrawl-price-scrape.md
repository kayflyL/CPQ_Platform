---
name: firecrawl-price-scrape
description: Firecrawl 爬电商价格:京东JD全线被挡(所有页面类型 markdown 空、搜索连 item.jd.com URL 都不返回);淘宝/天猫可爬(实测拿到¥1980+店铺名);国产niche件走国产化平台/淘宝
metadata: 
  node_type: memory
  type: reference
  originSessionId: 0aa265ad-5de4-4f99-a706-563646f639bb
  modified: 2026-08-06T09:13:15.411Z
---

用 Firecrawl 爬**电商实时售价**的可行性(2026-08-06 实测):

## 京东 JD.com — 爬不到(全线被挡)
测了 3 类 JD 页面,Firecrawl 全部返回 **markdown 长度=0**(空 JS 壳):
- `/jiage/`(价格聚合页)、`/chanpin/`(产品页)、`/hprm/`、`/phb/`(排行榜)均空。
- `/search` 搜 JD 商品**永远不返回真实 `item.jd.com/<id>.html` 链接**,只给 SEO 聚合页(`jd.com/jiage/...` 等)。
- 原因:JD 反爬(空壳+价格走异步 JS API,需 referer/cookie)。**不是 Firecrawl 的问题,是 JD 主动挡爬虫。**
- 想拿 JD 价只能走:京东联盟/淘宝客**官方 API**(要 key)、或 headful 浏览器方案,Firecrawl 这条路死。

## 淘宝/天猫 — 能爬(实测通)
- 实测 `taobao.com/list/item/...` → 干净拿到 **兆芯 KX-U6780A ¥1980.00 + 商品名 + 店铺(云川国产化平台)**。
- 价格 schema(`{price_yuan,price_text,product_name,shop}`)对淘宝页生效。

## 第三方比价站 — 能爬
- 慢慢买、什么值得买、知乎"京东价格汇总"类文章会**转抄 JD 价**且可被 Firecrawl 抓(实测知乎 SSD 文章含"JD M.2 SSD 2TB 1500+"等)。

## 怎么用(CPQ 场景)
- **niche 国产件**(兆芯 CPU/国产 GPU 等):京东基本无货,主流零售在**国产化平台/淘宝**——直接爬淘宝。
- **大宗标品**(内存/SSD/风扇/线缆):无"唯一价",品牌/卖家不同价差大,只能抓**代表品**给区间,不是单值。
- 真要给料号库填实时价:**别依赖实时爬 JD**;按周期人工/市场参考价(现有 KP 库做法)更稳,或接官方比价 API。
- 接入/key/坑见 [[firecrawl-spec-extract-poc]](curl --ssl-no-revoke、v2 formats、429 限流串行+sleep)。
