"""Compatibility rule repository — 兼容性规则引擎 CRUD + seed（schema=rules）。

照 requirement_rule_repo 模式。声明式 WHEN→THEN 规则，type:
require/exclude/derive/filter/recommend。seed_default_if_empty 幂等，由 startup 自动触发。
"""
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.base import Rules_SessionLocal
from app.models.compatibility_rule import CompatibilityRule


# 选型配置默认规则（声明式 WHEN→THEN）。CRE 规则是线缆/背板/筛选的「唯一真相源」（拒绝黑盒：
# 数量计算方式在选型配置页可视化、可配、改即生效）。
#
# 寻址：ctx.kp 聚合 KP 配件库件（GPU/CPU/Memory/HDD-SSD…，按 kp_categories 英文名）；
#   ctx.config 暴露盘类型计数 config.sata_qty / sas_qty / nvme_qty、盘类型集合 config.drive_kinds、
#   config.bp_type。规则只产出「某类型线缆要几根」的数量，
#   target 取线缆类型标签（SATA/SAS/NVMe/GPU线），消费端（L6ChassisConfig）据此填步进器默认值——
#   具体选哪根 PN 是用户的事，规则不碰料号库。手改数量优先于规则默认（推导仅兜底）。
DEFAULT_RULES: list[dict] = [
    # ① derive（赋值型）：配置含 NVMe 盘 → 背板类型=tri。tri-mode 支持 SATA/SAS/NVMe 三协议、
    #    dc 直连只走 SATA/SAS——故含 NVMe 盘必须 tri；纯 SATA/SAS 或无盘 → dc
    #    （消费端 bpType() ?? 'dc' 兜底，不 seed dc 规则——CRE 无 not-contains）。
    {"type": "derive", "status": "active", "name": "背板类型：含 NVMe 盘→三模",
     "body": {"when": {"field": "config.drive_kinds", "op": "contains", "value": "NVMe"},
              "then": {"action": "derive", "field": "config.bp_type", "value": "tri"},
              "desc": "配置含 NVMe 盘 → 三模(tri)背板（tri 支持 SATA/SAS/NVMe）；纯 SATA/SAS 或无盘 → dc 直连兜底"}},
    # ②③④ 前面板线缆：按硬盘类型各算各的，盘数 ÷ 每组盘数 向上取整。
    #    盘数走 config.sata_qty/sas_qty/nvme_qty（消费端按盘类型分别聚合，不再用全盘总量）。
    {"type": "derive", "status": "active", "name": "SATA 线缆根数",
     "body": {"when": {"field": "config.sata_qty", "op": ">=", "value": 1},
              "then": {"action": "derive", "target": "SATA", "basis": "config.sata_qty", "per": 8, "round": "ceil"},
              "desc": "SATA 盘数 ÷ 8（向上取整）= SATA 线缆根数；改 per 即改每组盘数"}},
    {"type": "derive", "status": "active", "name": "SAS 线缆根数",
     "body": {"when": {"field": "config.sas_qty", "op": ">=", "value": 1},
              "then": {"action": "derive", "target": "SAS", "basis": "config.sas_qty", "per": 8, "round": "ceil"},
              "desc": "SAS 盘数 ÷ 8（向上取整）= SAS 线缆根数；改 per 即改每组盘数"}},
    {"type": "derive", "status": "active", "name": "NVMe 线缆根数",
     "body": {"when": {"field": "config.nvme_qty", "op": ">=", "value": 1},
              "then": {"action": "derive", "target": "NVMe", "basis": "config.nvme_qty", "per": 2, "round": "ceil"},
              "desc": "NVMe 盘数 ÷ 2（向上取整）= NVMe 线缆根数；改 per 即改每组盘数"}},
    # ⑤ GPU 供电线：每张 GPU 配 1 根（per=1，改 per 可调成每 N 卡 1 根）
    {"type": "derive", "status": "active", "name": "GPU 供电线根数",
     "body": {"when": {"field": "kp.GPU.qty", "op": ">=", "value": 1},
              "then": {"action": "derive", "target": "GPU线", "basis": "kp.GPU.qty", "per": 1, "round": "ceil"},
              "desc": "GPU 数量 ÷ 1（向上取整）= GPU 供电线根数；改 per 即改每 N 卡 1 根"}},
]


class CompatibilityRuleRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    # ===== 规则 CRUD =====
    def list(self, type: Optional[str] = None, status: Optional[str] = None,
             domain: str = "selection") -> List[dict]:
        q = self.session.query(CompatibilityRule)
        if domain:
            q = q.filter(CompatibilityRule.domain == domain)
        if type:
            q = q.filter(CompatibilityRule.type == type)
        if status:
            q = q.filter(CompatibilityRule.status == status)
        q = q.order_by(CompatibilityRule.type, CompatibilityRule.id)
        return [r.to_dict() for r in q.all()]

    def list_by_type(self, rule_type: str, status: str = "active") -> List[dict]:
        """执行器读取用：某 type 的生效规则（body 已解析）。"""
        return self.list(type=rule_type, status=status)

    def get(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        return r.to_dict() if r else None

    def create(self, data: dict, operator: str = "system") -> dict:
        now = datetime.now().isoformat()
        body = data.get("body")
        scope = data.get("scope")
        rule = CompatibilityRule(
            domain=data.get("domain", "selection"),
            type=data["type"],
            name=data["name"],
            scope=json.dumps(scope, ensure_ascii=False) if scope else None,
            body=json.dumps(body, ensure_ascii=False) if body is not None else "{}",
            status=data.get("status", "active"),
            version=1,
            hit_count=0,
            change_reason=data.get("change_reason"),
            description=data.get("description"),
            created_at=now,
            updated_at=now,
            created_by=operator,
            updated_by=operator,
        )
        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule.to_dict()

    def update(self, rule_id: int, data: dict, operator: str = "system") -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        now = datetime.now().isoformat()
        for k in ("type", "name", "status", "change_reason", "description"):
            if k in data and data[k] is not None:
                setattr(r, k, data[k])
        if "scope" in data:
            r.scope = json.dumps(data["scope"], ensure_ascii=False) if data["scope"] else None
        if "body" in data:
            r.body = json.dumps(data["body"], ensure_ascii=False) if data["body"] is not None else "{}"
        r.version = (r.version or 1) + 1
        r.updated_at = now
        r.updated_by = operator
        self.session.commit()
        self.session.refresh(r)
        return r.to_dict()

    def set_status(self, rule_id: int, status: str, operator: str = "system") -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        r.status = status
        r.updated_at = datetime.now().isoformat()
        r.updated_by = operator
        self.session.commit()
        return r.to_dict()

    def delete(self, rule_id: int) -> bool:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return False
        self.session.delete(r)
        self.session.commit()
        return True

    # ===== 命中计数（越跑越聪明） =====
    def record_hit(self, rule_id: int) -> Optional[dict]:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return None
        r.hit_count = (r.hit_count or 0) + 1
        r.last_hit_at = datetime.now().isoformat()
        self.session.commit()
        self.session.refresh(r)
        return {"id": r.id, "hit_count": r.hit_count, "last_hit_at": r.last_hit_at}

    def stats(self, rule_id: int) -> dict:
        r = self.session.query(CompatibilityRule).filter(CompatibilityRule.id == rule_id).first()
        if not r:
            return {"hit_count": 0, "last_hit_at": None}
        return {"hit_count": r.hit_count or 0, "last_hit_at": r.last_hit_at}

    def reset_to_defaults(self) -> int:
        """清空并重新 seed 默认规则（规则迭代后让用户一键更新到最新 seed）。"""
        try:
            self.session.query(CompatibilityRule).delete()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.seed_default_if_empty()

    # ===== Seed =====
    def seed_default_if_empty(self) -> int:
        existing = self.session.query(CompatibilityRule).count()
        if existing > 0:
            return 0
        now = datetime.now().isoformat()
        for item in DEFAULT_RULES:
            self.session.add(CompatibilityRule(
                domain="selection",
                type=item["type"],
                name=item["name"],
                body=json.dumps(item["body"], ensure_ascii=False),
                status=item.get("status", "active"),
                version=1,
                hit_count=0,
                created_at=now,
                updated_at=now,
                created_by="seed",
                updated_by="seed",
            ))
        self.session.commit()
        return len(DEFAULT_RULES)

    def close(self):
        self.session.close()
