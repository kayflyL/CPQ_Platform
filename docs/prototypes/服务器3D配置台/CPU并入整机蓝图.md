# CPU 并入整机蓝图 · 第一轮：品牌参数化（2026-11-06）

> 定调出处：风扇墙并入整机同方法 + 会话讨论「同服务器 CPU 切换不复制资产」。
> 范围（第一轮/地基）：cpuFamily 参数化打通链路。第二轮（另行立项）：machine 行组合声明 schema + 管理页复制/绑定 UI。

## 1. 背景

- cpu.ts 工厂有 sp5(AMD)/kh(兆芯) 双形态，但种子只登记了 AMD 一行 → 部件页只出过 AMD（"最后一厘米没接"）。
- 整机 CPU 区是示意级（蓝色发光顶盖+鳍片塔）；ServerStage3D 挂载传 cfg=undefined → 全部机型渲染同一默认整机。
- 目标：同一份 machine.ts + 同一份 CPU 模块工厂，兆芯机型自动渲染兆芯 CPU，资产零复制。

## 2. 模块抽取契约（闸3 落地物）

```ts
// parts/cpu.ts 导出公共单颗模块(mm 域,按 family 定型)
export interface CpuModuleMats { sub, chip, iod, ihs, caps, gold: MeshPhysicalMaterial }
export function createCpuModule(mats: CpuModuleMats, spec?: { family?: 'sp5'|'kh' }): { g: THREE.Group }
// 含:基板+chips(sp5=12CCD+IOD / kh=单片)+IHS台阶沿+品牌刻字(CanvasTexture,noBloom)+电容排+pin1金三角
// 不含:底面 LGA 触点阵(整机装配态看不见;部件页 createCpuModel 自带)
// 刻字纹理按 brand 缓存;材质调用方注入(部件页一组/整机一组,禁每颗新建)
```

createCpuModel 改为消费该模块（保留 pads 底面阵与爆炸分层），family/brand 判定逻辑随模块下沉。

## 3. 整机侧

| 项 | 值 |
|---|---|
| `MachineConfig.cpuFamily` | `'sp5' \| 'kh'`，缺省 'sp5'（老数据无痛） |
| mm→整机单位 | 0.00825（同风扇系数；基板 75mm→0.62、IHS 顶盖 55mm→0.45） |
| 插座位 | x=±0.85（现位不动），y=主板面 0.325，z=D×0.09 |
| 与内存间距 | 中组 DIMM 最右 ~0.50 < 模块半宽 0.31+0.85=0.54 起 —— 不重叠（已核算） |
| 发光 | cpuCap 蓝顶盖退役 → **插座发光定位框**（主板四边 cyan 描边，tagGlow('cpu') 原路径；IHS 镀镍不进 bloom，刻字 noBloom 豁免照旧） |
| 数量 | cfg.cpus 颗（现 2），超出的隐藏走 cpuUnits（模块组替换鳍片塔组） |
| PART_INFO.cpu | 按 family 出文案：sp5='AMD 9004/9005 · DDR5 6400'，kh='兆芯平台 · DDR5'（labels 覆盖机制照旧在顶层） |
| applyTheme | 扩展 CPU 模块换色（基板色按 family 选 sub/subKh，机内同品牌同色一套材质） |

## 4. 链路（品牌从哪来）

- `stage.ts`：createServerStage opts 加 `cpuFamily`，并入 cfg 后传 createMachine。
- `ServerStage3D.vue`：新 prop `cpuFamily?: 'sp5'|'kh'`，变化时重建舞台（同 partSpec 既有 watch 模式）。
- `ModelDetailPage.vue`：机型 `series` → family 映射（名称含「兆芯」→ 'kh'，否则缺省），传 :cpu-family。ConfigWizard/管理页不传=缺省 sp5。
- **种子补行**（startup ensure 幂等段）：INSERT「兆芯 CPU 部件模型」part_type='cpu'，layout_config='{"family":"kh"}' WHERE NOT EXISTS —— 部件库两行并存，前端零改动。

## 5. 不做清单（第二轮）

- machine 行组合声明 schema（layout_config.machine）、管理页复制机型/绑定编辑 UI、挂载链路读行配置
- GPU/PSU/PCIe/机箱绑定面（部件化未到位不开假功能）
- Intel family 分支（将来加一个分支即可，本轮不预埋）

## 6. 硬坑对照

- 后台面板截图：renderOnce 步进 + canvas→img 覆盖层；页挂 resize 防 innerWidth=0。
- 按 key 数网格验收：整机 cpu 区应得 ihs 台阶沿/顶盖/凸台=每颗 3 件×2、caps instanced×2、pin1×2；部件页基准不变。
- 父级有偏移子件用局部坐标（cpuBank 在 y 偏移组内，模块 position 用 cpuBank 局部域）。
