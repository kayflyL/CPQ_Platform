# -*- coding: utf-8 -*-
"""解决方案迁移：AI 场景占位方案（ai-infer / ai-train）下线，替换为场景化方案 kb-qa。

默认 dry-run：只打印计划，不写库；--commit 先备份受影响行到 D:\\CPQ_Archive（仓库外，按项目规矩），
再删旧 key、写入 kb-qa（内容来自 app.services.solution_seed.KB_QA_SEED，正文源头是 docs 文档）。
幂等：重复执行时 kb-qa 走 update，旧 key 不存在则跳过删除。
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.repository.solution_repo import SolutionRepository  # noqa: E402
from app.services.solution_seed import KB_QA_SEED  # noqa: E402

OLD_KEYS = ["ai-infer", "ai-train"]
BACKUP_DIR = r"D:\CPQ_Archive"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="写库（先备份旧方案行）")
    args = ap.parse_args()

    repo = SolutionRepository()
    try:
        old_rows = [repo.get_by_key(k) for k in OLD_KEYS]
        old_rows = [r for r in old_rows if r]
        existing_new = repo.get_by_key(KB_QA_SEED["key"])

        print(f"计划：删除 {[r['key'] for r in old_rows]}；{'更新' if existing_new else '新增'} {KB_QA_SEED['key']}"
              f"（正文 {_load_md_len()} 字符，标题《{KB_QA_SEED['title']}》）")
        if not args.commit:
            print("dry-run 未写库；加 --commit 执行")
            return

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(BACKUP_DIR, f"solutions_backup_{ts}.json")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(old_rows, f, ensure_ascii=False, indent=1)
        print(f"已备份 {len(old_rows)} 行 → {backup_path}")

        for r in old_rows:
            repo.delete(r["key"])
            print(f"已删除 {r['key']}")

        if existing_new:
            repo.update(KB_QA_SEED["key"], KB_QA_SEED, operator="migration")
            print(f"已更新 {KB_QA_SEED['key']}")
        else:
            repo.create(dict(KB_QA_SEED), operator="migration")
            print(f"已新增 {KB_QA_SEED['key']}")
        print("迁移完成")
    finally:
        repo.close()


def _load_md_len():
    from app.services.solution_seed import _load_kb_qa_md
    return len(_load_kb_qa_md())


if __name__ == "__main__":
    main()
