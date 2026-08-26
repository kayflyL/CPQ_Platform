# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "repository", "reasoning_flow_repo.py")
text = io.open(path, encoding="utf-8").read()

start_anchor = "    def self_heal_agent_node_configs(self, flow_id: Optional[int] = None) -> int:"
end_anchor = "    def activate(self, flow_id: int, operator: str = \"system\") -> Optional[dict]:"
i = text.index(start_anchor)
j = text.index(end_anchor, i)
old = text[i:j]

new = '''    def self_heal_agent_node_configs(self, flow_id: Optional[int] = None) -> int:
        """自愈节点配置：仅对 requirement_analysis 生效，主链集合从默认配置动态取。

        不再写死旧六节点集合；非 requirement_analysis 技能不做删除/新建，避免误伤。
        只补缺失字段，不覆盖用户已保存的 enabled/system_prompt/label 等值。
        """
        query = self.session.query(ReasoningFlow).filter(ReasoningFlow.is_active == True)
        if flow_id is not None:
            query = query.filter(ReasoningFlow.id == flow_id)
        f = query.first()
        if not f:
            return 0
        is_ra = str(f.skill_key or f.name or "") == "requirement_analysis"
        if not is_ra:
            return 0
        defaults = _requirement_analysis_node_configs()
        canonical = set(defaults.keys())
        changed = 0

        for n in self.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == f.id
        ).all():
            if n.node_key not in canonical:
                self.session.delete(n)
                changed += 1
        if changed:
            self.session.commit()

        for node_key in canonical:
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if n:
                continue
            default = dict(defaults.get(node_key) or {})
            ptype = _prompt_node_type(node_key)
            if ptype:
                try:
                    from app.services.prompt_store import merge_node_prompt
                    default = merge_node_prompt(ptype, default)
                except Exception:
                    pass
            self.upsert_node_config(f.id, node_key, default, operator="self-heal")
            changed += 1

        for node_key in canonical:
            n = self.session.query(ReasoningNodeConfig).filter(
                ReasoningNodeConfig.flow_id == f.id,
                ReasoningNodeConfig.node_key == node_key,
            ).first()
            if not n:
                continue
            try:
                cfg = json.loads(n.config) if n.config else {}
            except Exception:
                cfg = {}
            default = defaults.get(node_key) or {}
            dirty = False
            for k, v in default.items():
                if k in ("description", "system_prompt"):
                    continue
                if isinstance(v, dict):
                    if isinstance(cfg.get(k), dict) and not cfg[k]:
                        cfg[k] = dict(v)
                        dirty = True
                    elif cfg.get(k) is None:
                        cfg[k] = dict(v)
                        dirty = True
                elif isinstance(v, list):
                    if cfg.get(k) in (None, []):
                        cfg[k] = list(v)
                        dirty = True
                else:
                    if cfg.get(k) is None:
                        cfg[k] = v
                        dirty = True
            if dirty:
                n.config = json.dumps(cfg, ensure_ascii=False)
                n.updated_at = datetime.now().isoformat()
                n.updated_by = "self-heal"
                changed += 1
        if changed:
            self.session.commit()
        return changed

'''
text = text[:i] + new + text[j:]
io.open(path, "w", encoding="utf-8").write(text)
print("self_heal rewritten OK", len(new))
