"""spec_compliance / audit_fix 节点单测（v12：规格合规校验 + 审计自纠）。"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

from app.services.capabilities import (
    run_spec_compliance, run_audit_fix, _req_cpu_tokens, _memory_upgrade_target,
)


def _ctx(server_type="AI / 加速计算服务器", kp_parts=None, ext_extra=None):
    ext = {"server_type_name": server_type, "categories": ["CPU", "Memory"],
           **(ext_extra or {})}
    return {"ext": ext, "kp_parts": kp_parts or [], "requirement_text": "",
            "flow_configs": {"llm_ask": {"scale_tiers": {"内存": [
                {"label": "入门", "recommend": "32G*4条"},
                {"label": "标准", "recommend": "32G*8条"},
                {"label": "高配", "recommend": "64G*8条"},
            ]}}}}


def test_spec_compliance_ai_missing_gpu_autofix():
    """AI 类型缺 GPU → auto_fix 追加 GPU 品类并请求重跑链。"""
    ctx = _ctx()
    cfg = {"enabled": True, "mode": "auto_fix", "gpu_required_for_ai": True}
    res = run_spec_compliance(ctx, cfg)
    assert any("GPU" in i for i in res["issues"])
    assert "GPU" in ctx["ext"]["categories"]
    assert res["fixed"] >= 1
    assert "kp_reason" in (ctx.get("retry_caps") or [])


def test_spec_compliance_ai_no_gpu_flag_only():
    """flag_only 模式：只标 issue，不追加品类。"""
    ctx = _ctx()
    cfg = {"enabled": True, "mode": "flag_only", "gpu_required_for_ai": True}
    res = run_spec_compliance(ctx, cfg)
    assert any("GPU" in i for i in res["issues"])
    assert "GPU" not in ctx["ext"]["categories"]
    assert not ctx.get("retry_caps")


def test_spec_compliance_cpu_model_mismatch_flags():
    """需求指定 EPYC 9654，实配 9124 → 标 issue（不自动造件）。"""
    ctx = _ctx(server_type="通用计算服务器", kp_parts=[
        {"category": "CPU", "name": "AMD EPYC 9124", "description": "AMD EPYC 9124"},
        {"category": "Memory", "name": "16G DDR5", "description": "16G DDR5 4800"},
    ])
    ctx["requirement_text"] = "双路 AMD EPYC 9654，内存 32G*8"
    cfg = {"enabled": True, "mode": "auto_fix", "gpu_required_for_ai": False}
    res = run_spec_compliance(ctx, cfg)
    assert any("9654" in i and "9124" in i for i in res["issues"])


def test_req_cpu_tokens():
    assert "EPYC9654" in _req_cpu_tokens("双路 AMD EPYC 9654")
    assert "KH50000" in _req_cpu_tokens("KH50000 处理器")
    assert _req_cpu_tokens("没有CPU型号") == []


def test_audit_fix_memory_insufficient_bumps_and_retries():
    """审计说内存不足 → 抬到标准档总量并请求重跑。"""
    ctx = _ctx()
    ctx["llm_audits"] = [{"issues": ["内存仅 1×16GB，远低于中型数据库所需内存容量"]}]
    cfg = {"enabled": True, "max_retry": 1}
    res = run_audit_fix(ctx, cfg)
    assert res["retry"] is True
    assert ctx["ext"]["mem_signal"]["total_gb"] == 256  # 32G*8条 标准档
    assert "kp_reason" in (ctx.get("retry_caps") or [])


def test_audit_fix_retry_capped():
    """重跑一次后仍有问题 → 不再重试（交 review 人工复核）。"""
    ctx = _ctx()
    ctx["llm_audits"] = [{"issues": ["内存不足"]}]
    ctx["audit_retry_count"] = 1
    cfg = {"enabled": True, "max_retry": 1}
    res = run_audit_fix(ctx, cfg)
    assert res["retry"] is False
    assert res["reason"] == "retry_capped"


def test_audit_fix_no_issues_no_retry():
    ctx = _ctx()
    ctx["llm_audits"] = []
    res = run_audit_fix(ctx, {"enabled": True, "max_retry": 1})
    assert res["retry"] is False


def test_memory_upgrade_target_from_scale_tiers():
    ctx = _ctx()
    assert _memory_upgrade_target(ctx, {}) == 256  # 优先「标准」档 32G*8条 = 256
