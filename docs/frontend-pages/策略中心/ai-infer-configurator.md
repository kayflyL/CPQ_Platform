# AI 推理配置器（选型配置页·第一模式）

> 最后更新：2026-09-28
> 落点变更：v1 曾嵌解决方案详情页(ai-infer)，用户裁定**破坏文档型页面结构**——已迁出。现常驻
> **选型配置页**([SelectionWorkspace](../../../frontend/src/views/admin/selection/SelectionWorkspace.vue))顶栏模式开关的**第一个模式「推理配置」**，与 兼容规则 / BOM案例库 / 模型与参数库 并列（tab 图标用 @ant-design/icons-vue：Thunderbolt/Tool/FileText/Database）。解决方案详情页恢复纯文档形态(hero+正文+静态平台卡)。

组件：[AiInferConfigurator](../../../frontend/src/components/solution/AiInferConfigurator.vue)（自含，所有数字来自 `/api/gpu-sizing`，前端零硬编码）。

## 页面结构（Glass Console 皮肤 · 跟随主题 · 剖面纯需求侧 · 三栏固定框架）

**2026-09-28 用户定调「页面 AI 味很重」→ 方案 A：结构与交互全保留，皮肤回归站内 Glass Console token**（v6「深渊冰芯」igloo.inc 皮肤退役）。撤掉的「AI 味」四来源：①特效装饰层（feTurbulence 胶片颗粒/顶部辉光/卡砖 HUD 角标全删）；②排版表演（巨型 200 细字重刊头数字 → 30px/600 工具尺度，全场 mono → 站内字体）；③文案腔（STEP 01/英文灰注/双语标签/`//` 注释脚全中文化）；④风格孤岛（脱离站内视觉语言）。实现要点：容器=单玻璃层（`--cpq-glass-card-bg` 渐变 + blur 14px + `--cpq-glass-border`），内部平面不嵌套；组件内用**局部 CSS 变量重映射**最小改样——scoped `.aic` 里把旧变量指到 cpq token（`--ice: var(--cpq-accent-primary)`、`--mono: var(--cpq-font-family)` 等），几十条规则零改动自动换肤；**暗色零专属代码**——token 主题感知，整段 `:root[data-theme='dark'] .aic` 覆盖块已删；antd 下拉浮层交全局玻璃化接管（组件级 `aic-sel-dd` popupClassName 与 global 样式块已删）。权威原型 `docs/prototypes/选型配置-推理配置器-原型.html`（右上「◐ 主题」可切换预览）。

**三栏固定框架（09-28 用户批准「三栏 + 整页框架固定、窗口内部滑动」；同日再调「中栏占比加大、右栏收窄、整体字号微降」）**：`.aic` = `height: calc(100vh - var(--cpq-sticky-top) - 122px)` 的 flex 列（60px 顶栏 token + 122 = 实测让位 142px + 底部 40px 呼吸，页面级滚动归零）；`.aic-cols` 三轨 grid `minmax(292px,324px) + minmax(340px,400px) + minmax(0,1fr)`（1440 下 324|400|610），grid-template-areas `"sel prof cards"`，行轨必须 `minmax(0,1fr)`（auto 行不占满容器高，内滚会失效）。左=选择、中=剖面**常驻不滚**（overflow-y:auto 仅作矮屏兜底），右=卡砖：`.col-r` flex 列，「哪些卡合适」mark+筛选 chips 钉在顶部，`.rbody{flex:1;overflow-y:auto}` 独立内滚，foot 随内容滚。sticky 全删（固定框架下无意义）。响应式（09-28 二次定调：**浏览器放大区间三栏必须保持，不出两栏中间档**）：≤1280 收窄两根固定栏（`292px 360px minmax(0,1fr)`）给卡区腾位；≤1080 才退单栏文档流（height:auto + overflow 全 visible + 宿主滚动恢复）。曾试「≤1400 并两栏」方案——用户环境=系统125%缩放，浏览器 110% 即落入该档，三栏垮掉被否决；现在放大到 125% 叠加（≈1222 宽）仍是三栏固定框架。tiles `minmax(200px,1fr)`（1222 宽下仍 2 列）。字号整体微降（h1 18 / mark 13 / giga 26 / 卡砖标题 12.5 / 统计数 14.5 / 明细行 11.5），tiles `repeat(auto-fill,minmax(200px,1fr))`、量筒 204px（矮屏 156）；hero 默认竖排（中栏 ~400px）。原型同步（`.ctx` max-width 1200→1440、底 padding 收窄 20px；固定高 `calc(100vh - 115px)`）。

