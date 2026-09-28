"""B3 — 策略中心：加法定价引擎的 8 条维度策略种子。

替换原 pricing.margin_tier（按平台三档）为多维度加法模型。每条维度一条 active 策略，
type 为维度 key（与 frontend constants/pricingMeta.ts 的 DimensionKey 一致），scope=None（全局系数表）：

    platform_baseline  base   {Polaris:15, Orion:11, Intel:11, 工作站:13}      基准毛利，加法链起点
    industry_adj       add    {行业→±百分点}                                     在基准上 ±
    region_adj         add    {factors:{桶→±百分点|{pct,fixed_fee}}, keywords}  交付地区分桶后 ±（海外可带每台固定费）
    form_adj           add    {2U:0, 4U:-1, 5U:-1, 塔式:1}                      机箱形态 ±百分点（4U 成本高压点）
    order_mult         mult   {customer_type→系数}                              订单类型乘系数（customer_type 枚举存商机 extra_fields）
    cost_tier          mult   {tiers:[{max,mult}]}                              BOM 成本阶梯乘系数
    qty_mult           mult   {bands:[{min,mult}]}                              台数折扣（量大让利）
    guardrail          clamp  {floor, cap, tiers?:[{customer_type,floor,cap}]} 保底封顶夹取（可按订单类型分档红线）

另有两条独立策略（非流水线维度）：
    margin_alert   工作台低毛利弹窗（开关+门槛+文案）
    part_margin    BOM 分项毛利（deal 目标毛利之上的品类 ±百分点，未来 AI 出价 per-line 消费）

数值是合理起步默认，后台策略中心画布可改。
⚠️ 默认值必须与 frontend/src/constants/pricingMeta.ts 的 DEFAULT_DIM_BODIES / DEFAULT_MARGIN_ALERT / DEFAULT_PART_MARGIN 保持一致。

幂等：同 domain+type 的 active 策略已存在则跳过（不覆盖用户改动）。
      --reset 强制覆盖为默认；--dry-run 只打印不写。
同时把线上旧 pricing.margin_tier / pricing.pricing_scenario 归档为 archived（不删，可回滚）。

用法（backend 目录）：
    python -X utf8 scripts/seed_pricing_strategies.py            # 增量 seed + 归档旧类型
    python -X utf8 scripts/seed_pricing_strategies.py --reset    # 强制覆盖 8 维度 + margin_alert + part_margin 为默认
    python -X utf8 scripts/seed_pricing_strategies.py --dry-run  # 只打印
"""
import sys
import os
import json
import argparse

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.repository.strategy_repo import StrategyRepository

# 维度默认系数表 —— 与 frontend constants/pricingMeta.ts DEFAULT_DIM_BODIES 同步
DEFAULT_DIMS = {
    "platform_baseline": {
        "name": "平台基准毛利",
        "body": {"Polaris": 15, "Orion": 11, "Intel": 11, "工作站": 13},
        "desc": "按芯片平台取基准毛利率（百分点），加法链起点",
    },
    "industry_adj": {
        "name": "行业浮动",
        "body": {"AI算力": 3, "IDC机房": -2, "政企信息化": 3, "高校科研": 0, "安防存储": 1, "工业边缘": 2},
        "desc": "在基准上按客户行业 ±百分点",
    },
    "region_adj": {
        "name": "区域浮动",
        "body": {
            # 海外 = ±百分点 + 每台固定费(报关/国际物流/海外质保，只入售价不进毛利)；纯数字形态兼容
            "factors": {"国内": 0, "海外": {"pct": 2, "fixed_fee": 800}, "偏远": 1},
            "keywords": {
                "海外": ["海外", "境外", "东南亚", "欧美", "中东", "日本", "韩国", "新加坡", "德国", "美国", "越南", "泰国", "马来西亚", "欧洲", "北美"],
                "偏远": ["西藏", "新疆", "青海", "内蒙古", "宁夏", "甘肃", "偏远"],
            },
        },
        "desc": "按交付地区分桶(国内/海外/偏远)后 ±百分点；海外可带每台固定费",
    },
    "form_adj": {
        "name": "形态浮动",
        "body": {"2U": 0, "4U": -1, "5U": -1, "塔式": 1},
        "desc": "按机箱形态 ±百分点（4U 整机成本高压点、塔式利基加点）",
    },
    "order_mult": {
        "name": "订单系数",
        "body": {"直签大客户": 0.9, "渠道分销": 0.7, "集采项目": 0.75, "零散项目": 1.0},
        "desc": "按订单/客户类型乘系数修正",
    },
    "cost_tier": {
        "name": "成本阶梯",
        "body": {"tiers": [{"max": 50000, "mult": 1.1}, {"max": 300000, "mult": 1.0}, {"mult": 0.9}]},
        "desc": "按整机 BOM 总成本阶梯乘系数（成本越高点位越低）",
    },
    "qty_mult": {
        "name": "台数折扣",
        "body": {"bands": [{"min": 1, "mult": 1.0}, {"min": 6, "mult": 0.9}, {"min": 21, "mult": 0.84}, {"min": 51, "mult": 0.75}]},
        "desc": "按销售台数分档乘系数（量越大让利越多；整体毛利率倍率压缩，不改基准/行业/区域加点）",
    },
    "guardrail": {
        "name": "保底封顶",
        "body": {
            "floor": 7,
            "cap": 30,
            # 按订单类型差异化红线（首命中）：渠道/集采毛利天然被系数压低，红线放宽给现实空间
            "tiers": [
                {"customer_type": "渠道分销", "floor": 5, "cap": 25},
                {"customer_type": "集采项目", "floor": 5, "cap": 20},
            ],
        },
        "desc": "最终毛利率夹在 [保底, 封顶] 之间；可按订单类型分档差异化红线",
    },
}

