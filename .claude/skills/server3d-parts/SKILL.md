---
name: server3d-parts
description: 服务器3D部件库建模的强制工作流（蓝图→分pass→接入→终审→固化）。新增CPU/GPU/盘位/PSU等部件模型、改server3d部件工厂、或碰服务器3D配置台视觉时必须先读。
---

# server3d 部件建模 · 五闸工作流

目标：部件级 3D 模型（能看/能爆炸/能点选/带知识卡语义层），将来按装配蓝图组合成整机并支撑培训程序。参考实现：`frontend/src/server3d/parts/cpu.ts`；流程权威文档：`docs/prototypes/服务器3D配置台/CPU部件建模蓝图.md`。

## 配套 skill（装在全局 ~/.claude/skills/，按阶段主动加载，别让它们躺平）

| 阶段 | 加载什么 | 用途 |
|---|---|---|
| 闸2 建造前 | Skill(threejs-geometry / threejs-materials / threejs-lighting / threejs-postprocessing) | r186 API 新鲜度（Clock→Timer、env/PMREM、bloom 参数），开写前扫一遍防过期 API；主循环的 Clock deprecated 警告就是这类问题的活例 |
| 闸2 复杂部件（有机形态/高还原度参考图） | Skill(img2threejs) | 跑它的 forge 分 pass 管线（spec→pass门→divine_eye评分→有界纠错）；CPU 这类盒体几何手动执行 pass 纪律即可，别为仪式跑重管线 |
| 闸5 后培训程序（拆解导览/镜头脚本/实时面板） | Skill(teardown) | 对标它的 live 页架构（kin/engine/stage/console/film 分层+自动导览），做「服务器拆装教学」时整页复刻其形态 |

## 五道闸（每道有产物，错误只回退一步）

1. **闸1 蓝图**：不动 3D 代码。出蓝图文档（md 权威 + 可视化 HTML 示意台，示意台一律 three.js 同 P1 品质，禁 CSS 手搓）——结构分层表、爆炸行为、尺寸依据（引真实规格，官方没公开的标「待核对」禁止发明）、工厂接口契约、管理页扩展方案。**用户批准后才动代码**。参考素材（产品渲染图/截图）拷入 `refs/` 并在文档中逐视角说明结构结论。
   **照片建模专用：量图管线（有正交多视图时必做，机箱 2026-11-04 实证：三视图交叉量出深度 835mm，推翻目测的 650）**：① PIL 脚本对每张正交视图量主体 bbox（白底阈值）② 用已知锚点（19"=482.6 含耳/448 裸宽/4U=178）解出每视图 px/mm ③ 同一尺寸两视图交叉验证差<2% 才采信 ④ 特征测量：按颜色定位（如盘位蓝把手条）换算 mm、按行列暗度剖面找分区边界 ⑤ 取色做材质调色板。**闸2 门禁升级**：每轮 pass 用正交相机按同标定渲染同视角与参考 PNG 叠加，轮廓 IoU≥0.9 为块头门禁。
   **照片方向/标定工具**：`docs/prototypes/服务器3D配置台/照片贴图工具.html`（v2 交互范式）——六个面各自的上传按钮，照片天生属于该面（锚点局部 u/v 坐标），拖拽用射线求交面平面+钳制在面内（物理上拖不出去），禁止自由漂浮；位置有数值框（mm）+方向键 1mm 微调+磁吸（面缘/中心 5mm 内吸附，黄色参考线）；旋转只有 90° 档+镜像，方向由人定。贴合即自动 px/mm 标定（盒体单位=mm），导出 photo-calib.json 是蓝图尺寸依据。调试口 `window.__fit`。经验：交互约束要"软件做数学，人只做语义决定"（fSpy 工作模式的迁移）——凡带拖拽的建模辅助工具一律面锚点约束+数值框+磁吸，不做自由 TransformControls。
