---
name: quote-export-reveal
description: 报价预览导出价格揭示机制：sens_group三档掩蔽+scope区域聚合合并+模板绑定非硬编码+单台价口径
metadata: 
  node_type: memory
  type: project
  originSessionId: 733e35ad-0744-4844-ba46-1ab84978e21e
  modified: 2026-10-10T09:04:36.481Z
---

报价工作台预览/导出的价格揭示机制（2026-09-15 落地）。

**结构**：字段目录 `rules.dynamic_source_fields` 驱动，不硬编码——
- `sens_group`：sell=明细销售价(无权限要求) / cost=成本 / margin=利润率；掩蔽分两档：**sell→blank（明细清空、列保留，Total Price 总计行恒显）**，cost/margin→hide（**整列物理删除**，2026-10-10 定调：客户版文件里这列压根不存在，不是 hd=1 隐藏——隐藏列可被解除、表头残留；空数据也摘列，此前空数据时掩蔽被整体跳过致表头漏出）。删除在 `template_filler._delete_column` 单点实现：cellData 左移收敛+mergeData 收敛（横跨被删列的合并区右端缩一格）+columnData/columnCount 同步
- `scope`：row=逐行(默认) / **region=区域聚合**——整机单台价挂 L6 首行，填充器按实际行数运行时生成纵向 mergeData（模板不预画合并）
- `scope`：row=逐行(默认) / **region=区域聚合**——整机单台价挂 L6 首行，填充器按实际行数运行时生成纵向 mergeData（模板不预画合并）
- 权限 `field.quote.export_internal` 控制 cost/margin（服务端剥除，前端开关只是交互层）；下载对内版归档 internal_quote + 文件名 `_对内版`

**用户定调**：
- 配置页显示的本来就是**单台价**——Total Price 行绑 `cfg_unit_price` 勿改成 total_price；L6 合并格也是单台价
- 价格字段必须在导出模板（设置→导出模板）里绑定，不许硬编码

**模板1绑定布局（09-15 深夜定稿·双列常显五列式；09-22 晚质保费行已撤）**：配置页明细表 E..I = 销售单价(final_price)/销售总价(sell_total)/成本单价(base_price)/成本总价(cost_total)/Margin%(profit_margin)；L6 合并格只绑 F=l6_sell_price、H=l6_base_price、I=l6_margin_rate（E/G 留空——整机无单价/总价之分）；Total Price 值 E13→**F13**（落销售总价列），头部信息 Sales/FAE/DATE 值格+绑定留在 **F1/F2/F3**（曾随插列机械推到 G1-G3，客户版 cost 整列隐藏时头信息陪葬+与 E 标签隔空列——fix2 已迁回；**头信息等非价格静态绑定必须落永不隐藏的列**，sell 列会清明细、cost/margin 列会整列藏）。勾选分组→sell 勾=E/F 明细清空列保留、cost 勾=G/H 整列隐藏、margin 勾=I 隐藏，Total Price 恒显；封面本就有「含税单价+含税总价」双列零改动。**综合利润率=成本口径 (售-成)/成，质保费算纯利润不进成本**——2026-09-22 定调全系统以右面板 calcConfigTotals(quote.ts) 为准（预览 preview_data_loader 原来把费率维保费进 cost_total 致封面 11.7 vs 面板 14.58 打架，已改对齐；费率法质保费=维保服务收入零成本）。**09-22 晚用户定调「质保只显示一个总价」：Warranty 区价格格 F11/F12（cfg_warranty_l6/kp 静态绑定）整体摘除**——质保费只折进 Total Price 不单显（static 绑定不吃 sens_group 掩蔽，客户版会漏显质保价而明细价全空）；描述行（warranty_desc_l6/kp 绑 B 列）保留；顺带清了 KP 描述重复格 D12+c3。preview_data_loader 的 config_summary.warranty_l6/warranty_kp 字段仍在（数据契约），只是无格可绑。手术脚本 patch_dual_price_tpl1.py + 修复脚本 patch_dual_price_fix1.py（E13 标记格漏迁→F13、Warranty 横幅漏拉通）+ 离线验证 verify_dual_price_tpl1.py（13 检查项，live/excel/USD 单三单过），备份表 univer_templates_bak_dual_20260915；09-22 摘除前备份 `backend/_backups/univer_tpl1_backup_20260922_warranty_line.json`。**USD 件成本列口径**：DB 里 base 是 USD 裸值、final 已是 RMB 含税——显示层换算（×汇率×(1+税率)）只能做在 `_load_item_details` 的 kp_details 显示行副本上；**勿改 items 本身**（items 同时喂 `_calc_cost_sum`，它自己按 currency 换算，改了=双重换算→成本爆炸→封面利润率 -62 的大回归，09-15 踩过）。插列手术注意：列插入只移 col>=at 的格子，col4 标记格不动会漏迁，绑定格与标记格要分开迁。

**⚠️ 编辑器覆盖坑**：模板编辑器旧页面保存会把脚本改过的 bindings 覆盖回旧状态（用户实测踩过：聚合绑定被还原→合并不生成+价格消失，看似"合并机制坏了"实为绑定被覆盖）。脚本改绑定后必须让用户刷新编辑器再保存。运行时合并生成前会剔除区域列上模板遗留手工合并（自愈）。

**Why**: 客户版不能泄露成本/利润率（整列必须物理删除，隐藏≠删除），但总售价是报价本身必须恒显；L6 价格在整机级非逐行级；Quotation 列必须堆得上 Total Price。
**How to apply**: 碰导出模板/预览揭示/价格列绑定前先看；加新敏感价格字段走 sens_group 打标，勿在导出链路写死列；改模板 bindings 优先脚本+提醒刷新编辑器；验证跑 `backend/scripts/verify_dual_price_tpl1.py`（含空数据回归项；`scripts/_localdb.py` 垫片不进仓库，内联注入 `get_settings().DATABASE_URL` 跑）。
