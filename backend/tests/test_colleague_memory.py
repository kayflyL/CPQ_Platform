"""同事结构化记忆（2026-09-27 重构 + 2026-09-28 域隔离）：
prompt 注入块 + 记忆工具四动作 + 空闲整理归并 + 公共/私有域隔离。"""
import asyncio
import json

from app.models.colleague_memory import MEMORY_TYPES
from app.services import colleague_memory_service as svc


def _norm_type(value):
    value = str(value or "").strip()
    return value if value in MEMORY_TYPES else "business_fact"


def _uid(row):
    return str(row.get("user_id") or "").strip()


class FakeRepo:
    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self._next = max((r["id"] for r in rows), default=0) + 1
        self.touched = []

    def list_by_role(self, role_key, keyword="", limit=100, include_retired=False,
                     visible_to=None, public_only=False):
        rows = [r for r in self.rows.values()
                if include_retired or not r.get("retired_at")]
        if public_only:
            rows = [r for r in rows if not _uid(r)]
        elif str(visible_to or "").strip():
            v = str(visible_to).strip()
            rows = [r for r in rows if not _uid(r) or _uid(r) == v]
        return sorted(rows, key=lambda r: (-int(bool(r.get("pinned"))), -r["id"]))[:limit]

    def get(self, mid):
        row = self.rows.get(int(mid))
        return dict(row) if row else None

    def add(self, role_key, mtype, content, source="auto", pinned=False,
            created_by="", provenance=None, user_id=None):
        content = str(content or "").strip()
        if not content:
            return None
        row = {"id": self._next, "role_key": role_key, "type": _norm_type(mtype),
               "content": content[:1000], "source": source, "pinned": pinned,
               "created_by": created_by, "valid_from": "2026-09-27 10:00:00",
               "retired_at": None, "superseded_by": None, "last_accessed_at": None,
               "provenance": json.dumps(provenance, ensure_ascii=False) if provenance else None,
               "user_id": str(user_id or "").strip() or None}
        self._next += 1
        self.rows[row["id"]] = row
        return dict(row)

    def update(self, mid, patch):
        row = self.rows.get(int(mid))
        if not row:
            return None
        if "content" in patch and not str(patch["content"]).strip():
            return None
        row.update({k: v for k, v in patch.items() if v is not None})
        return dict(row)

    def retire(self, mid, superseded_by=None, force=False):
        row = self.rows.get(int(mid))
        if not row or row.get("retired_at"):
            return dict(row) if row else None
        if not force and (row.get("pinned") or str(row.get("source") or "") == "manual"):
            return None
        row["retired_at"] = "2026-09-27 11:00:00"
        if superseded_by is not None:
            row["superseded_by"] = int(superseded_by)
        return dict(row)

    def touch_access(self, ids):
        fresh = [int(i) for i in ids
                 if int(i) in self.rows and not self.rows[int(i)].get("retired_at")]
        self.touched.extend(fresh)
        return len(fresh)

    def enforce_cap(self, role_key, cap=100, user_id=None):
        return 0


def _existing():
    return [
        {"id": 1, "role_key": "support_engineer", "type": "preference",
         "content": "报价默认按进口平台配", "source": "auto", "pinned": False,
         "user_id": "u1"},
        {"id": 2, "role_key": "support_engineer", "type": "business_fact",
         "content": "主力推 Orion 系列", "source": "manual", "pinned": True},
    ]


_CTX = {"role_key": "support_engineer", "thread_id": "dm:support_engineer",
        "price_ok": False, "user_id": "u1"}


# ── 注入层：memory_block ─────────────────────────────────────────────────────

def test_memory_block_groups_by_type(monkeypatch):
    rows = [
        {"id": 1, "type": "preference", "content": "别再推荐 8T 盘"},
        {"id": 2, "type": "business_fact", "content": "报价默认含三年质保"},
        {"id": 3, "type": "user_profile", "content": "客户是华东区集成商"},
    ]
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo(rows))
    block = svc.memory_block("support_engineer")
    assert "同事长期记忆" in block
    assert "[偏好反馈] 别再推荐 8T 盘" in block
    assert "[业务事实] 报价默认含三年质保" in block
    assert "[用户画像] 客户是华东区集成商" in block


