"""启用定向钻取工具（open_part / open_row / open_category / grep_parts）的节点工具迁移
（2026-09-10，幂等，只增不减）。

背景：kp_reason 的检索侧原先只有「精确检索」（query_parts），没有「点开看」——
模型要看全某一颗料的规格、回看某一行当前状态与其已找到的候选、看某个类目到底有哪些字段、
或拿一个型号词在库里定位，唯一手段都是**再发一次广搜**。Mistral Agentic Search 的对照实验
指出：这种 repeated broad search 既费 token 又降准确率，定向钻取（open/navigate/read/grep）
才是质量与效率的双升点。

四个工具都是**只读**：零去库写入、不登记新料号、不放宽 select_parts 白名单。
  open_part     打开一颗已检索到的料，看全规格（read 类比）
  open_row      回看某一行待选型行的状态与其已检索候选（read 类比）
  open_category 看某个类目的字段画像与取值样例，把猜字段变成看字段（navigate 类比）
  grep_parts    拿一个词扫全库，看它出现在哪颗料/哪个字段（grep 类比）

动作（幂等，可重复执行）：
  A. rules.reasoning_node_default（requirement_analysis）kp_reason 行：
     enabled_tools 追加上述四个工具；只改这一个键，其余键原样保留。
  B. active 流的 rules.reasoning_node_config kp_reason 行：只有该行**自己显式配了**
     enabled_tools 时才追加（没配就是继承默认契约，改默认即可，不动它）。

注意：这两个工具**不是**机制保底工具（skill_plan_runtime.MECHANISM_TOOLS），
所以必须在 enabled_tools 里显式列出才会挂载给大脑；画布抽屉里可以随时取消勾选。
"""
import json
import sys

import sqlalchemy as sa

ENG = sa.create_engine(
    "postgresql+psycopg2://postgres:961216@localhost:5432/cpq_platform",
    connect_args={"client_encoding": "UTF8"},
)

SKILL_KEY = "requirement_analysis"
NODE_KEY = "kp_reason"
NEW_TOOLS = ("open_part", "open_row", "open_category", "grep_parts")


def _enabled(cfg: dict) -> list:
    raw = cfg.get("enabled_tools")
    return [str(x) for x in raw] if isinstance(raw, list) else []


def _with_new_tools(cfg: dict) -> tuple:
    """返回 (新配置, 追加了哪些工具)；已是全集则原样返回。"""
    cur = _enabled(cfg)
    add = [t for t in NEW_TOOLS if t not in cur]
    if not add:
        return cfg, []
    out = dict(cfg)
    out["enabled_tools"] = cur + add
    return out, add


def main() -> int:
    changed = 0
    with ENG.begin() as c:
        # A. 默认契约行
        row = c.execute(sa.text(
            "SELECT id, config FROM rules.reasoning_node_default "
            "WHERE skill_key=:s AND node_key=:k"), {"s": SKILL_KEY, "k": NODE_KEY}).first()
        if row is None:
            print(f"[default] {NODE_KEY}: 行不存在，跳过（新库由 skill_config_bootstrap 播种）")
        else:
            cfg = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
            new_cfg, add = _with_new_tools(cfg)
            if add:
                c.execute(sa.text(
                    "UPDATE rules.reasoning_node_default SET config=:cfg, updated_by='migrate-enable-open-tools' "
                    "WHERE id=:i"), {"cfg": json.dumps(new_cfg, ensure_ascii=False), "i": row[0]})
                changed += 1
                print(f"[default] {NODE_KEY}: 追加 {add} -> {_enabled(new_cfg)}")
            else:
                print(f"[default] {NODE_KEY}: 已含 {list(NEW_TOOLS)}，不动")

        # B. active 流的节点实例配置（仅在它自己显式配了工具集时才动）
        flow = c.execute(sa.text(
            "SELECT id FROM rules.reasoning_flow "
            "WHERE skill_key=:s AND is_active ORDER BY id DESC LIMIT 1"), {"s": SKILL_KEY}).first()
        if flow is None:
            print("[config] 没有 active 流，跳过")
        else:
            rows = c.execute(sa.text(
                "SELECT node_key, config FROM rules.reasoning_node_config WHERE flow_id=:f"),
                {"f": flow[0]}).fetchall()
            for node_key, raw in rows:
                if node_key != NODE_KEY:
                    continue
                cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
                if not _enabled(cfg):
                    print(f"[config] flow={flow[0]} {node_key}: 未自配 enabled_tools（继承默认契约），不动")
                    continue
                new_cfg, add = _with_new_tools(cfg)
                if add:
                    c.execute(sa.text(
                        "UPDATE rules.reasoning_node_config SET config=:cfg, updated_by='migrate-enable-open-tools' "
                        "WHERE flow_id=:f AND node_key=:k"),
                        {"cfg": json.dumps(new_cfg, ensure_ascii=False), "f": flow[0], "k": node_key})
                    changed += 1
                    print(f"[config] flow={flow[0]} {node_key}: 追加 {add} -> {_enabled(new_cfg)}")
                else:
                    print(f"[config] flow={flow[0]} {node_key}: 已含 {list(NEW_TOOLS)}，不动")
    print(f"DONE changed={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
