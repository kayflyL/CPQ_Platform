"""Seed rules.solutions with the baseline 6 solutions (idempotent by key).

适配平台 platforms 绑定机型目录真实机型（l6.server_models）：model_id + /servers/models/:id 链接，
规格文案取自机型规格表，绝不写目录里不存在的型号（存量假数据由 scripts/fix_solution_platforms.py 修复）。
"""
from app.repository.solution_repo import SolutionRepository

SCENES = [
    {"key": "ai", "label": "AI·加速计算"},
    {"key": "virt", "label": "虚拟化·数据库"},
    {"key": "store", "label": "海量存储"},
    {"key": "sim", "label": "工业仿真"},
]

# 真实机型锚点（l6.server_models.id）：Orion 双子 = ES220 V3(2U通用)/ESA240 V3(4U AI)，Polaris 信创双子 = ZS220 V2(2U)/ZSA240 V2(4U AI)
_P_ES220 = {"name": "ES220 V3", "spec": "2U 双路 · AMD 9004/9005 · 24× DDR5 6400 · 最高 29 盘位", "model_id": 6, "link": "/servers/models/6"}
_P_ZS220 = {"name": "ZS220 V2", "spec": "2U 双路 · 兆芯 KH-50000 信创 · 24× DDR5 5200 · 最高 28 盘位", "model_id": 8, "link": "/servers/models/8"}
_P_ESA240 = {"name": "ESA240 V3", "spec": "4U 双路 · AMD 9004/9005 · 最高 8× 双宽 GPU 直连（10× 交换）", "model_id": 16, "link": "/servers/models/16"}
_P_ZSA240 = {"name": "ZSA240 V2", "spec": "4U 双路 · 兆芯 KH-50000 · 适配国产 GPU（天数智芯/沐曦）", "model_id": 17, "link": "/servers/models/17"}

