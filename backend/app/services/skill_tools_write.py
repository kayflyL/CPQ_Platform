# -*- coding: utf-8 -*-
"""skill_tools_write —— 写操作工具的聊天适配层（方案助手/同事的写操作工具）。

业务实现的唯一出处是 delivery_core（与页面同源直调路由函数本体）；本层是聊天语义
的薄壳，只做四件事：
1. 身份注入：TOOL_CTX.user（fail-closed）与 TOOL_CTX.price_ok 门；
2. 商机自然标识解析（显式 id > customer_name > 会话绑定，委托 delivery_core）；
3. 高危动作两阶段确认（agent_write_confirm，会话语义——工作流侧走暂停/确认卡，两轨不混）；
4. 结果摘要与人话指引（模型只读摘要）。

纪律：业务规则只许住在 delivery_core——本层出现第二套业务逻辑即为返工。
"""
from __future__ import annotations

from typing import Any, Optional

from app.services import delivery_core as dcore

_COST_SHEET_EXTS = dcore.COST_SHEET_EXTS
_CATEGORY_FOLDER = dcore.CATEGORY_FOLDER


# ── 上下文与公共小件 ─────────────────────────────────────────────────────


def _ctx() -> dict:
    from app.services.skill_tool_context import TOOL_CTX
    ctx = TOOL_CTX.get()
    return ctx if isinstance(ctx, dict) else {}


def _require_user() -> dict:
    """操作身份 fail-closed：拿不到完整用户 dict（含 role）一律拒绝。"""
    user = _ctx().get("user")
    return user if isinstance(user, dict) and user.get("user_id") else {}


def _err(message: str, **extra: Any) -> dict:
    return {"ok": False, "error": message, **extra}


def _consume_pending(tool: str) -> None:
    """写动作执行成功后销待确认记录；失败不销——重试直达放行，
    不再出现"失败一次就永远只出预览"的死循环（2026-10-22 实锤）。"""
    from app.services.agent_write_confirm import consume
    consume(str(_ctx().get("thread_id") or ""), tool)


def _confirm_gate(args: dict, tool: str, preview: dict):
    """两阶段确认门。→ (gate, staged_args)：

    - 无 confirm → stage 落待确认记录，返回 (needs_confirmation 卡, None)；
    - confirm=true → agent_write_confirm.resolve_confirmed 裁决：
        通过 → (None, staged_args)——**执行参数以预览为准**（用户批准的是 staged 那份，
        大脑重放参数漂移不进落库值）；调用方必须用 staged 的字段执行；
        stage 后无新用户消息 → (错误卡, None)：确认必须来自用户在预览之后真实说过的话，
        防大脑同回合自问自答吃掉确认（2026-10-22 实锤）；
        无 pending/过期 → (错误, None)，错误带 staged_args 供自纠。"""
    from app.services.agent_write_confirm import resolve_confirmed, stage, staged_args
    thread_id = str(_ctx().get("thread_id") or "")
    if not args.get("confirm"):
        stage(thread_id, tool, args, preview)
        return {"needs_confirmation": True, "preview": preview}, None
    ok, staged, note = resolve_confirmed(thread_id, tool, args)
    if ok:
        return None, (staged or {})
    if note == "confirm_not_from_user":
        # 用户还没说话（stage 后无新消息）：确认卡已就绪，等用户点选即可——
        # 明确禁止大脑重新出预览（再出一次就是用户看到的"重复确认"）
        out = _err("预览与确认卡已就绪：请等待用户在卡片上点选确认，不要重新出预览或重调工具",
                   status="confirm_not_from_user")
        prev = staged_args(thread_id, tool)
        if prev:
            out["staged_args"] = prev
        return out, None
    # 抢跑自愈：大脑带 confirm=true 却没有待确认记录（陈述跑在闸前面——上一段节点
    # 就把"请在卡片确认"说完了，轮到本步直接补 confirm；或旧记录过期）→ 原地降级
    # 为出预览出卡，绝不执行。预览不可绕过的性质不变：执行仍要求 stage 之后有
    # 真实用户消息（2026-10-22 实锤：报错了事=用户等一张永远不来的卡）。
    stage(thread_id, tool, args, preview)
    return {"needs_confirmation": True, "preview": preview,
            "note": "按预览流程走（此前未出过预览，本次先出确认卡）"}, None