2. **闸2 分pass**：单部件独立 HTML 原型（`docs/prototypes/服务器3D配置台/部件-P{n}*.html`，jsdelivr three importmap 惯例）。P1 块头比例 → P2 结构布点 → P3 细节触点 → P4 材质灯光双主题。**每 pass 截图给用户确认才进下一 pass**。P1/P2 错误成本是分钟级，这就是分闸的意义。AI 永远禁止一口气生成整机。
3. **闸3 接入**：原型翻译成 `server3d/parts/<part>.ts` 工厂 + `server_3d_models.kind/part_type` 扩展 + 管理页分组。新部件种子行走迁移 SQL + startup ensure（幂等），部件不做网页新建（「模型由代码/种子产出」定调）。
   **新部件类型接入触点清单（每处都是漏点，fan 接入时曾漏 EditPage 白名单导致部件页建了整机）**：
   - `server3d/parts/<part>.ts`（工厂，照 cpu.ts/fan.ts 范本）
   - `stage.ts`：opts.partType 联合类型 + import + createServerStage 分支
   - `ServerStage3D.vue`：partType prop 类型
   - `Server3dModelEditPage.vue`：**load() 里 partType 白名单（fan 接入曾漏此处）** + PART_LABEL
   - `Server3dModelManager.vue`：PART_LABEL
   - 迁移 SQL + startup ensure：种子行
   - 验证：部件页 `__s3dStage.machine.root.userData.part` 必须等于新类型（等于空=白名单漏了）；**并按 key 数网格**（`root.traverse` 数 userData.key）——fan 曾翻车：扇框组 `g` 建完忘了 `gFans.add(g)`，转子/护罩走别的组所以页面"看着差不多"，唯独外壳 12 件全没进场景图。遍历计数 fanframe=24/screw=48 一眼就能抓住这种"某组整体缺席"。
4. **闸4 终审**：`cd frontend && npm run build`（style-gate+vue-tsc+vite）→ dev 起来实机点验（管理页分组/部件页爆炸/整机页回归）→ 用户终审。
5. **闸5 固化**：新踩的坑回写本 skill 与记忆，蓝图定调回写文档。

## 部件工厂契约（cpu.ts 为范本，新部件照抄结构）

- 返回句柄与 machine.ts 同形：`{ root, PART_INFO, KEY_ALIAS, setCounts, setExploded, updateTick, setHover, applyTheme?, setGlassBase?, explodeRatio }`——stage.ts 的 `StageModel` 接口按此驱动，部件无需改舞台。
- 根 Group `userData.part = '<part>'`；每子件 `userData = { key, name, spec, desc }`（悬浮标注/培训知识卡共用此层）。
- 尺寸：内部按 mm 建模，`root.scale.setScalar(0.02)`（machine.ts ≈50mm/unit），auto-fit 自动取景不需要改相机。
- 爆炸：轴向分层（每层一个 Group，updateTick 里 exp 缓动趋近 target），禁止径向散射、禁止手工关键帧。
- 悬停：材质登记 byKey，emissiveIntensity 缓动提亮（#37c8ff）。
- 主题：实现 `applyTheme(t, name)` 钩子（t=STAGE_THEMES 行），色表按 dark/light 两档；哑光件 envMapIntensity 压低（0.15-0.3），只有金属件给高值。
- 刻字/文案：**只出品牌字，不出现具体型号**（2026-11-03 用户定调）；CanvasTexture 程序生成，零贴图文件。

## 硬坑清单（每条都真实烧过时间）

