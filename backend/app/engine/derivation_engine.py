"""推导引擎（DerivationEngine）— 纯算法，不碰数据库。

输入：配置状态（kp_lines 带 part 信息、gpu_arch、base_config 盘位等）+ 规则参数（由 repo 从
rules.derivation_rules 表读出后注入）。输出：各步推导结果 + 约束校验警告。

业务规则来源：4 份真实报价单 + STEP BY STEP 文件 + 用户确认（见 docs/服务器页改造-落地设计.md）。
所有阈值/分组数/单卡线数都从 self.rules 读，引擎只执行、不写死。
"""
from typing import List, Dict, Optional, Any


class DerivationEngine:
    def __init__(self, rules: Dict[str, Any] = None):
        self.rules = rules or {}

    def _rule(self, key: str, default: Dict = None) -> Dict:
        return self.rules.get(key, default if default is not None else {})

    # ---------- 聚合辅助 ----------
    def _drive_kinds(self, kp_lines: List[Dict]) -> Dict[str, int]:
        """按硬盘 kind 聚合数量"""
        kinds: Dict[str, int] = {}
        for l in kp_lines:
            if l.get("cat") != "drive":
                continue
            part = l.get("part") or {}
            k = part.get("kind") or part.get("sub_type")
            if k:
                kinds[k] = kinds.get(k, 0) + l.get("qty", 1)
        return kinds

    def _power_parts(self, kp_lines: List[Dict]):
        """返回 (cpu功耗, gpu功耗)"""
        cpu_p = gpu_p = 0
        for l in kp_lines:
            part = l.get("part") or {}
            tdp = part.get("tdp")
            if tdp is None:
                tdp = (part.get("specs") or {}).get("tdp", 0)
            try:
                tdp = float(tdp)
            except (TypeError, ValueError):
                tdp = 0
            if l.get("cat") == "cpu":
                cpu_p += tdp * l.get("qty", 1)
            elif l.get("cat") == "gpu":
                gpu_p += tdp * l.get("qty", 1)
        return cpu_p, gpu_p

    def gpu_count(self, kp_lines: List[Dict]) -> int:
        return sum(l.get("qty", 1) for l in kp_lines if l.get("cat") == "gpu")

    # ---------- 推导 ----------
    def derive_bp_type(self, kp_lines: List[Dict]) -> str:
        """背板类型：含机械盘(SATA/SAS)→tri，纯 NVMe/无盘→dc"""
        cfg = self._rule("bp_type", {"mech_kinds": ["SATA", "SAS"], "tri": "tri", "dc": "dc"})
        mech = cfg.get("mech_kinds", ["SATA", "SAS"])
        kinds = self._drive_kinds(kp_lines)
        has_mech = any(k in mech for k in kinds)
        return cfg.get("tri", "tri") if has_mech else cfg.get("dc", "dc")

    def calc_power(self, kp_lines: List[Dict]) -> Dict:
        """整机峰值功耗分解 = 基础 + CPU + GPU"""
        base = self._rule("base_power", {"watts": 500}).get("watts", 500)
        cpu_p, gpu_p = self._power_parts(kp_lines)
        total = base + cpu_p + gpu_p
        return {"total": total, "base": base, "cpu": cpu_p, "gpu": gpu_p}

    def derive_psu(self, kp_lines: List[Dict], psu_options: List[Dict] = None) -> Dict:
        """电源：功耗定数量(>阈值→4，≤→2)，冗余定单路承担，选最小满足瓦数档"""
        power_info = self.calc_power(kp_lines)
        power = power_info["total"]
        cfg = self._rule("psu_qty_threshold", {"watts": 4800, "qty_low": 2, "qty_high": 4})
        qty = cfg.get("qty_high", 4) if power > cfg.get("watts", 4800) else cfg.get("qty_low", 2)
        # 1+1：单路扛全部；2+2：每路(2个)扛全部 → 单路需 power 或 power/2
        need = power if qty == 2 else power / 2
        chosen = None
        if psu_options:
            for opt in sorted(psu_options, key=lambda x: x.get("wattage", 0)):
                if opt.get("wattage", 0) >= need:
                    chosen = opt
                    break
            if not chosen:
                chosen = max(psu_options, key=lambda x: x.get("wattage", 0))
        return {"power": power_info, "qty": qty, "need_wattage": need, "psu": chosen}

    def derive_front_cables(self, kp_lines: List[Dict]) -> List[Dict]:
        """前面板线缆：每种硬盘 ÷ 每组盘数（SATA/SAS÷8、NVMe÷2）"""
        groups = self._rule("cable_group", {"SATA": 8, "SAS": 8, "NVMe": 2})
        kinds = self._drive_kinds(kp_lines)
        out = []
        for kind, n in kinds.items():
            g = groups.get(kind, 8)
            out.append({"kind": kind, "drive_count": n, "group_size": g,
                        "qty": max(0, -(-n // g))})  # 向上取整
        return out

    def derive_gpu_cables(self, kp_lines: List[Dict]) -> Dict:
        """GPU 供电线：Σ 卡数 × 单卡线数（按显卡型号绑定）"""
        per = self._rule("gpu_cable_per", {"per_model": {}}).get("per_model", {})
        total = 0
        detail = []
        for l in kp_lines:
            if l.get("cat") != "gpu":
                continue
            part = l.get("part") or {}
            model = part.get("sub_type") or part.get("name", "")
            cables = part.get("cables_per") or 1  # specs 里可直接带 cables_per
            if cables == 1:  # 否则按规则表匹配型号
                for mk, mv in per.items():
                    if mk.lower() in (model or "").lower():
                        cables = mv
                        break
            total += cables * l.get("qty", 1)
            detail.append({"model": model, "qty": l.get("qty", 1), "per": cables})
        return {"total": total, "detail": detail}

    def switch_extra(self, gpu_arch: str, gpu_count: int = 8) -> List[Dict]:
        """Switch 架构额外料号（NVSwitch 板 + NVLink 铜缆）
        返回料号列表，每个料号包含 pn, name, qty, price
        """
        if gpu_arch != "switch":
            return []
        # 从规则中读取料号类别
        categories = self._rule("switch_extra_parts", {"add_pn_category": ["NVSwitch", "NVLink"]}).get(
            "add_pn_category", ["NVSwitch", "NVLink"])
        # 这里返回类别列表，实际料号由 derive.py 从 parts_master 查询
        return [{"category": cat, "gpu_count": gpu_count} for cat in categories]

    # ---------- 约束校验 ----------
    def check_switch(self, gpu_arch: str, kp_lines: List[Dict]) -> Optional[str]:
        """Switch 必须 8 卡全互联"""
        if gpu_arch != "switch":
            return None
        req = self._rule("switch_constraint", {"gpu_required": 8}).get("gpu_required", 8)
        n = self.gpu_count(kp_lines)
        if n != req:
            return f"Switch 架构需 {req} 卡全互联，当前 {n} 卡"
        return None

    def check_bays(self, bp_part_specs: Dict, config_bays: int) -> Optional[str]:
        """背板盘位须与底盘盘位一致"""
        bp_bays = bp_part_specs.get("bays") if bp_part_specs else None
        if bp_bays and config_bays and bp_bays != config_bays:
            return f"背板盘位({bp_bays})与底盘({config_bays})不符"
        return None

    # ---------- 汇总 ----------
    def derive_all(self, state: Dict) -> Dict:
        kp = state.get("kp_lines", [])
        arch = state.get("gpu_arch", "none")
        gpu_count = self.gpu_count(kp)
        warnings = [w for w in [self.check_switch(arch, kp)] if w]
        return {
            "bp_type": self.derive_bp_type(kp),
            "power": self.calc_power(kp),
            "psu": self.derive_psu(kp, state.get("psu_options")),
            "front_cables": self.derive_front_cables(kp),
            "gpu_cables": self.derive_gpu_cables(kp),
            "switch_extra": self.switch_extra(arch, gpu_count),
            "warnings": warnings,
        }
