"""B3 — 策略中心：毛利三档种子（pricing.margin_tier，按 platform_type 分层）。

每平台一条 active 策略：scope={platform_type:X}，body={floor,standard,premium}（百分点）。
- floor：底线，报价利润率低于此值触发告警（对应原 profit_margin_alert_threshold 的分层化）
- standard：标准目标
- premium：优质

数值是合理起步默认，后台 strategy 管理页可改。
幂等：同 domain+type+scope 的 active 策略已存在则跳过。

用法（backend 目录）：python -X utf8 scripts/seed_pricing_strategies.py
"""
import sys
import os
import json

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.repository.strategy_repo import StrategyRepository


# 每平台毛利三档（百分点）。一期默认值，后台可改。
TIERS = {
    "Polaris": {"floor": 8, "standard": 12, "premium": 18},
    "Orion":   {"floor": 8, "standard": 12, "premium": 18},
    "Intel":   {"floor": 6, "standard": 10, "premium": 15},
    "工作站":  {"floor": 10, "standard": 15, "premium": 20},
}


def main():
    repo = StrategyRepository()
    try:
        existing = {
            json.dumps(s["scope"], ensure_ascii=False)
            for s in repo.list(domain="pricing", status="active")
            if s["type"] == "margin_tier"
        }
        added, skipped = [], []
        for pt, body in TIERS.items():
            scope = {"platform_type": pt}
            key = json.dumps(scope, ensure_ascii=False)
            if key in existing:
                skipped.append(pt)
                continue
            repo.create({
                "domain": "pricing",
                "type": "margin_tier",
                "name": f"毛利三档·{pt}",
                "scope": scope,
                "body": body,
                "status": "active",
                "description": f"{pt} 平台毛利底线/标准/优质三档（百分点）；低于 floor 触发告警",
                "change_reason": "一期种子",
            }, operator="seed")
            added.append(pt)
        print(f"✓ 新增毛利三档：{added or '无'}")
        print(f"  跳过（已存在）：{skipped or '无'}")
    finally:
        repo.close()


if __name__ == '__main__':
    main()