0. **交付前必须亲眼看到渲染结果（2026-11-04 机箱事故主根因）**：窗口最小化时截图是冻结旧帧——靠 bbox 数字/读坐标"验收"过的画面不算验收。交付任何可视化前：用 renderOnce 步进 + canvas→2D→img 覆盖层法亲眼截到新帧；截不到（窗口隐藏/超时）就明说"未复核，请本地打开确认"，禁止当成已验收交付。**像素检查必须隔离目标物做显隐对比**（目标隐藏→渲染→像素差>0 才算目标物真实在画面上），全局亮度/颜色桶会量到盒体灯光等别的东西——贴图工具照片缩放 bug（几何 1×aspect 配 mm/px 缩放=0.03mm 小点，两轮像素检查都没发现）就是这么漏网的。CSS 手搓 3D 禁止再用于任何部件示意（精度=卡通级、变换链易错，机箱事故第二根因），示意台一律 three.js。
1. **父级有偏移时子件必须用局部坐标**：机箱事故——bezel/ rear 已有 position，子件再写世界坐标 = 双重偏移飞出箱外（bezel 悬空 320mm、螺丝条 z=-648）。写子件坐标前先问"父级在哪"；交付前用 `Box3.setFromObject(root)` 量包围盒，超出设计尺寸 = 有子件飞了。
2. **金属件顶视炸白（2026-11-05 已根治,勿再走参数妥协老路）**：metalness≈1 的件（镀镍 IHS）镜面反射环境光,GGX 高光瓣一过 bloom 阈值,全屏 bloom 直接把三分之一区域放大成纯白。老方案（roughness/envMapIntensity/阈值三参数悬停妥协,验收只量"中心单像素<200"）修不干净——单像素恰好落在大高光瓣的暗缝里就算"过验"。**根治=stage.ts 选择性 bloom 双 composer**：辉光件（整机霓虹=所有 MeshBasicMaterial 面+舞台光环/尘埃）打 BLOOM_LAYER,其余件在 bloom-only 通道涂黑,金属再亮也进不了 bloom;阈值不再悬停妥协。cpu 品牌刻字带 `noBloom` 豁免（白色 Basic 平面不是霓虹）。新件为霓虹时只要用 MeshBasicMaterial 就自动上 bloom 层,非霓虹 Basic 平面记得标 noBloom。**验收标准=区域统计**（renderOnce + drawImage + getImageData）：模型区均值 <150 且白像素（L>240）占比=0,禁用单像素/全局亮度指标。
3. **金属没有 env 会渲染近黑**：stage 必须有 `scene.environment`（PMREM+RoomEnvironment），强度走 STAGE_THEMES.env。
4. **暗色三层拉开**：背景 #0a1526 / 地台 / 机体 亮度必须递增可辨，否则糊成一团（11-01 大亮板教训）。
5. **后台预览面板 rAF 节流**：Browser pane 在后台时动画帧≈0.5fps 且 dt 被钳 0.05，补间看起来冻住——**代码没坏**。验证动画要么用户本地开，要么用 `stage.renderOnce(dt)` 手动步进后把 canvas drawImage 到 2D canvas 转成 `<img>` 覆盖层再截图（WebGL canvas 本体在后台合成不更新，DOM img 会更新）。**面板后台初始化时 innerWidth=0**：WebGL canvas 0×0，drawImage 直接抛 InvalidStateError——独立原型页必须挂 resize 监听（高宽钳 ≥1），?snap 截图前重试等 canvas 有宽度；`?v=front|top` 类初始视角参数让节流环境下不用等飞入动画。
6. **测量要在同一 eval 原子做**：HMR/热改参数会跨 eval 残留脏状态，扫参前先 reload、扫参后恢复原值，否则数据互相矛盾。
7. **8000 端口后端可能是提权进程**：netstat 看得见 kill 不掉——别硬杀。幂等迁移直接对库执行，新后端代码等它自然重启时 startup 自愈生效。
8. **E2E 登录**：AUTH 开启时签发 token 用 opportunities.feed_users 里 **is_active=true** 的 admin（曾拿过 is_active=false 的行，/me 永远 401），键 cpq_auth_token。
9. **实体验证顺序**：`npm run build`（style-gate 会拦）→ 迁移落库 → 浏览器 `window.__s3dStage`（含 camera/controls/renderOnce 调试口）读状态，别靠截图猜。
10. **参考数据拿不到 = 停机条件，不是降级条件（2026-11-04 机箱事故）**：ZTE 站点 GLB/JSON 被 WAF 按扩展名封死（css/js/png 放行，json/glb 一律兜底页，cookie/UA/http2 都试过无效）——此时**明说"这个精度我做不出来"并给用户选项**（用户从浏览器 DevTools Network 保存 GLB 给我解析 / 接受降级 / 改用实件照片），禁止默默用截图猜一个低精度版本交付。

## 验收清单（闸4 打勾用）

- [ ] 管理页部件库分组出现，整机页回归无损坏
- [ ] 部件页：装配态/爆炸态/四视角/悬停标注文案正确
- [ ] 顶视中心区域均值 <150 且白像素占比=0（区域统计,禁单像素）；浅色主题切一遍模型可辨（模型与背景亮度差≥40,浅色照度=暗色同源,靠背景/地台/色板区分身份）
- [ ] userData 语义键全部有 PART_INFO 中文文案（培训知识卡的地基）
- [ ] build 通过；新迁移幂等重跑无副作用
