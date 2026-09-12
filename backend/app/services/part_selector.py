# -*- coding: utf-8 -*-
"""part_selector —— 需求分析 skill 的唯一配件选型工具（AI 决策，工具落地）。

AI-first 原则：
- AI 决定“要什么/怎么配”：cpu/memory/storage/gpu/raid/
  nic 是唯一真值源（llm_extract_enhance 产出，slot_contract 对齐）。
  AI 在调用 select_parts 前补全模糊项（内存拆条、硬盘接口、GPU 型号等）。
- 工具只做“检索 + 落地”：料号/价格/规格全部来自 KP 库真实返回；未命中白盒 unmatched，
  绝不静默回退固定规则。
- 类目直接取 KP 库真实类目，规则词不再来自规则目录；场景包等规则驱动项已移除。
"""

# 总出口薄壳（2026-09-11 拆分）：实现住在四个语义模块里，这里只做转发。
# 现存 import 一律不用改；不许在本文件重新长出实现（tests/test_skill_module_layout.py 守卫）。
from app.services.part_specs import (  # noqa: F401
    _SeriesScopedRepo,
    _cap_disp,
    _capacity_mismatch,
    _drive_display,
    _drive_media_label,
    _gb_of,
    _norm_model,
    _num_of,
    _series_ok,
    _spec_hit,
    kp_repository,
)
from app.services.part_row_identity import (  # noqa: F401
    _ROW_NOISE_RE,
    _is_row_id_key,
    _norm_cat_key,
    _pick,
    _pick_entry_key_norm,
    _placeholder,
    _ref_candidates,
    _ref_hit,
    _row,
    _unmatched,
    apply_kp_picks,
    apply_kp_waived,
    config_rows_to_parts,
    ensure_pick_rows,
    kp_registered_specified,
    kp_row_id,
    kp_row_key,
    kp_row_key_norm,
    kp_rows_present,
    kp_rows_slot_keys,
    pick_entry_identity,
    pick_for_row,
    pick_is_stale,
    pick_key_for_row,
    requirement_rows_to_parts,
    resolve_row_ref,
    row_content_rev,
    row_desc_norm,
    row_id_for_origin,
    row_key_norm,
    row_origin,
    row_ref_meta,
    stamp_row_identity,
)
from app.services.part_recall import (  # noqa: F401
    CANDIDATE_RESOLVERS,
    DEFAULT_RESOLVER,
    _ALIAS_CACHE,
    _candidate_desc,
    _category_aliases,
    _category_index,
    _dedupe_rows,
    _kp_candidate_pools_full,
    _kp_row_recall_pools,
    _resolve_db_category,
    _row_search_hits,
    _search_category_names,
    kp_candidate_pools,
    list_kp_categories,
    resolve_kp_category,
    resolve_kp_pools,
    resolve_part_alias,
    retrieve_part_candidates,
)
from app.services.part_landing import (  # noqa: F401
    _ground_cpu,
    _ground_generic,
    _ground_gpu,
    _ground_memory,
    _ground_nic,
    _ground_raid,
    _ground_storage,
    _scenario_slot_for,
    _slot_db_cats,
    manual_pick_options,
    manual_signal_for_text,
    select_parts,
)

from app.repository.kp_repo import KPRepository  # noqa: F401  历史 import 点，保持可用

import logging  # noqa: F401

logger = logging.getLogger(__name__)
