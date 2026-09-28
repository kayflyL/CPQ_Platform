# -*- coding: utf-8 -*-
"""幽灵指令收尾（2026-09-12）：指令唯一出处 = 左栏 manual_rules。

1) 把节点抽屉/默认契约里仍活的指令增量合并进 flow 125 左栏（规则 13/14/15 扩充 + 新增规则 24）；
2) 清除 reasoning_node_default（requirement_analysis）与 flow 125 node_configs 里的
   指令 prose 键（description / goal / final_contract）——结构键（target/enabled_tools/fields…）不动。

背景：前端抽屉 09-10 起已无指令编辑器，但后端 node_mission 仍读这两层 prose 注入每步
system——UI 不可见、却真实发给模型的「幽灵指令」。本脚本先搬后清（搬走≠删掉）。
trend_analysis（flow 126，遗留 agent 运行时）不属本次范围。
"""
import json
import re
import sys
from datetime import datetime

from sqlalchemy import create_engine, text
from _localdb import db_url  # 2026-09-14 安全加固：密码不再硬编码

FLOW_ID = 125
SKILL_KEY = "requirement_analysis"

RULE_13 = ("13.【登记步】先调 fill_requirement 完成登记（部件进 kp_rows），成功后向客户确认已登记关键项并引出未登记项；"
           "严格按客户原话登记（型号/数量/单位/RAID 级别不改写不丢），硬盘容量必须带单位（如 1.92T）；"
           "客户没提的留空禁止编造；不自行匹配型号（交给选型步骤）；禁止逐项复述登记表。"
           "增量纪律：已登记的字段与部件行不重新推导、不重复登记，本轮只处理客户新增信息或刚确认的选项"
           "（确认后把确认值登记即可），不要既填又追问同一字段；目录字段缺口里优先确认「服务器类型」。")
RULE_14 = ("14.【机型步】候选池就绪，从中选型（choose_model 池内取值），成功后用一两句话向客户说明选定理由（只引用池内字段）；"
           "池外拒绝；无法决断时不要调用工具，说明需要客户确认即可，由系统把选择权交回客户。")
RULE_15 = ("15.【配件步】原文决定覆盖范围，登记表仅作缓存：原文提到的每一类配件都转为选配信号，多个盘组/GPU 组必须逐行列出。"
           "落行按料号名：select_parts 的 picks 填 name（料号名，库里没有业务 part_id），"
           "引擎按「类目+料号名」（忽略大小写/空格差异）回库精确核对——唯一命中才落行、价格取库里最新值；"
           "库内同名料号多命中时未落料、把全部同名行回候选，从候选里确认后重新提交；"
           "零命中回白盒消息，换 keywords/required_specs 再查一次，仍空则该行不锁定、如实说明并调 ask_user 交客户决策，禁止断言库里没有。"
           "料号名取自库内返回原文（query_parts 的 keywords 用库内拉丁型号/厂商词或该行客户登记的具体型号规格词，如 KH50000、DDR5、6T；"
           "规格收窄用 required_specs 如 Type=DDR5、Capacity=6TB），不凭记忆编造；检索时不全类目浏览，中文用途词先换成库内数值/型号词（万兆→10G）。"
           "查之前先用 inspect_parts(action=category) 看该类目有哪些 specs 字段与取值样例（别猜字段名）；"
           "一个词不知落在哪个类目/字段时用 inspect_parts(action=grep) 扫一遍；要看全某颗已命中料用 inspect_parts(action=part)、"
           "回看某一行状态用 inspect_parts(action=row)——四者都只读，锁定候选仍必须走 query_parts。"
           "多行待选时优先用 query_parts(rows=...) 一次批量召回各行候选（每行用自己的类目+行描述去库召回），"
           "批量里零召回的行再单独用 category+required_specs 收窄重查；一次回复可并行带多个工具调用；"
           "每行只检索一次、命中首选，避免逐行逐类串行、反复换词/翻页盲搜。"
           "行清单 specified=true 的行可直接锁定；specified=false 且为必填类目 → 只登记推荐，"
           "并立即调 ask_user 升格选项卡（options 2-4 个、标推荐、一回合一卡）交客户确认，不能当作已锁定、也不能静默丢弃；"
           "问客户时选项要带你查到的库内候选料——选项带 pick（part_id/name，取 query_parts 结果），"
           "客户点选即落地该料号，不要让客户再打字；类目级「不配/自备」的逃生用带 absent 的选项。"
           "组合需求给 qty，近替代带 substitute=true 并写明原需求→替代。"
           "「我查过了」不是交付——每一行必须落到 锁定／交客户确认／如实标注 三者之一，禁止只输出总结。")
