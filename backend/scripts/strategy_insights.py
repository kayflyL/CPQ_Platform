"""策略洞察 — 跑真实商机/报价数据，验证哪些维度值得做策略（只读统计，不改数据）。

发现维度不靠假设：直接扫所有商机的 extra_fields JSON，统计每个 key 的
填充率 + 值分布。再跑毛利分布 / 需求原文→机型 / 高频配置组合。

用法（在 backend 目录）：
  python -X utf8 scripts/strategy_insights.py
"""
import sys
import os
import json
from collections import Counter
from statistics import median

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sqlalchemy import text
from app.models.base import Opportunity_SessionLocal


def pct(n, d):
    return f"{n/d*100:.1f}%" if d else "—"


def main():
    s = Opportunity_SessionLocal()
    try:
        # ============ 1. 总览 ============
        tot = s.execute(text("""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE status != 'deleted') AS not_deleted,
              COUNT(*) FILTER (WHERE status = 'archived') AS archived
            FROM opportunities.opportunities
        """)).mappings().first()
        qstat = s.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE status = 'active') AS active_q,
              COUNT(*) FILTER (WHERE status = 'active' AND exported_at IS NOT NULL) AS exported
            FROM opportunities.quotations
        """)).mappings().first()

        nd = tot['not_deleted'] or 0
        print("=" * 64)
        print("【1. 总览】")
        print(f"  商机总数（含已删）：{tot['total']}")
        print(f"  未删除商机：{nd}（其中 archived {tot['archived']}）")
        print(f"  报价单（active）：{qstat['active_q']}（已导出冻结 {qstat['exported']}）")

        if nd == 0:
            print("\n无商机数据，结束。")
            return

        # ============ 2. 核心列分布：platform_type / chassis_form ============
        print("\n" + "=" * 64)
        print("【2. 核心列维度分布】")
        for col, label in [("platform_type", "平台类型"), ("chassis_form", "机箱形态")]:
            rows = s.execute(text(f"""
                SELECT COALESCE({col}, '') AS v, COUNT(*) AS n
                FROM opportunities.opportunities
                WHERE status != 'deleted'
                GROUP BY {col} ORDER BY n DESC
            """)).mappings().all()
            print(f"  · {label}（{col}）：")
            for r in rows:
                v = r['v'] or '(空)'
                print(f"      {v:<20} {r['n']:>4}  ({pct(r['n'], nd)})")

        # ============ 3. extra_fields 维度自动发现（核心）============
        print("\n" + "=" * 64)
        print("【3. extra_fields 动态字段发现（填充率 + 值分布 top5）】")
        ef_rows = s.execute(text("""
            SELECT extra_fields FROM opportunities.opportunities
            WHERE status != 'deleted'
        """)).mappings().all()
        key_fill = Counter()       # 有非空值的次数
        key_values = {}            # key -> Counter of values
        for r in ef_rows:
            raw = r['extra_fields']
            if not raw:
                continue
            try:
                ef = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(ef, dict):
                continue
            for k, v in ef.items():
                if v is None or v == '' or v == []:
                    continue
                key_fill[k] += 1
                if isinstance(v, str) and len(v) <= 40:
                    key_values.setdefault(k, Counter())[v] += 1

        print(f"  发现 {len(key_fill)} 个有数据的动态字段（按填充率降序）：")
        for k, n in key_fill.most_common():
            vc = key_values.get(k)
            top = ""
            if vc and len(vc) <= 15:   # 枚举性字段才打分布
                top = " | ".join(f"{val}×{c}" for val, c in vc.most_common(5))
            elif vc:
                top = f"（{len(vc)} 种不同值）"
            print(f"  · {k:<32} {n:>4}/{nd}  {pct(n, nd):>6}  {top}")

        # ============ 4. 已导出报价毛利分布 ============
        print("\n" + "=" * 64)
        print("【4. 已导出报价毛利分布（按平台类型分组）】")
        mrows = s.execute(text("""
            SELECT o.platform_type AS pt, q.profit_margin AS m
            FROM opportunities.quotations q
            JOIN opportunities.opportunities o ON o.opportunity_id = q.opportunity_id
            WHERE q.status = 'active' AND q.exported_at IS NOT NULL
              AND q.profit_margin IS NOT NULL
        """)).mappings().all()
        all_m = [r['m'] for r in mrows]
        print(f"  已导出报价总数：{len(all_m)}")
        if all_m:
            print(f"  整体利润率：均值 {sum(all_m)/len(all_m):.2f}% | 中位 {median(all_m):.2f}% | min {min(all_m):.2f}% | max {max(all_m):.2f}%")
            by_pt = {}
            for r in mrows:
                by_pt.setdefault(r['pt'] or '(空)', []).append(r['m'])
            print("  分平台类型：")
            for pt, ms in sorted(by_pt.items(), key=lambda x: -len(x[1])):
                print(f"    {pt:<16} n={len(ms):>3} 均值 {sum(ms)/len(ms):.2f}% 中位 {median(ms):.2f}%")
        else:
            print("  （无已导出报价，无法看毛利分布）")

        # ============ 5. 需求原文 → 机型 样本 ============
        print("\n" + "=" * 64)
        print("【5. 需求原文 → 最终机型 样本（前 12 条，用于淬炼关键词库）】")
        sample = s.execute(text("""
            SELECT o.opportunity_id, o.extra_fields,
                   (SELECT q.config_server_models FROM opportunities.quotations q
                    WHERE q.opportunity_id = o.opportunity_id
                      AND q.status = 'active' AND q.config_server_models IS NOT NULL
                    ORDER BY q.exported_at DESC NULLS LAST LIMIT 1) AS models
            FROM opportunities.opportunities o
            WHERE o.status != 'deleted'
              AND o.extra_fields LIKE '%customer_requirement_text%'
            LIMIT 12
        """)).mappings().all()
        shown = 0
        for r in sample:
            try:
                ef = json.loads(r['extra_fields'] or '{}')
            except Exception:
                ef = {}
            req = (ef.get('customer_requirement_text') or '').strip()
            if not req or not r['models']:
                continue
            models = r['models']
            if isinstance(models, str):
                try:
                    models = json.loads(models)
                except Exception:
                    models = {}
            mlist = list(models.values()) if isinstance(models, dict) else []
            mlist = [str(m) for m in mlist if m]
            req_short = req.replace('\n', ' ')[:70]
            print(f"  · [{','.join(mlist) or '—'}]")
            print(f"      需求：{req_short}{'…' if len(req) > 70 else ''}")
            shown += 1
        if shown == 0:
            print("  （无同时有需求原文 + 机型的样本）")

        # ============ 6. 高频机型组合 ============
        print("\n" + "=" * 64)
        print("【6. 高频机型（已导出报价 config_server_models 聚合，top 10）】")
        mrows2 = s.execute(text("""
            SELECT config_server_models FROM opportunities.quotations
            WHERE status = 'active' AND exported_at IS NOT NULL
              AND config_server_models IS NOT NULL
        """)).mappings().all()
        model_cnt = Counter()
        for r in mrows2:
            m = r['config_server_models']
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except Exception:
                    m = {}
            if isinstance(m, dict):
                for v in m.values():
                    if v:
                        model_cnt[str(v)] += 1
        if model_cnt:
            for m, n in model_cnt.most_common(10):
                print(f"  · {m:<30} {n}")
        else:
            print("  （已导出报价无机型数据）")

        print("\n" + "=" * 64)
        print("done.")

    finally:
        s.close()


if __name__ == '__main__':
    main()
