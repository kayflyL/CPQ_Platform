"""型号家族词自动同步 —— 从 kp 库 CPU/GPU 品类件名自动补齐 system_config.model_family_words。

原则（拒绝硬编码、自动更新）：
  - 只加不删：仅把库中新出现的型号 token / 家族前缀并入配置，绝不覆盖用户手工编辑；
  - 保守抽取：只收「字母开头、长度 4-10」的型号 token（h100/a100/r9700/kh50000/b200…），
    以及其字母前缀（len>=2，如 kh50000→kh、rtx4090d→rtx）——天然过滤 32G/5090/涡轮卡 等
    容量与中文噪声，品牌短词（amd/intel/pro/ai 等 len<4）也被排除，无需维护黑名单；
  - 幂等：无新增返回 0。startup 调用；新料号进库后重启即自动补齐（未来可加管理面按钮手动触发）。
"""
import re
from typing import Optional

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")


def _candidate_words(name: str) -> set:
    """保守抽取：字母开头、长度 4-10、且【含数字】的型号 token。
    型号必有数字（h100/a100/r9700/kh50000/b200/rtx5090…）；品牌/通用词
    （nvidia/intel/core/server/edition/pro/ai 等）无数字或过短，天然被排除——
    不额外维护黑名单，家族前缀（kh/rtx 等）由基线词表覆盖。"""
    out = set()
    for m in _TOKEN_RE.finditer(name or ""):
        t = m.group().lower()
        if 4 <= len(t) <= 10 and any(ch.isdigit() for ch in t):
            out.add(t)
    return out


def sync_model_family_words() -> int:
    """从 kp 库 CPU/GPU 件名自动补齐家族词表。返回新增词数（幂等）。"""
    from app.repository.kp_repo import KPRepository
    from app.repository.system_config_repo import SystemConfigRepository
    from app.services.clarity_evaluator import load_family_words

    kp = KPRepository()
    try:
        cats = kp.get_categories()
    finally:
        kp.close()
    cpu_cats = [c.get("category") for c in cats
                if "cpu" in (c.get("category") or "").lower()]
    gpu_cats = [c.get("category") for c in cats
                if "gpu" in (c.get("category") or "").lower() or "显卡" in (c.get("category") or "")]

    collected: dict[str, set] = {"CPU": set(), "GPU": set()}
    kp = KPRepository()
    try:
        for name, key in [(n, "CPU") for n in cpu_cats if n] + [(n, "GPU") for n in gpu_cats if n]:
            try:
                rows = kp.get_by_category(name) or []
            except Exception:
                rows = []
            for r in rows:
                collected[key] |= _candidate_words(r.get("model") or "")
    finally:
        kp.close()

    repo = SystemConfigRepository()
    try:
        cur = load_family_words()
        added = 0
        for key in ("CPU", "GPU"):
            base = [str(w) for w in (cur.get(key) or []) if w]
            new_words = [w for w in sorted(collected[key]) if w not in base]
            if new_words:
                cur[key] = base + new_words
                added += len(new_words)
        if added:
            repo.set("model_family_words", cur, description="CPU/GPU 型号家族词表（startup 自动补齐）")
        return added
    finally:
        repo.close()
