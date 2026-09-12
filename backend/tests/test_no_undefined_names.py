# -*- coding: utf-8 -*-
"""全量扫描：函数里读到、但既非模块级定义也非内建的全局名 —— 运行到才会炸的 NameError。

历史事故（2026-09-10）：点击通路用了未导入的 `KP_NODE`，参数求值即 NameError，被宽 except
吞掉，整条点击通路静默失效；`_ComposeNode.prepare` 同样漏了一行 `final_gate` 导入。
这类「静态就能看出来」的坑不该再靠实测撞。
"""
import builtins
import os
import symtable
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
BUILTINS = set(dir(builtins))
# 模块级由解释器注入、不进 symtable 全局符号表的名字
INJECTED = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__", "__builtins__"}


def _scan(path, out):
    import io
    src = io.open(path, encoding="utf-8").read()
    top = symtable.symtable(src, path, "exec")
    mod_names = {s.get_name() for s in top.get_symbols()} | INJECTED

    def walk(tbl):
        for child in tbl.get_children():
            if child.get_type() in ("function", "class"):
                for s in child.get_symbols():
                    n = s.get_name()
                    if s.is_global() and s.is_referenced() and n not in mod_names and n not in BUILTINS:
                        out.append((path, n))
            walk(child)

    walk(top)


def test_no_undefined_globals_in_app():
    hits = []
    for dirpath, _dirs, files in os.walk(ROOT):
        for f in files:
            if f.endswith(".py"):
                _scan(os.path.join(dirpath, f), hits)
    assert not hits, "未定义的全局名（运行到即 NameError）：" + "; ".join(
        f"{os.path.relpath(p, ROOT)}::{n}" for p, n in sorted(set(hits)))
