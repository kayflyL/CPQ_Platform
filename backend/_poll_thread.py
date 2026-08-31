# -*- coding: utf-8 -*-
"""临时：轮询最新助手线程的消息（测完与 _e2e_skill.py 一起删）。"""
import sys

from sqlalchemy import create_engine, text

eng = create_engine("postgresql://postgres:961216@localhost:5432/cpq_platform",
                    connect_args={"client_encoding": "UTF8"})
tid_arg = sys.argv[1] if len(sys.argv) > 1 else None
with eng.connect() as c:
    if tid_arg:
        tid = tid_arg
    else:
        row = c.execute(text(
            "select thread_id from opportunities.assistant_threads order by created_at desc limit 1")).fetchone()
        if not row:
            print("no threads")
            sys.exit(0)
        tid = row[0]
    print("thread:", tid)
    ms = c.execute(text(
        "select role, kind, left(coalesce(content,''),110), created_at, left(coalesce(data,''),400) "
        "from opportunities.assistant_messages where thread_id=:t order by created_at asc, seq asc"), {"t": tid}).fetchall()
    for m in ms:
        print(f"[{str(m[3])[11:19]}|{str(m[0])[:4]}|{str(m[1] or 'text')[:15]}] {m[2]}")
        if m[1] == "input_options" and m[4]:
            print("    card:", m[4][:360])