1. **左栏 = 选择区（六个步骤，零下拉，常驻）**：品牌商 seg · 模型搜索式 combobox · 量化 · 框架 · 并发分段 · 场景 chips——全部 hairline 幽灵态，激活=主色描边+淡蓝底（`--cpq-bg-selected` 口径）。
2. **中栏 显存剖面 = 纯需求侧（09-28 用户定调：剖面不推荐具体 GPU，卡型只出现在右栏）**：需求总量数字（30px/600，tabular-nums）+ ruled 明细（权重/视觉/KV@ctx×并发/每token KV/框架预留）+ **冰芯量筒**（每芯固定 100G 通用刻度，权重先填、KV 后填接续，不绑定任何卡型；无单卡上限线/系统预留带）。
3. **右栏「哪些卡合适」卡砖网格（主交互，卡型推荐唯一出处，标题+筛选钉顶、结果区独立内滚）**：全部有显存的卡各算推荐张数（余量≥30% 升档）/最低张数/余量/最大上下文/吞吐；首砖「推荐」蓝描边标签；**点砖展开 = 张数步进（evaluate 返回参数本地重算，零请求）+ 适配机型（直读 kp_parts.applicable，空则指路配件管理）**；rec>12 张折叠底部；品牌筛选（全部/NVIDIA/国产）；hover/open 描边加亮（`--cpq-glass-border-strong`）+ 浮起阴影。
4. 旧机型反推链已退役：前端只调 catalog + evaluate。

## 诚实降级（不猜）

- 无任何机型维护卡配置 → 结论卡退化为需求侧结论（总需显存 GB）+ 录入指路；
- 模型缺结构四参数 / params_b≤0 → 409 提示去模型库补齐；缺带宽 → 「估速不可用」。

## 计算与数据

- 内核：`backend/app/services/gpu_sizing.py` 纯函数（单测锚点=Excel v10 速查表，7/7）；并发乘进 KV、MLA 潜变量修正、推荐档=余量≥30%；
- **TP 门（09-28 Excel 对账补齐，Excel 使用指南原文口径）**：不支持张量并行的框架（ollama/llama.cpp）多卡不并显存——`eff=单卡可用`，所需卡数返回 `null`（前端显示 N/A(不并卡)），B 区出琥珀提示条；evaluate 响应新增 `tp` 顶层字段，前端 local() 本地重算同口径；
- 吞吐口径统一：TP 框架按推荐张数聚合带宽（rec×单卡带宽÷每 step 读取），非 TP 按单卡；
- API：`/api/gpu-sizing/catalog | solve | evaluate`（evaluate=批量卡试算，返回 need/params/rows；need 缺失曾致整页渲染崩溃，已修；09-28 再补 params.overhead——前端类型早已声明，后端漏传，明细行「框架预留」一度裸显 `vLLM GB/卡`）；
- 数据链：三软库(rules) → 基准配置 gpu_default → KP GPU spec(显存/带宽)。

## 与 Excel v10 对账结论（2026-09-28）

- **数值 100% 一致**：模型库 60/60、框架库 5/5、场景表 7/7 与 Excel 逐字段核对通过（置信度标签高✓/中/低⚠️→high/mid/low 为导入时刻意规范化）；GQA 模型（58/60，含 Excel 口径的 DeepSeek-V3/R1）权重/KV 公式在 全量化档×全框架×全卡容量 下逐格复算零差异；
- **有意偏差（保留）**：①并发乘进 KV（Excel 无并发变量）②MLA（DeepSeek-V2/Coder-V2）按压缩潜变量 ~576 维算，Excel 走 MHA 分支偏大 ~18×③MoE 按总参数（Excel 自己也声明偏保守）④每卡扣系统预留+框架开销 vs Excel 多卡 TP 一次性扣（8×16G vLLM 差 17.5G，我方更保守）⑤最少卡数按场景 ctx 而非 Excel 的 4K 最小占用；
- **对账修出的缺陷（已修）**：后端 tensor_parallel 字段进了库却没进计算（非 TP 框架也按 n 卡池化，已加 TP 门）；原型 FW_OH 三处硬编码错值（TensorRT 0.4→0.8、ollama 1.7→0.3、llama.cpp 0.6→0.2）与 4bit 系数未分框架（w4 内含 AWQ 1.05 基准，现按框架 1.05/1.125 换算）；gpu_sizing_api.py 三段重复定义已清理（_framework/admin CRUD/cards 各 ×2）；
- **未复刻（后置项）**：Excel ③区的场景适配判断 ✅ 一句话（ctx≥推荐+速度达标，现为卡砖明细自判）、💡改进建议/⚠️注意事项文案块、档位速查表静态全卡一览（evaluate 即其动态版）。

管理面见 [模型与参数库](llm-catalog.md)；卡配置录入见基准编辑器⑨扩展（候选清单 `docs/GPU_DEFAULT_CANDIDATES.md`）。
