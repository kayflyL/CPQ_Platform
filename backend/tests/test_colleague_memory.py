"""同事结构化记忆：抽取归并 ops 应用与 prompt 注入块。"""
import asyncio

from app.models.colleague_memory import MEMORY_TYPES
from app.services import colleague_memory_service as svc


def _norm_type(value):
    value = str(value or "").strip()
    return value if value in MEMORY_TYPES else "business_fact"


class FakeRepo:
    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self._next = max((r["id"] for r in rows), default=0) + 1

    def list_by_role(self, role_key, keyword="", limit=100):
        return sorted(self.rows.values(), key=lambda r: (-int(bool(r.get("pinned"))), -r["id"]))[:limit]

    def add(self, role_key, mtype, content, source="auto", pinned=False, created_by=""):
        content = str(content or "").strip()
        if not content:
            return None
        row = {"id": self._next, "role_key": role_key, "type": _norm_type(mtype),
               "content": content[:1000], "source": source, "pinned": pinned,
               "created_by": created_by}
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

    def delete(self, mid):
        return self.rows.pop(int(mid), None) is not None


def _existing():
    return [
        {"id": 1, "role_key": "support_engineer", "type": "preference",
         "content": "报价默认按进口平台配", "source": "auto", "pinned": False},
        {"id": 2, "role_key": "support_engineer", "type": "business_fact",
         "content": "主力推 Orion 系列", "source": "manual", "pinned": True},
    ]


def test_apply_ops_add_update_delete_dedupe():
    repo = FakeRepo(_existing())
    ops = [
        {"op": "add", "type": "preference", "content": "以后方案默认按国产化平台配"},
        {"op": "add", "type": "preference", "content": "以后方案默认按国产化平台配"},  # 重复 → 只落一条
        {"op": "update", "id": 1, "content": "报价默认按国产化平台配（2026-08 改）"},
        {"op": "update", "id": 999, "content": "不存在的 id → 忽略"},
        {"op": "delete", "id": 2},
        {"op": "noop"},
        {"op": "add", "type": "preference", "content": ""},  # 空内容 → 忽略
    ]
    applied = svc._apply_ops(repo, "support_engineer", ops, repo.list_by_role("support_engineer", limit=200))
    # add#3 / update#1 / delete#2；重复 add、未知 id、noop、空内容全部忽略
    assert sorted(applied) == ["add#3", "delete#2", "update#1"]
    contents = [r["content"] for r in repo.rows.values()]
    assert contents.count("以后方案默认按国产化平台配") == 1
    assert "报价默认按国产化平台配（2026-08 改）" in contents
    assert 2 not in repo.rows


def test_apply_ops_ignores_garbage():
    repo = FakeRepo(_existing())
    ops = ["not-a-dict", {"op": "unknown", "content": "x"}, {"op": "add", "content": "无类型也给默认"}]
    applied = svc._apply_ops(repo, "support_engineer", ops, repo.list_by_role("support_engineer", limit=200))
    assert applied == ["add#3"]
    assert repo.rows[3]["type"] == "business_fact"


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


def test_extract_and_reconcile_applies_llm_ops(monkeypatch):
    repo = FakeRepo(_existing())

    async def fake_chat_json(messages, **kwargs):
        assert kwargs.get("reasoning_effort") == "low"
        return {"ops": [
            {"op": "add", "type": "guide", "content": "先给结论再展开"},
            {"op": "update", "id": 1, "content": "报价默认按国产化平台配"},
        ]}

    import app.services.llm_client as llm_client
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    monkeypatch.setattr(llm_client, "chat_json", fake_chat_json)
    asyncio.run(svc.extract_and_reconcile("support_engineer", "张三", "以后按国产化配", "好的"))
    contents = {r["content"] for r in repo.rows.values()}
    assert "先给结论再展开" in contents
    assert "报价默认按国产化平台配" in contents


def test_extract_and_reconcile_swallows_llm_failure(monkeypatch):
    repo = FakeRepo(_existing())

    async def boom(messages, **kwargs):
        raise RuntimeError("LLM down")

    import app.services.llm_client as llm_client
    monkeypatch.setattr(svc, "ColleagueMemoryRepository", lambda: repo)
    monkeypatch.setattr(llm_client, "chat_json", boom)
    asyncio.run(svc.extract_and_reconcile("support_engineer", "张三", "x", "y"))  # 不抛
    assert len(repo.rows) == 2