RULE_24 = ("24.【收尾步】收尾汇报纪律：向客户汇报需求分析结果时先确认已完成的登记，再说明锁定的机型与理由、"
           "配件落地情况与生成的方案；只引用给定事实；总成本的币种与数值逐字取给定事实（人民币元）；"
           "已落地配件数、未匹配配件数及其类目名与事实完全一致，未匹配的行不得说成已落地；两三句话，面向客户口吻。")

PROSE_KEYS = ("description", "goal", "final_contract")


def _replace_rule(rules_text: str, num: int, new_line: str) -> tuple[str, bool]:
    pat = re.compile(rf"^{num}\..*$", re.M)
    if not pat.search(rules_text):
        return rules_text, False
    return pat.sub(new_line, rules_text, count=1), True


def main() -> int:
    eng = create_engine(
        db_url(),
        connect_args={"client_encoding": "UTF8"},
    )
    now = datetime.now().isoformat()
    with eng.begin() as cn:
        row = cn.execute(
            text("SELECT graph FROM rules.reasoning_flow WHERE id = :fid"), {"fid": FLOW_ID}
        ).fetchone()
        if not row:
            print(f"✖ flow {FLOW_ID} 不存在"); return 1
        g = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        mr = str(g.get("manual_rules") or "")

        changed = []
        for num, line in ((13, RULE_13), (14, RULE_14), (15, RULE_15)):
            mr2, ok = _replace_rule(mr, num, line)
            if ok:
                mr = mr2
                changed.append(num)
        if not re.search(r"^24\.", mr, re.M):
            mr = (mr.rstrip() + "\n" + RULE_24).strip()
            changed.append(24)
        g["manual_rules"] = mr
        cn.execute(
            text("UPDATE rules.reasoning_flow SET graph = cast(:g AS jsonb), updated_at = :t WHERE id = :fid"),
            {"g": json.dumps(g, ensure_ascii=False), "t": now, "fid": FLOW_ID},
        )
        print(f"左栏：规则 {changed} 已合并，共 {len(re.findall(chr(10), mr)) + 1} 行 {len(mr)} 字")

        # 清 flow 125 node_configs 的 prose 键
        rows = cn.execute(
            text("SELECT node_key, config FROM rules.reasoning_node_config WHERE flow_id = :fid"),
            {"fid": FLOW_ID},
        ).fetchall()
        for node_key, cfg_raw in rows:
            cfg = cfg_raw if isinstance(cfg_raw, dict) else json.loads(cfg_raw or "{}")
            hit = [k for k in PROSE_KEYS if k in cfg]
            if not hit:
                continue
            for k in hit:
                cfg.pop(k)
            cn.execute(
                text("UPDATE rules.reasoning_node_config SET config = cast(:c AS jsonb), updated_at = :t "
                     "WHERE flow_id = :fid AND node_key = :nk"),
                {"c": json.dumps(cfg, ensure_ascii=False), "t": now, "fid": FLOW_ID, "nk": node_key},
            )
            print(f"node_config[{FLOW_ID}/{node_key}] 清除 prose 键：{hit}")

        # 清 defaults 的 prose 键（仅 requirement_analysis）
        rows = cn.execute(
            text("SELECT node_key, config FROM rules.reasoning_node_default WHERE skill_key = :sk"),
            {"sk": SKILL_KEY},
        ).fetchall()
        for node_key, cfg_raw in rows:
            cfg = cfg_raw if isinstance(cfg_raw, dict) else json.loads(cfg_raw or "{}")
            hit = [k for k in PROSE_KEYS if k in cfg]
            if not hit:
                continue
            for k in hit:
                cfg.pop(k)
            cn.execute(
                text("UPDATE rules.reasoning_node_default SET config = cast(:c AS jsonb), updated_at = :t, "
                     "updated_by = 'migrate_single_home_20260912' WHERE skill_key = :sk AND node_key = :nk"),
                {"c": json.dumps(cfg, ensure_ascii=False), "t": now, "sk": SKILL_KEY, "nk": node_key},
            )
            print(f"node_default[{node_key}] 清除 prose 键：{hit}")

    # 自检：锚点必须留在左栏
    with eng.connect() as cn:
        row = cn.execute(
            text("SELECT graph FROM rules.reasoning_flow WHERE id = :fid"), {"fid": FLOW_ID}
        ).fetchone()
        g = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        mr = str(g.get("manual_rules") or "")
    for anchor in ("既填又追问", "优先确认「服务器类型」", "收尾汇报纪律", "query_parts",
                   "inspect_parts(action=category)", "specified=false"):
        assert anchor in mr, f"锚点丢失：{anchor}"
    print("锚点自检通过（搬走≠删掉）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