def test_memory_block_empty(monkeypatch):
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo([]))
    assert svc.memory_block("nobody") == ""


def test_memory_block_durable_always_included(monkeypatch):
    rows = [{"id": 50, "role_key": "r", "type": "guide",
             "content": "手工录入不受限", "source": "manual", "pinned": False}]
    for i in range(1, 11):
        rows.append({"id": i, "role_key": "r", "type": "business_fact",
                     "content": f"自动{i}", "source": "auto", "pinned": False})
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo(rows))
    block = svc.memory_block("r", limit=2, user_text="")
    assert "手工录入不受限" in block
    assert "自动10" in block and "自动9" in block  # limit 个非置顶按最新序
    assert "- [业务事实] 自动1\n" not in block  # 超出 limit 的最旧自动记忆不注入


def test_memory_block_relevance_beats_recency(monkeypatch):
    rows = [
        {"id": 1, "role_key": "r", "type": "business_fact",
         "content": "旧但相关：客户主营金融行业", "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact",
         "content": "新但不相关", "source": "auto", "pinned": False},
    ]
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo(rows))
    from app.services import colleague_memory_search
    monkeypatch.setattr(colleague_memory_search, "rank_by_relevance",
                        lambda rk, rws, q, k: list(reversed(rws))[:k])
    block = svc.memory_block("r", limit=1, user_text="客户做什么行业的？")
    assert "旧但相关" in block
    assert "新但不相关" not in block


def test_memory_block_degrades_to_newest_when_embed_unavailable(monkeypatch):
    rows = [
        {"id": 1, "role_key": "r", "type": "business_fact",
         "content": "旧记忆", "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact",
         "content": "新记忆", "source": "auto", "pinned": False},
    ]
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo(rows))
    from app.services import colleague_memory_search
    monkeypatch.setattr(colleague_memory_search, "rank_by_relevance",
                        lambda rk, rws, q, k: None)
    block = svc.memory_block("r", limit=1, user_text="随便问")
    assert "新记忆" in block and "旧记忆" not in block


def test_memory_block_touches_selected_and_skips_retired(monkeypatch):
    rows = [
        {"id": 1, "role_key": "r", "type": "business_fact", "content": "活跃",
         "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact", "content": "已失效",
         "source": "auto", "pinned": False, "retired_at": "2026-09-26 00:00:00"},
    ]
    repo = FakeRepo(rows)
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    block = svc.memory_block("r", limit=5, user_text="问点事")
    assert "活跃" in block and "已失效" not in block
    assert repo.touched == [1]


# ── 写入层：tool_memory_action 四动作 ────────────────────────────────────────