def _resolve_opp(user: dict, args: dict):
    """商机定位（聊天语义）：委托核心解析，会话绑定商机作为兜底。"""
    return dcore.resolve_opportunity(
        user, opportunity_id=str(args.get("opportunity_id") or ""),
        customer_name=str(args.get("customer_name") or ""),
        fallback_opp_id=str(_ctx().get("opportunity_id") or ""))


# ── 1. create_opportunity ────────────────────────────────────────────────


def tool_create_opportunity(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝创建商机")
    customer = str(args.get("customer_name") or "").strip()
    if not customer:
        return _err("customer_name 缺失：用对话里客户明确说出的名称")
    sales_person = str(args.get("sales_person") or "").strip()
    # 归属必填：契约驱动（identify 节点目标层 fields.sales_person.ask，默认必填）。
    # ask=true 且非 business 角色缺归属 → 先要姓名（避免确认后改参数的双确认死循环）；
    # 配置者关掉 ask → 检查消失，建档按页面同源规则走（非 business 缺归属由路由层兜底报错）。
    fields = _ctx().get("step_fields") or []
    sales_ask = next((bool(f.get("ask")) for f in fields
                      if isinstance(f, dict) and str(f.get("key")) == "sales_person"), True)
    if sales_ask and user.get("role") != "business" and not sales_person:
        return {"ok": False, "needs_input": True, "missing": ["sales_person"],
                "error": "缺少归属业务：这个商机归属给哪位业务同事？拿到姓名后连同 customer_name 一起调用"}
    # 建档不走两阶段确认：客户/归属是开工单或对话里的明确指令（低风险、可删除），
    # 再问一轮是无意义摩擦（2026-10-18 人工测试定调）。确认闸保留在提交/加价两处。
    result = dcore.create_opportunity(user, customer_name=customer, sales_person=sales_person)
    if not result.get("ok"):
        return result
    # 会话绑定真实商机(real_bound):后续回合的商机兜底、原件归档、草稿全部落这里
    thread_id = str(_ctx().get("thread_id") or "")
    if thread_id:
        from app.repository.assistant_repo import AssistantRepository
        ar = AssistantRepository()
        try:
            ar.update_thread_opportunity_id(thread_id, result["opportunity_id"])
        finally:
            ar.close()
    return {
        "ok": True,
        "opportunity_id": result.get("opportunity_id"),
        "customer_name": customer,
        "note": "商机已创建（归属按角色规则解析；同名客户系统不查重）",
    }


# ── 2. save_requirement_draft ────────────────────────────────────────────


def tool_save_requirement_draft(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝保存需求草稿")
    resolved = _resolve_opp(user, args)
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    text = str(args.get("requirement_text") or "").strip()
    if not text:
        return _err("requirement_text 缺失：填客户需求的原文整理")
    slots = args.get("slots") if isinstance(args.get("slots"), dict) else {}
    result = dcore.save_requirement_draft(
        user, opp_id=opp_id, requirement_text=text, slots=slots)
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "opportunity_id": opp_id,
        "version": result.get("version"),
        "status": result.get("status"),
        "note": "已存为需求草稿（未提交，不影响当前版本；提交在商机详情页需求节点进行）",
    }


# ── 3. import_cost_sheet（解析成本表 / 纯归档，附件跟随商机）──────────────


def tool_import_cost_sheet(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝处理附件")

    from app.api.deps import ensure_opportunity_access, user_has_permission
    resolved = dcore.resolve_opportunity(
        user, opportunity_id=str(args.get("opportunity_id") or ""),
        customer_name=str(args.get("customer_name") or ""),
        fallback_opp_id=str(_ctx().get("opportunity_id") or ""))
    has_target = resolved.get("ok") is True
    opp_id = resolved.get("opportunity_id") if has_target else ""
    # 分流纪律（机制保下限）：识别步只做解析预览（lane 判定），落草稿一律发生在
    # 成本落位节点——step_key 由轮壳注入，大脑再积极也越不过这行（2026-10-22 用户定）。
    # 降级时带 deferred_by_step 声明：调和器把这笔调用记入推迟账本，指针推进到
    # 所属步后原参数重放（R3a）——跨步交接不依赖大脑记得重新调用。
    demoted_by_step = False
    if has_target and str(_ctx().get("step_key") or "") == "identify":
        has_target = False
        opp_id = ""
        demoted_by_step = True

    # ── archive_only：纯归档（不解析）——必须有商机 ──
    if args.get("archive_only"):
        if not has_target:
            return resolved
        try:
            opp = ensure_opportunity_access(opp_id, user)
        except Exception as exc:
            return _err(str(getattr(exc, "detail", exc)), status=getattr(exc, "status_code", 400))
        category = str(args.get("category") or "").strip() or None
        if category and category not in _CATEGORY_FOLDER:
            return _err("category 只支持 " + "/".join(_CATEGORY_FOLDER) + "，或不传（未分类）")
        att, aerr = dcore.pick_attachment(user, opp_id,
                                          attachment_id=str(args.get("attachment_id") or ""),
                                          exts=None)
        if aerr:
            return aerr
        content = dcore.read_attachment_bytes(att)
        if isinstance(content, dict):
            return content
        out = dcore.archive_attachment(user, opp=opp, att=att, content=content,
                                       category=category)
        if not out.get("ok"):
            return out
        return {"ok": True, "attachment_id": att.get("attachment_id"),
                "opportunity_id": opp_id, "category": out.get("category", ""),
                "note": f"附件已归档到商机「{out.get('bucket_label', '未分类')}」桶"}

    if not user_has_permission(user, "action.flow.submit.costing"):
        return _err("当前角色无权编辑成本核算，无法导入成本表")

    att, aerr = dcore.pick_attachment(
        user, opp_id if has_target else None,
        attachment_id=str(args.get("attachment_id") or ""), exts=_COST_SHEET_EXTS)
    if aerr:
        return aerr
    content = dcore.read_attachment_bytes(att)
    if isinstance(content, dict):
        return content
    filename = att.get("original_filename") or "成本表.xlsx"

    overrides = args.get("parse_overrides") if isinstance(args.get("parse_overrides"), dict) else None
    sheet_id = None
    if args.get("sheet_id") not in (None, "", 0):
        try:
            sheet_id = int(args.get("sheet_id"))
        except (TypeError, ValueError):
            return _err("sheet_id 非法：传上次导入返回的数字ID（修正重导时原地更新草稿）")
    if sheet_id and not has_target:
        return _err("sheet_id 原地更新需先指定商机（customer_name 或 opportunity_id）")
    # ── 重导护栏（破坏性写保护，2026-10-22 死循环实锤）：商机已有未归档草稿时，
    # 不带 sheet_id 的重导一律改判——草稿已有人工补价就拒绝（要原地更新带 sheet_id /
    # 确认重置带 reset=true），没补过价就自动原地更新（不另起 -v2 挤掉探针在读的草稿）。
    # 重解析覆盖行数据：用户在产物卡补的价格被抹掉后，缺价闸永远过不去。──
    if has_target and not sheet_id:
        existing = dcore.latest_cost_sheet(opp_id)
        if existing:
            filled = dcore.filled_price_count(existing.get("configs") or [])
            if filled and not args.get("reset"):
                return _err(
                    f"已有成本草稿 sheet_id={existing.get('sheet_id')}（{existing.get('name')}，"
                    f"已填 {filled} 处价格）。重导会覆盖人工补价："
                    "要原地更新价格请带该 sheet_id 重调；确认清空重置请带 reset=true。",
                    status="reimport_guard", sheet_id=existing.get("sheet_id"))
            sheet_id = int(existing.get("sheet_id") or 0) or None

    parsed = dcore.parse_cost_sheet(content, filename, parse_overrides=overrides)
    if not parsed.get("ok"):
        return {k: v for k, v in parsed.items() if k != "parse_result"}

    # ── 抹价护栏：显式 sheet_id 原地更新时，重解析若比现存草稿少填价，必须显式重置 ──
    if has_target and sheet_id:
        existing = dcore.get_cost_sheet(opp_id, sheet_id)
        if existing:
            cur = dcore.filled_price_count(existing.get("configs") or [])
            new = dcore.filled_price_count(parsed.get("configs") or [])
            if cur > new and not args.get("reset"):
                return _err(
                    f"原地更新会丢 {cur - new} 处已填价格（现 {cur} 处 → 重导后 {new} 处）。"
                    "确认清空重置请带 reset=true。",
                    status="wipe_guard")

    # ── 无商机：仅解析预览（零落库零归档）──
    if not has_target:
        out = {
            "ok": True,
            "analysis_only": True,
            "attachment_id": att.get("attachment_id"),
            "configs": parsed["digest"],
            "note": "仅解析预览（未落草稿未归档）",
        }
        if demoted_by_step:
            out["deferred_by_step"] = True
        if overrides:
            out["overrides_applied"] = True
        return out

    # ── 两阶段确认：先看后落（2026-10-22 用户定调——解析结果先出预览等用户点头再落草稿；
    # 无商机=仅解析预览已在上面返回，此闸只拦「带商机落库」这段写动作）──
    sheet_name = dcore.cost_sheet_name(filename)
    cfg_digest = parsed["digest"] or []
    head = "；".join(
        f"{c.get('name')}（{str(c.get('server_model') or '') or '机型未知'}）×{c.get('qty') or 1}"
        for c in cfg_digest[:6])
    gate, staged = _confirm_gate(
        {"attachment_id": str(att.get("attachment_id") or ""),
         "sheet_id": int(sheet_id) if sheet_id else 0,
         "opportunity_id": str(opp_id or ""),
         **({"confirm": True} if args.get("confirm") else {})},
        "import_cost_sheet",
        {"动作": "解析成本表并落草稿（不提交）",
         "附件": filename,
         "成本表名": sheet_name,
         "配置": f"{len(cfg_digest)} 个：{head}",
         "将发生": "生成成本核算草稿 + 原件归档；不会提交、不会通知报价人"})
    if gate:
        return gate
    if staged:
        # 确认执行：一切以 staged（用户看过的预览那份）为准——附件按 staged ID 直取
        # 重新解析（同一文件解析确定一致），大脑重放的参数漂移不进落库值。
        # 执行失败记录保留（成功才消费），重试直达。
        try:
            sheet_id = int(staged.get("sheet_id") or 0) or None
        except (TypeError, ValueError):
            sheet_id = None
        opp_id = str(staged.get("opportunity_id") or opp_id)
        staged_att = str(staged.get("attachment_id") or "")
        if staged_att and staged_att != str(att.get("attachment_id") or ""):
            att, aerr = dcore.pick_attachment(user, opp_id if has_target else None,
                                              attachment_id=staged_att, exts=_COST_SHEET_EXTS)
            if aerr:
                return aerr
            content = dcore.read_attachment_bytes(att)
            if isinstance(content, dict):
                return content
            filename = att.get("original_filename") or "成本表.xlsx"
            overrides = args.get("parse_overrides") if isinstance(args.get("parse_overrides"), dict) else None
            parsed = dcore.parse_cost_sheet(content, filename, parse_overrides=overrides)
            if not parsed.get("ok"):
                return {k: v for k, v in parsed.items() if k != "parse_result"}
            sheet_name = dcore.cost_sheet_name(filename)
            cfg_digest = parsed["digest"] or []

    # ── 落草稿 ──
    saved = dcore.save_cost_draft(user, opp_id, sheet_id,
                                  sheet_name, parsed["configs"])
    if not saved.get("ok"):
        return saved
    _consume_pending("import_cost_sheet")
    # 会话绑定真实商机(real_bound):落位即绑,后续回合的兜底/归档全部指向真实商机
    thread_id = str(_ctx().get("thread_id") or "")
    if thread_id:
        from app.repository.assistant_repo import AssistantRepository
        ar = AssistantRepository()
        try:
            ar.update_thread_opportunity_id(thread_id, opp_id)
        finally:
            ar.close()
    try:
        opp = ensure_opportunity_access(opp_id, user)
    except Exception as exc:
        return _err(str(getattr(exc, "detail", exc)))

    out = {
        "ok": True,
        "sheet_id": saved.get("sheet_id"),
        "sheet_name": saved.get("sheet_name"),
        "attachment_id": att.get("attachment_id"),
        "configs": parsed["digest"],
        "note": "已生成成本核算草稿（未提交）",
    }
    if not att.get("opportunity_id"):
        bound = dcore.bind_staged_to_opportunity(att, opp, content, category="requirement")
        if bound:
            out["archived"] = {"attachment_id": bound.get("attachment_id"), "category": "requirement"}
    if overrides:
        out["overrides_applied"] = True
    return out


# ── 4. submit_cost_sheet（提交 + 转报价草稿，一步到位）────────────────────


def tool_submit_cost_sheet(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝提交成本表")
    resolved = dcore.resolve_opportunity(
        user, opportunity_id=str(args.get("opportunity_id") or ""),
        customer_name=str(args.get("customer_name") or ""),
        fallback_opp_id=str(_ctx().get("opportunity_id") or ""))
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    try:
        sheet_id = int(args.get("sheet_id"))
    except (TypeError, ValueError):
        return _err("sheet_id 缺失或非法：传成本表数字ID（import_cost_sheet 结果里有）")

    from app.repository.flow_repo import FlowRepository
    flow_repo = FlowRepository()
    try:
        sheet = flow_repo.get_cost_sheet(opp_id, sheet_id)
    finally:
        flow_repo.close()
    if not sheet:
        return _err("成本表不存在或不属于该商机")
    if sheet.get("status") != "draft":
        return _err("仅草稿成本表可提交")

    cfgs = sheet.get("configs") or []
    # 闸门摘要用解析后的值（opp_id 而非客户名原文）：大脑重放时在
    # customer_name/opportunity_id 之间漂移不再造成假性失配
    gate, staged = _confirm_gate({"sheet_id": sheet_id, "opportunity_id": opp_id,
                                  **({"confirm": True} if args.get("confirm") else {})},
                                 "submit_cost_sheet", {
        "动作": "提交成本表并转为报价单草稿",
        "成本表": f"{sheet.get('name')}（{len(cfgs)} 个配置）",
        "将发生": ["生成成本口径的报价单草稿", "流程推进到「报价单」节点",
                   "报价节点处理人与商机归属人会收到通知"],
    })
    if gate:
        return gate
    if staged:
        # 执行参数以预览为准（用户批准的那份）；大脑重放漂移不进落库值
        try:
            sheet_id = int(staged.get("sheet_id"))
        except (TypeError, ValueError):
            pass
        opp_id = str(staged.get("opportunity_id") or opp_id)

    result = dcore.submit_and_convert(
        user, opp_id=opp_id, sheet_id=sheet_id,
        assignee_name=str(args.get("assignee_name") or ""))
    if not result.get("ok"):
        return result
    _consume_pending("submit_cost_sheet")
    quotation_id = result.get("quotation_id") or ""
    out = {"ok": True, "sheet_id": sheet_id, "quotation_id": quotation_id,
           "converted": bool(result.get("converted"))}
    if result.get("converted"):
        out["note"] = "成本表已提交并转为报价单草稿"
    else:
        out["note"] = f"成本表已提交（报价草稿 {quotation_id}），但转正式草稿未完成：{result.get('convert_error')}"
    return out


# ── 5. set_quote_margin ──────────────────────────────────────────────────


def tool_set_quote_margin(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝改价")
    if _ctx().get("price_ok") is not True:
        return _err("无价格权限：该同事或当前账号未开通价格访问（price_access），已拒绝改价")
    resolved = dcore.resolve_opportunity(
        user, opportunity_id=str(args.get("opportunity_id") or ""),
        customer_name=str(args.get("customer_name") or ""),
        fallback_opp_id=str(_ctx().get("opportunity_id") or ""))
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    try:
        margin = float(args.get("margin_pct"))
    except (TypeError, ValueError):
        return _err("margin_pct 缺失或非法：传加价率百分数（如 15 表示加价 15%）")
    if not -100 < margin <= 500:
        return _err("margin_pct 超出合理范围 (-100, 500]")
    apply_to = str(args.get("apply_to") or "kp+l6").strip()
    if apply_to not in ("kp", "l6", "kp+l6"):
        return _err("apply_to 只支持 kp / l6 / kp+l6")

    q = dcore.margin_resolve_quotation(
        user, opp_id=opp_id, quotation_id=str(args.get("quotation_id") or ""))
    if not q.get("ok"):
        return q
    quotation_id = q["quotation_id"]

    # 预览段（零写入；confirm 分支不算预览，过闸消费待确认记录——与 submit 同形，
    # 机制上保证没出过预览就带 confirm=true 首调会被拒，预览不可绕过）
    if not args.get("confirm"):
        preview = dcore.margin_preview(user, opp_id=opp_id, quotation_id=quotation_id,
                                       margin=margin, apply_to=apply_to, price_ok=True)
        if not preview.get("ok"):
            return preview
        _ver = str(q.get("version") or "1").lstrip("vV") or "1"
        preview = {
            "报价单": f"{q.get('quotation_name')}（{quotation_id} v{_ver}）",
            "加价率": f"{margin:g}%（范围：{apply_to}）",
            # ok 是工具结果标志不是预览字段，别让它进确认卡
            **{k: v for k, v in preview.items() if k != "ok"},
        }
    else:
        preview = {}
    # 闸门摘要用解析后的值（quotation_id 而非商机命名原文）：重放参数漂移不再造成假性失配
    gate_args = {"quotation_id": quotation_id, "margin_pct": margin, "apply_to": apply_to,
                 **({"confirm": True} if args.get("confirm") else {})}
    gate, staged = _confirm_gate(gate_args, "set_quote_margin", preview)
    if gate:
        return gate
    if staged:
        # 执行参数以预览为准（用户批准的那份）；大脑重放漂移不进落库值
        try:
            margin = float(staged.get("margin_pct"))
        except (TypeError, ValueError):
            pass
        apply_to = str(staged.get("apply_to") or apply_to)
        quotation_id = str(staged.get("quotation_id") or quotation_id)

    result = dcore.margin_execute(user, opp_id=opp_id, quotation_id=quotation_id,
                                  margin=margin, apply_to=apply_to, price_ok=True)
    if not result.get("ok"):
        return result
    _consume_pending("set_quote_margin")
    return {
        "ok": True,
        "quotation_id": quotation_id,
        "margin_pct": margin,
        "saved_items": result.get("saved_items"),
        "totals": result.get("totals"),
        "note": ("加价已保存：Key Parts 行加价率与各配置 L6 加价率已更新，"
                 "final_price/整单快照按报价工作台同口径重算"),
    }


# ── 6. share_quote ───────────────────────────────────────────────────────


def tool_share_quote(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝创建分享")
    resolved = dcore.resolve_opportunity(
        user, opportunity_id=str(args.get("opportunity_id") or ""),
        customer_name=str(args.get("customer_name") or ""),
        fallback_opp_id=str(_ctx().get("opportunity_id") or ""))
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    view = str(args.get("view") or "internal").strip()
    if view == "customer":
        return _err("customer 视角=报价外发，必须走外发审批闸（商机详情页发起审批，总监批准），AI 不代办")
    if view not in ("scheme", "internal", "cost"):
        return _err("view 只支持 scheme / internal / cost")

    result = dcore.share_quote(
        user, opp_id=opp_id, quotation_id=str(args.get("quotation_id") or ""),
        view=view, expiry_days=args.get("expiry_days"))
    if not result.get("ok"):
        return result
    return {
        "ok": True,
        "quotation_id": result.get("quotation_id"),
        "view": result.get("view"),
        "share_path": result.get("share_path"),
        "expiry_days": result.get("expiry_days"),
        "note": "分享链接已生成（免登录、可过期、可撤销，文件已归档到商机附件）；customer 视角外发始终走人审闸",
    }

# ── 7. import_bom_scheme（方案表落位：不要求价格列）──────────────────────


def tool_import_bom_scheme(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝落位方案表")
    # 分流纪律：识别步只判定（import_cost_sheet 解析预览零落库，结构解析两表通用、
    # 价格列为空即方案表），方案落位发生在「方案落位」节点（2026-10-22 用户定）
    if str(_ctx().get("step_key") or "") == "identify":
        return _err("识别步只做分流判定：改用 import_cost_sheet 做解析预览（零落库）；"
                    "方案落位在「方案落位」节点执行", status="preview_only_step")
    resolved = _resolve_opp(user, args)
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    result = dcore.import_bom_scheme(
        user, opp_id, attachment_id=str(args.get("attachment_id") or ""))
    if not result.get("ok"):
        return result
    thread_id = str(_ctx().get("thread_id") or "")
    if thread_id:
        from app.repository.assistant_repo import AssistantRepository
        ar = AssistantRepository()
        try:
            ar.update_thread_opportunity_id(thread_id, opp_id)
        finally:
            ar.close()
    out = {
        "ok": True,
        "bom_scheme_id": result.get("bom_scheme_id"),
        "scheme_name": result.get("scheme_name"),
        "configs": result.get("configs"),
        "note": result.get("note"),
    }
    if result.get("archived"):
        out["archived"] = result["archived"]
    return out


# ── 8. derive_cost_from_scheme（方案表 → 成本表，库价填充）───────────────


def tool_derive_cost_from_scheme(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝推导成本表")
    resolved = _resolve_opp(user, args)
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    result = dcore.derive_cost_from_scheme(
        user, opp_id, bom_scheme_id=str(args.get("bom_scheme_id") or ""))
    if not result.get("ok"):
        return result
    thread_id = str(_ctx().get("thread_id") or "")
    if thread_id:
        from app.repository.assistant_repo import AssistantRepository
        ar = AssistantRepository()
        try:
            ar.update_thread_opportunity_id(thread_id, opp_id)
        finally:
            ar.close()
    return {
        "ok": True,
        "sheet_id": result.get("sheet_id"),
        "sheet_name": result.get("sheet_name"),
        "bom_scheme_id": result.get("bom_scheme_id"),
        "configs": result.get("configs"),
        "note": result.get("note"),
    }


# ── 9. set_cost_prices（缺价补充：聊天回价 → 回写成本草稿行）─────────────


def tool_set_cost_prices(args: dict) -> dict:
    user = _require_user()
    if not user:
        return _err("无法确定操作身份，拒绝补价")
    resolved = _resolve_opp(user, args)
    if not resolved.get("ok"):
        return resolved
    opp_id = resolved["opportunity_id"]
    prices = args.get("prices")
    if not isinstance(prices, list) or not prices:
        return _err("prices 缺失：L6 整价传 [{config_name, l6_price}]；KP 逐行传 "
                    "[{config_name, catalogue, base_price}]")
    sheet_id = None
    if args.get("sheet_id") not in (None, "", 0):
        try:
            sheet_id = int(args.get("sheet_id"))
        except (TypeError, ValueError):
            return _err("sheet_id 非法：传成本表数字ID（import_cost_sheet 结果里有）")
    return dcore.set_cost_prices(user, opp_id, sheet_id, prices)


# ── 10. ask_user_card（会话输入卡：大脑定时机与内容，系统保证弹出与渲染）──


def tool_ask_user(args: dict) -> dict:
    """向人提问（human-as-tool）：载荷即问题的形状（options→单选卡 / fields→表单卡），
    渲染与存在性由 human_query 协议保证——大脑描述问题，不选模板。用户回答后
    结构化回流对话。无存证语义（写动作的授权走确认闸，不经本工具）。"""
    if not _require_user():
        return _err("无法确定操作身份，拒绝提问")
    from app.services import human_query as hq
    options_raw = args.get("options") if isinstance(args.get("options"), list) else None
    fields_raw = args.get("fields") if isinstance(args.get("fields"), list) else None
    kind, err = hq.validate_payload(args.get("title"), options_raw, fields_raw)
    if err:
        return _err(err)
    options = None
    if options_raw:
        options = [{"label": str(o.get("label") or "").strip()[:60],
                    "description": str(o.get("description") or "").strip()[:120],
                    "recommended": bool(o.get("recommended"))}
                   for o in options_raw if isinstance(o, dict) and str(o.get("label") or "").strip()]
        options.sort(key=lambda o: not o["recommended"])  # 推荐项机械置首
        recommended = [o["label"] for o in options if o["recommended"]]
        if len(recommended) > 1:
            return _err("recommended 只能标一个：推荐是引导，不是多选")
    fields = None
    if fields_raw:
        fields = [{"key": str(f["key"]).strip()[:40],
                   "label": str(f.get("label") or f["key"]).strip()[:60],
                   "placeholder": str(f.get("placeholder") or "")[:80],
                   "type": str(f.get("type") or "text")}
                  for f in fields_raw if isinstance(f, dict) and str(f.get("key") or "").strip()]
    title = str(args.get("title") or "").strip()[:60]
    hint = str(args.get("hint") or "")[:200]
    return {"ok": True,
            "user_query": {"kind": kind, "title": title, "hint": hint,
                           "options": options, "fields": fields},
            "await_user": True,
            "note": f"问题已就绪：{title}（等用户回答）"}
