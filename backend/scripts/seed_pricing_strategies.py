"""B3 — 策略中心：加法定价引擎的 6 条维度策略种子。

替换原 pricing.margin_tier（按平台三档）为多维度加法模型。每条维度一条 active 策略，
type 为维度 key（与 frontend constants/pricingMeta.ts 的 DimensionKey 一致），scope=None（全局系数表）：

    platform_baseline  base   {Polaris:15, Orion:11, Intel:11, 工作站:13}      基准毛利，加法链起点
    industry_adj       add    {行业→±百分点}                                     在基准上 ±
    region_adj         add    {factors:{国内/海外/偏远}, keywords:{...}}         交付地区分桶后 ±
    order_mult         mult   {customer_type→系数}                              订单类型乘系数
    cost_tier          mult   {tiers:[{max,mult}]}                              BOM 成本阶梯乘系数
    guardrail          clamp  {floor, cap}                                      保底封顶夹取

数值是合理起步默认，后台策略中心画布可改。
⚠️ 默认值必须与 frontend/src/constants/pricingMeta.ts 的 DEFAULT_DIM_BODIES 保持一致。

幂等：同 domain+type 的 active 策略已存在则跳过（不覆盖用户改动）。
      --reset 强制覆盖为默认；--dry-run 只打印不写。
同时把线上旧 pricing.margin_tier / pricing.pricing_scenario 归档为 archived（不删，可回滚）。

用法（backend 目录）：
    python -X utf8 scripts/seed_pricing_strategies.py            # 增量 seed + 归档旧类型
    python -X utf8 scripts/seed_pricing_strategies.py --reset    # 强制覆盖 6 维度为默认
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
            "factors": {"国内": 0, "海外": 2, "偏远": 1},
            "keywords": {
                "海外": ["海外", "境外", "东南亚", "欧美", "中东", "日本", "韩国", "新加坡", "德国", "美国", "越南", "泰国", "马来西亚", "欧洲", "北美"],
                "偏远": ["西藏", "新疆", "青海", "内蒙古", "宁夏", "甘肃", "偏远"],
            },
        },
        "desc": "按交付地区分桶(国内/海外/偏远)后 ±百分点",
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
        "body": {"floor": 7, "cap": 30},
        "desc": "最终毛利率夹在 [保底, 封顶] 之间",
    },
}

LEGACY_TYPES = ("margin_tier", "pricing_scenario")  # 旧查表分类模型，归档


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不写库")
    ap.add_argument("--reset", action="store_true", help="强制覆盖 6 维度为默认值（保留用户改动的安全默认关）")
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

        print(f"✓ 维度 seed：新增 {added or '无'}；跳过(已存在) {skipped or '无'}；重置 {reset or '无'}")
        print(f"  归档旧类型 {archived or '无'}（margin_tier/pricing_scenario → archived，未删除）")
        if dry:
            print("  [dry-run] 未实际写库")
    finally:
        repo.close()


if __name__ == '__main__':
    main()