def test_tool_write_happy_path_records_provenance(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action(
        {"action": "write", "type": "preference", "content": "客户偏好周三沟通"},
        tool_ctx=_CTX)
    assert result["ok"] is True
    row = repo.rows[result["memory"]["id"]]
    prov = json.loads(row["provenance"])
    assert prov["via"] == "memory_tool" and prov["thread_id"] == "dm:support_engineer"
    assert row["valid_from"]


def test_tool_write_dedups_exact_content(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action(
        {"action": "write", "type": "preference", "content": "报价默认按进口平台配"},
        tool_ctx=_CTX)
    assert result["ok"] is False and result.get("duplicate_of") == 1


def test_tool_write_rejects_bad_type_and_empty(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    r1 = svc.tool_memory_action({"action": "write", "type": "hobby", "content": "x"}, _CTX)
    r2 = svc.tool_memory_action({"action": "write", "type": "guide", "content": "  "}, _CTX)
    assert r1["ok"] is False and "type" in r1["error"]
    assert r2["ok"] is False


def test_tool_retire_refuses_durable(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action({"action": "retire", "id": 2}, _CTX)
    assert result["ok"] is False
    assert repo.rows[2].get("retired_at") is None


def test_tool_retire_auto_row_stamps(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action(
        {"action": "retire", "id": 1, "reason": "客户已改口国产化"}, _CTX)
    assert result["ok"] is True
    assert repo.rows[1]["retired_at"]
    # 失效后不再出现在注入与 list
    assert all(r["id"] != 1 for r in repo.list_by_role("support_engineer"))


def test_tool_rejects_cross_role_access(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    other = dict(_CTX, role_key="cost_analyst")
    r1 = svc.tool_memory_action({"action": "view", "id": 1}, other)
    r2 = svc.tool_memory_action({"action": "retire", "id": 1}, other)
    assert r1["ok"] is False and r2["ok"] is False
    assert svc.tool_memory_action({"action": "list"}, {"role_key": ""})["ok"] is False


def test_tool_list_and_unknown_action(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    listed = svc.tool_memory_action({"action": "list"}, _CTX)
    assert listed["ok"] is True and listed["count"] == 2
    bad = svc.tool_memory_action({"action": "purge"}, _CTX)
    assert bad["ok"] is False and "action" in bad["error"]


# ── 域隔离（2026-09-28）：对话私有 / 治理面公共 ─────────────────────────────

def test_memory_block_scopes_private_rows_by_user(monkeypatch):
    rows = [
        {"id": 1, "role_key": "r", "type": "business_fact", "content": "公共事实",
         "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact", "content": "u1的私有偏好",
         "source": "auto", "pinned": False, "user_id": "u1"},
        {"id": 3, "role_key": "r", "type": "business_fact", "content": "u2的私有偏好",
         "source": "auto", "pinned": False, "user_id": "u2"},
    ]
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: FakeRepo(rows))
    b1 = svc.memory_block("r", user_id="u1")
    assert "u1的私有偏好" in b1 and "u2的私有偏好" not in b1 and "公共事实" in b1
    b2 = svc.memory_block("r", user_id="u2")
    assert "u2的私有偏好" in b2 and "u1的私有偏好" not in b2
    b_anon = svc.memory_block("r")  # 无用户上下文=只注入公共域（fail-safe）
    assert "公共事实" in b_anon and "u1的私有偏好" not in b_anon


def test_tool_write_requires_user_context(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    ctx = {k: v for k, v in _CTX.items() if k != "user_id"}
    result = svc.tool_memory_action(
        {"action": "write", "type": "guide", "content": "无主记忆"}, ctx)
    assert result["ok"] is False and "用户" in result["error"]
    assert all(r["content"] != "无主记忆" for r in repo.rows.values())


def test_tool_write_lands_in_caller_private_domain(monkeypatch):
    repo = FakeRepo(_existing())
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action(
        {"action": "write", "type": "business_fact", "content": "u1专属事实"}, tool_ctx=_CTX)
    assert result["ok"] is True
    assert repo.rows[result["memory"]["id"]]["user_id"] == "u1"
    other_view = repo.list_by_role("support_engineer", visible_to="u2")
    assert all(r["content"] != "u1专属事实" for r in other_view)


def test_tool_retire_refuses_public_rows(monkeypatch):
    repo = FakeRepo([
        {"id": 1, "role_key": "support_engineer", "type": "business_fact",
         "content": "公共记忆", "source": "auto", "pinned": False},  # user_id 空=公共域
    ])
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    result = svc.tool_memory_action({"action": "retire", "id": 1}, _CTX)
    assert result["ok"] is False and "公共域" in result["error"]
    assert repo.rows[1].get("retired_at") is None


def test_tool_view_rejects_other_users_private(monkeypatch):
    repo = FakeRepo(_existing() + [
        {"id": 9, "role_key": "support_engineer", "type": "business_fact",
         "content": "别人的私有记忆", "source": "auto", "pinned": False, "user_id": "u2"},
    ])
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    assert svc.tool_memory_action({"action": "view", "id": 9}, _CTX)["ok"] is False


# ── 整理层：consolidate_role ────────────────────────────────────────────────

def _patch_env(monkeypatch, repo, chat_json):
    import app.services.llm_client as llm_client
    import app.services.ai_colleague_service as acs
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    monkeypatch.setattr(acs, "get_colleague", lambda rk: {"system_prompt": "测试同事"})
    monkeypatch.setattr(llm_client, "chat_json", chat_json)


def test_consolidate_merges_and_supersedes(monkeypatch):
    repo = FakeRepo([
        {"id": 1, "role_key": "r", "type": "business_fact", "content": "客户用海光平台",
         "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "preference", "content": "张总那边海光",
         "source": "auto", "pinned": False},
        {"id": 3, "role_key": "r", "type": "business_fact", "content": "客户主营金融",
         "source": "auto", "pinned": False},
    ])

    async def fake_chat_json(messages, **kwargs):
        return {"ops": [
            {"op": "merge", "ids": [1, 2], "type": "business_fact", "content": "张总客户用海光平台"},
            {"op": "retire", "id": 3, "reason": "已过时"},
        ]}

    _patch_env(monkeypatch, repo, fake_chat_json)
    report = asyncio.run(svc.consolidate_role("r"))
    assert report["ok"] is True and report["applied"] == 2  # merge(2合1) + retire#3
    assert repo.rows[1]["retired_at"] and repo.rows[1]["superseded_by"] == 4
    assert repo.rows[2]["retired_at"] and repo.rows[2]["superseded_by"] == 4
    assert repo.rows[3]["retired_at"] is not None
    new = repo.rows[4]
    assert new["content"] == "张总客户用海光平台"
    assert json.loads(new["provenance"])["via"] == "consolidation"


def test_consolidate_never_touches_durable(monkeypatch):
    repo = FakeRepo([
        {"id": 1, "role_key": "r", "type": "guide", "content": "管理员守则",
         "source": "manual", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact", "content": "自动记忆",
         "source": "auto", "pinned": False},
    ])

    async def fake_chat_json(messages, **kwargs):
        # LLM 越权提案：碰钉死集 + 未知 id
        return {"ops": [
            {"op": "retire", "id": 1, "reason": "越权"},
            {"op": "merge", "ids": [1, 2], "type": "guide", "content": "合并钉死集"},
            {"op": "retire", "id": 999},
        ]}

    _patch_env(monkeypatch, repo, fake_chat_json)
    report = asyncio.run(svc.consolidate_role("r"))
    assert report["ok"] is True
    assert repo.rows[1].get("retired_at") is None  # 手工条目原样
    assert len(repo.rows) == 2  # merge 也被拦下，没有新条目
    assert any(s.startswith("durable:") for s in report["skipped"])


def test_consolidate_retypes_single(monkeypatch):
    repo = FakeRepo([
        {"id": 1, "role_key": "r", "type": "business_fact", "content": "客户偏好简洁汇报",
         "source": "auto", "pinned": False},
    ])

    async def fake_chat_json(messages, **kwargs):
        return {"ops": [{"op": "retype", "id": 1, "type": "preference"}]}

    _patch_env(monkeypatch, repo, fake_chat_json)
    asyncio.run(svc.consolidate_role("r"))
    assert repo.rows[1]["type"] == "preference"


def test_consolidate_llm_failure_returns_not_ok(monkeypatch):
    repo = FakeRepo(_existing())

    async def boom(messages, **kwargs):
        raise RuntimeError("LLM down")

    _patch_env(monkeypatch, repo, boom)
    report = asyncio.run(svc.consolidate_role("r"))
    assert report["ok"] is False
    assert len(repo.rows) == 2


def test_consolidate_only_touches_public_domain(monkeypatch):
    repo = FakeRepo([
        {"id": 1, "role_key": "r", "type": "business_fact", "content": "公共旧记忆",
         "source": "auto", "pinned": False},
        {"id": 2, "role_key": "r", "type": "business_fact", "content": "u1的私有记忆",
         "source": "auto", "pinned": False, "user_id": "u1"},
    ])

    async def fake_chat_json(messages, **kwargs):
        listing = messages[1]["content"]
        assert "u1的私有记忆" not in listing  # 私有域不进整理清单
        return {"ops": [{"op": "retire", "id": 1, "reason": "过时"}]}

    _patch_env(monkeypatch, repo, fake_chat_json)
    report = asyncio.run(svc.consolidate_role("r"))
    assert report["ok"] is True
    assert repo.rows[1]["retired_at"] is not None
    assert repo.rows[2].get("retired_at") is None