# 利润率告警策略（独立于上方 6 维度；工作台低毛利弹窗的阈值+文案 SSOT，与保底封顶解耦）
# ⚠️ body 必须与 frontend constants/pricingMeta.ts DEFAULT_MARGIN_ALERT 保持一致
MARGIN_ALERT = {
    "name": "利润率告警",
    "body": {
        "enabled": True,
        "threshold": 7,
        "approval_threshold": 5,
        "title": "利润率低于告警线",
        "content": "当前综合毛利率 ${margin}% 低于告警线 ${threshold}%，建议线下走特价审批，系统仅作记录。",
    },
    "desc": "工作台综合毛利率低于门槛时的告警弹窗（开关+门槛+审批红线+标题+正文模板 ${margin}/${threshold}）；低于审批红线发送报价单须总监审批；与保底封顶解耦",
}

LEGACY_TYPES = ("margin_tier", "pricing_scenario")  # 旧查表分类模型，归档

# BOM 分项毛利（独立策略，非流水线：deal 目标毛利之上的品类 ±百分点；演算器预览 + 未来 AI 出价 per-line 消费）
# ⚠️ body 必须与 frontend constants/pricingMeta.ts DEFAULT_PART_MARGIN 保持一致
PART_MARGIN = {
    "name": "BOM 分项毛利",
    "body": {"CPU": 2, "Memory": 3, "HDD/SSD": -2, "GPU": 3, "NIC": 1},
    "desc": "在 deal 目标毛利上按 KP 品类 ±百分点（内存/GPU 加价空间大、硬盘透明竞争压点），每个夹 [保底, 封顶]；未列品类 = 0 修正",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写库")
    ap.add_argument("--reset", action="store_true", help="强制覆盖 8 维度 + margin_alert + part_margin 为默认值（保留用户改动的安全默认关）")
    args = ap.parse_args()

    repo = StrategyRepository()
    dry = args.dry_run
    try:
        all_pricing = repo.list(domain="pricing")
        active_by_type = {s["type"]: s for s in all_pricing if s.get("status") == "active"}

        added, skipped, reset = [], [], []
        for dim_key, meta in DEFAULT_DIMS.items():
            exist = active_by_type.get(dim_key)
            if exist and not args.reset:
                skipped.append(dim_key)
                continue
            payload = {
                "domain": "pricing",
                "type": dim_key,
                "name": meta["name"],
                "scope": None,
                "body": meta["body"],
                "status": "active",
                "description": meta["desc"],
                "change_reason": "加法定价引擎种子",
            }
            if dry:
                added.append(dim_key)
                continue
            if exist and args.reset:
                repo.update(exist["id"], {"body": meta["body"], "name": meta["name"], "description": meta["desc"]}, operator="seed")
                reset.append(dim_key)
            else:
                repo.create(payload, operator="seed")
                added.append(dim_key)

        # 归档旧类型（margin_tier / pricing_scenario）
        archived = []
        for s in all_pricing:
            if s.get("type") in LEGACY_TYPES and s.get("status") == "active":
                if not dry:
                    repo.set_status(s["id"], "archived", operator="seed")
                archived.append(f'{s["type"]}#{s["id"]}')

        # 利润率告警（独立策略，非维度）
        ma_exist = active_by_type.get("margin_alert")
        if ma_exist and not args.reset:
            skipped.append("margin_alert")
        else:
            ma_payload = {
                "domain": "pricing",
                "type": "margin_alert",
                "name": MARGIN_ALERT["name"],
                "scope": None,
                "body": MARGIN_ALERT["body"],
                "status": "active",
                "description": MARGIN_ALERT["desc"],
                "change_reason": "利润率告警策略种子",
            }
            if dry:
                added.append("margin_alert")
            elif ma_exist and args.reset:
                repo.update(ma_exist["id"], {"body": MARGIN_ALERT["body"], "name": MARGIN_ALERT["name"], "description": MARGIN_ALERT["desc"]}, operator="seed")
                reset.append("margin_alert")
            else:
                repo.create(ma_payload, operator="seed")
                added.append("margin_alert")

        # BOM 分项毛利（独立策略，非维度）
        pm_exist = active_by_type.get("part_margin")
        if pm_exist and not args.reset:
            skipped.append("part_margin")
        else:
            pm_payload = {
                "domain": "pricing",
                "type": "part_margin",
                "name": PART_MARGIN["name"],
                "scope": None,
                "body": PART_MARGIN["body"],
                "status": "active",
                "description": PART_MARGIN["desc"],
                "change_reason": "BOM 分项毛利种子",
            }
            if dry:
                added.append("part_margin")
            elif pm_exist and args.reset:
                repo.update(pm_exist["id"], {"body": PART_MARGIN["body"], "name": PART_MARGIN["name"], "description": PART_MARGIN["desc"]}, operator="seed")
                reset.append("part_margin")
            else:
                repo.create(pm_payload, operator="seed")
                added.append("part_margin")

        print(f"✓ 维度 seed：新增 {added or '无'}；跳过(已存在) {skipped or '无'}；重置 {reset or '无'}")
        print(f"  归档旧类型 {archived or '无'}（margin_tier/pricing_scenario → archived，未删除）")
        if dry:
            print("  [dry-run] 未实际写库")
    finally:
        repo.close()


if __name__ == '__main__':
    main()
