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


# P1 默认规则（声明式 WHEN→THEN）。category 名以 DB kp.kp_categories.name 为准（2026-07-29 已核对，
# 实际为英文且仅 10 个：Network(NIC) requirement / HDD/SSD / GPU / CPU / Memory / Raid card /
# Bridge / HBA / NVSwitch / GPU card）。
#
# ⚠️ 重要边界：CRE 的 ctx 只聚合 cfg.items 里 category='Key Parts' 的件（见 Workspace.buildRuleContext），
#   即只有上列 KP category 能被 kp.<cat>.* 寻址。线缆/背板/电源等件在料号库 l6.parts_master（中文
#   category：GPU电源线/背板/电源/前面板线缆...），**不进 CRE 寻址空间**——这类功耗/线缆/背板约束
#   由后端 DerivationEngine 承担（derive_gpu_cables / derive_bp_type）。因此 ③④ 的 target 当前
#   寻址不到，标 status=testing 保留业务意图但不假装生效；待 ctx 扩展纳入料号库件后再激活。
DEFAULT_RULES: list[dict] = [
    # ① filter：商机平台 → 候选机型过滤（不依赖 category 名，最稳；验证 filter 动作）
    {"type": "filter", "status": "active", "name": "按商机平台过滤候选机型",
     "body": {"when": {"field": "opportunity.platform_type", "op": "exists"},
              "then": {"action": "filter", "scope": "server_model", "field": "series",
                       "op": "==", "value": "opportunity.platform_type"},
              "desc": "商机信息栏选了平台类型（如 Polaris），工作台/server config 只出现该系列机型"}},
    # ② exclude：内存同型号不混搭（Memory 为 kp_categories 真实 category；ctx.items.pn 由消费端从 oem_sku enrich）
    {"type": "exclude", "status": "active", "name": "内存同型号不混搭",
     "body": {"when": {"field": "kp.Memory.qty", "op": ">=", "value": 2},
              "then": {"action": "exclude", "target": "kp.Memory", "unique_field": "pn"},
              "desc": "配置内 ≥2 条内存时必须同型号（pn 唯一），禁止混用不同速率/容量"}},
    # ③ require：选 GPU → 必配 GPU 电源线（用户业务例①）
    #    testing：GPU 电源线在料号库 parts_master(category='GPU电源线')，不进 CRE kp.* 寻址；
    #    约束已由后端 DerivationEngine.derive_gpu_cables 承担。保留为 require 范例。
    {"type": "require", "status": "testing", "name": "选 GPU 需配 GPU 电源线（待 ctx 扩展）",
     "body": {"when": {"field": "kp.GPU.qty", "op": ">=", "value": 1},
              "then": {"action": "require", "target": "kp.GPU电源线", "min_qty": "kp.GPU.qty"},
              "desc": "[当前不生效] GPU 电源线属料号库件，不在 CRE 的 KP 寻址空间；已由后端 gpu_cables 推导承担。保留为范例"}},
    # ④ require(specs)：NVMe 盘 → tri-mode 背板
    #    testing：背板在料号库 parts_master(category='背板')，不进 CRE kp.* 寻址；
    #    背板类型由 DerivationEngine.derive_bp_type 推导。保留为 spec_constraint 范例。
    {"type": "require", "status": "testing", "name": "NVMe 盘需配 tri-mode 背板（待 ctx 扩展）",
     "body": {"when": {"field": "kp.HDD/SSD.spec.interface", "op": "==", "value": "NVMe"},
              "then": {"action": "require", "target": "kp.背板", "spec_constraint": {"support": "tri-mode"}},
              "desc": "[当前不生效] 背板属料号库件，不在 CRE 的 KP 寻址空间；背板类型已由后端推导承担。保留为范例"}},
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
