# 配置向导页 (ConfigWizardPage)

## 功能概述

四步配置流程，引导用户完成服务器配置。

### 核心功能
1. **面包屑导航** — 返回机型目录
2. **配置向导** — ConfigWizard 组件：
   - Step 1: 基础信息（型号、数量、描述）
   - Step 2: 部件配置（CPU/内存/硬盘/GPU/网卡/电源等）
   - Step 3: 推导与校验（功耗/PSU/GPU线缆/背板自动推导）
   - Step 4: 确认与保存

### 数据流
- 加载机型信息（含关联的基准配置）
- 用户逐步配置各部件
- 推导引擎自动计算（带手填兜底）
- 保存为报价单配置

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/config/:modelId` | `views/ConfigWizardPage.vue` |

## API 端点

### 机型与基准配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{modelId}` | `catalogApi.getModel` | 获取机型详情（含基准配置） |
| GET | `/api/base-configs/{id}` | `baseConfigApi.get` | 获取基准配置详情 |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（选择部件） |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |
| GET | `/api/kp/categories` | `kpPartsApi.categories` | KP 分类 |
| GET | `/api/kp/parts` | `kpPartsApi.listByCategory` | 按分类获取 KP 配件 |

### 推导引擎
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/derive` | `deriveApi.derive` | 传当前配置状态，返回推导结果 + 约束校验 |

### 配置方案
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/config-schemes` | `configSchemeApi.create` | 保存配置方案 |

### 规格书模板
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/spec-templates/default` | `specTemplateApi.getDefault` | 获取默认规格书模板 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型信息 |
| `l6` | `base_configs` | 基准配置（预填部件） |
| `l6` | `base_config_parts` | 基准配置料件 |
| `l6` | `parts_master` | 配件主数据（查价） |
| `kp` | `kp_parts` | KP 配件 |
| `kp` | `kp_categories` | KP 分类 |
| `l6` | `config_schemes` | 配置方案 |
| `rules` | `matching_rules` | 匹配规则 |
| `rules` | `system_config` | 系统参数 |
| `rules` | `spec_templates` | 规格书模板 |

## 关键组件

- `ConfigWizard.vue` — 四步配置向导主组件
  - 机箱配置（L6 via stepper modal）
  - KP 配件按分类（CPU/Memory/HDD-SSD/GPU/NIC + 用户自定义分类）
  - 计算总计（L6 + KP = 总价）
  - 保存配置方案并生成规格书