_SEED = [
    {
        "key": "ai-infer", "scene_key": "ai", "scene": "AI·加速计算",
        "title": "AI 推理一体机", "sub": "把模型装进显存，再谈吞吐",
        "features": ["双路供电", "IPMI", "液冷预留"],
        "intro": "推理服务器的瓶颈是显存与带宽：模型越大、量化越浅，需要的显存和带宽越高。CPU 负责预处理与调度，GPU 承担推理。",
        "content_md": """## 这个负载需要什么

**显存优先**：显存 ≥ 模型体积；推理吞吐靠卡间带宽，型号/代数优先于核心数。

**大内存加载**：内存承载权重复制与 KV cache，ECC 保证 7×24 稳定。

**冗余与运维**：双电源 + UPS、IPMI 带外管理；高负载考虑液冷/专业机房。

## 配置思路

- 单卡 4090 适合 35B 以下 INT4 推理；两卡以上做并发吞吐扩展，卡间 NVLink/PCIe 带宽决定收益。
- 主板要确认 PCIe 插槽 x16/x8 与间距；功率预留 30%，冗余 N+N。

## 选型要点

- 显存是第一瓶颈，先定模型与量化档位，再反推显卡数量与代数。
- 内存按 `模型权重 + KV cache` 估算，ECC 是 7×24 的底线。
- 高负载优先机架式 + 专业机房，避开办公室风冷。""",
        "platforms": [_P_ESA240, _P_ZSA240, _P_ES220],
    },
    {
        "key": "ai-train", "scene_key": "ai", "scene": "AI·加速计算",
        "title": "大模型微调工作站", "sub": "显存翻倍，参数才能跑起来",
        "features": ["A100/RTX PRO", "512G 内存"],
        "intro": "微调比纯推理更吃显存：全参微调需要把梯度与优化器状态一起放进显存，LoRA 可显著降低门槛。",
        "content_md": """## 这个负载需要什么

**96G 显存起步**：70B 全量需多卡 A100/RTX PRO 6000；LoRA/QP 可下探。

**高速存储**：NVMe 缓存数据集与检查点；SSD 瓶颈会拖慢每轮 epoch。

**专业散热**：4 卡以上建议液冷或 AIDC 机房；避开办公室风冷。

## 配置思路

- 显存决定能训多大的模型；内存决定加载速度；CPU 负责数据预处理与分布式协调。
- 多卡并行以 PCIe/NVLink 带宽聚合，需 ≥2000W 冗余电源与双路散热。

## 选型要点

- 全参微调显存需求约为推理的数倍，优先大显存单卡或 NVLink 多卡。
- 检查点写盘频繁，NVMe 的持续写吞吐比随机读更关键。""",
        "platforms": [_P_ESA240, _P_ZSA240],
    },    {
        "key": "virt-hci", "scene_key": "virt", "scene": "虚拟化·数据库",
        "title": "虚拟化超融合", "sub": "核数与内存决定能装多少台虚拟机",
        "features": ["ECC 全通道", "RAID10"],
        "intro": "每一台 VM 都要占用一份 CPU 核与一份内存，内存通道插满比单条大容量更重要。",
        "content_md": """## 这个负载需要什么

**多核 + 全通道**：双路高核 CPU，内存按通道插满，容量决定 VM 并发数。

**双系统盘**：Hypervisor 镜像盘镜像化，避免单盘故障拖垮整台宿主。

**数据盘 RAID10**：企业级 SSD RAID10，读写与冗余兼得。

## 配置思路

- VM 数量 ≈ 核数 × 内存密度；内存通常是真正的上限，平台最大内存决定了能塞多少 VM。
- 热迁移需要共享存储 + 双 25GbE，至少三台宿主机才能做到主机故障不中断。

## 选型要点

- 优先把内存通道插满，而不是买超大单条；带宽比容量更能撑起并发。
- 数据盘用企业级 SSD + 硬件 RAID10，别用主板软 RAID。""",
        "platforms": [_P_ES220, _P_ZS220],
    },
    {
        "key": "db-ha", "scene_key": "virt", "scene": "虚拟化·数据库",
        "title": "数据库高可用", "sub": "延迟取决于内存命中率",
        "features": ["NVMe 缓存", "双路冗余"],
        "intro": "数据库是内存与 I/O 密集：高主频、大内存、高速 NVMe 决定吞吐，ECC 与双机热备决定可用性。",
        "content_md": """## 这个负载需要什么

**大内存 + ECC**：RECC 大内存提升缓存命中；普通内存 7×24 易出错。

**NVMe 数据盘**：高随机读写；RAID1 保护数据目录，日志与数据分离。

**冗余与备份**：双电源双网卡，异地备份 + 主从复制。

## 配置思路

- OLTP 场景内存命中率主导延迟；将热数据尽量留在内存，必要时加内存而不是加盘。
- 双机热备 + 共享存储/复制，避免单点；备份走独立网络，防勒索。

## 选型要点

- 先看内存命中率再决定是否加内存；命中率高时加盘收益递减。
- 日志盘与数据盘分离，用高随机写 NVMe 承担日志。""",
        "platforms": [_P_ES220, _P_ZS220],
    },
    {
        "key": "nas", "scene_key": "store", "scene": "海量存储",
        "title": "冷热分层 NAS", "sub": "盘位与冗余优先，CPU 是配角",
        "features": ["RAID6", "2.5G 网络"],
        "intro": "存储服务器的核心是盘位数量、冗余等级与网络带宽，CPU 只要足够驱动阵列与文件服务即可。",
        "content_md": """## 这个负载需要什么

**硬件 RAID**：数据盘用企业级盘 + 硬件 RAID 卡，RAID6 容忍双盘。

**冷热分层**：热数据放 SSD/高转速，冷数据放大容量企业级盘。

**盲板与散热**：空位装盲板防热风回流；2.5G/10G 网络。

## 配置思路

- NAS 拼的是容量与冗余，不是核心数；4-8 核 + 32-64G 通常够用。
- 监控盘/桌面盘不做服务器数据盘；用希捷银河、西数 Ultrastar 等企业级。

## 选型要点

- 盘位数量决定扩容上限，先留足盘位再谈容量。
- 硬件 RAID 卡别省，软 RAID 在重建与掉盘场景可靠性差。""",
        "platforms": [_P_ES220, _P_ZS220],
    },
    {
        "key": "cae", "scene_key": "sim", "scene": "工业仿真",
        "title": "CAE/结构仿真", "sub": "浮点与超大内存，多核并行为王",
        "features": ["AVX2", "2000W 冗余"],
        "intro": "有限元、流体、渲染是典型的多核浮点负载，AVX2 指令集与内存带宽决定求解速度。",
        "content_md": """## 这个负载需要什么

**高核 + AVX2**：双路 EPYC 96 核以上；无 AVX2 很多求解器跑不动。

**512G 内存**：网格与中间结果常驻内存，容量比主频更吃紧。

**大功率冗余**：高负载双路散热 + 2000W 冗余电源。

## 配置思路

- 求解规模靠内存撑，速度靠核数 × 每核浮点；瓶颈往往是内存而非 CPU。
- 多节点并行走低延迟互连（如 RoCE/InfiniBand），单机先看内存上限。

## 选型要点

- 确认 CPU 支持 AVX2，否则大量求解器无法启动。
- 内存通道与容量同样重要，建议插满通道再谈主频。""",
        "platforms": [_P_ES220, _P_ZS220],
    },
]


def ensure_solutions_seeded():
    """Insert baseline solutions if their key is missing (idempotent)."""
    repo = SolutionRepository()
    try:
        inserted = 0
        for item in _SEED:
            if repo.get_by_key(item["key"]):
                continue
            repo.create(item)
            inserted += 1
        if inserted:
            print(f"   solutions seeded: +{inserted}")
        return inserted
    finally:
        repo.close()
