"""B1 — 建策略中心两张表：rules.strategies + rules.strategy_usage_log。

精准建单表（不碰 rules schema 其他已有表），幂等（已存在跳过）。
模型见 app/models/strategy.py。

用法（backend 目录）：python -X utf8 scripts/init_strategy_tables.py
"""
import sys
import os

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sqlalchemy import inspect
from app.models.base import rules_engine
from app.models.strategy import Strategy, StrategyUsageLog


def main():
    insp = inspect(rules_engine)
    targets = [
        (Strategy, "strategies"),
        (StrategyUsageLog, "strategy_usage_log"),
    ]
    for model, name in targets:
        if insp.has_table(name, schema="rules"):
            print(f"skip rules.{name}（已存在）")
        else:
            model.__table__.create(rules_engine)
            print(f"✓ created rules.{name}")


if __name__ == '__main__':
    main()
