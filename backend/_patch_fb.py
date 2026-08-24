# -*- coding: utf-8 -*-
import io
FN = "app/services/agent_react.py"
s = io.open(FN, encoding="utf-8").read()

OLD = '''        data: Optional[dict] = None
        if text:
            try:
                candidate = llm_client._parse_json_content(text)
                if isinstance(candidate, dict):
                    data = candidate
            except Exception:
                data = None
        return text, think, data'''

NEW = '''        data: Optional[dict] = None
        if text:
            try:
                candidate = llm_client._parse_json_content(text)
                if isinstance(candidate, dict):
                    data = candidate
            except Exception:
                data = None
        # 兜底：流式正文不是 JSON 时，用一次 chat_json 强制结构化（保证收敛，不静默失败）
        if data is None:
            try:
                data = await llm_client.chat_json(messages, model=model)
            except llm_client.LLMError:
                data = None
        return text, think, data'''

if OLD in s:
    s = s.replace(OLD, NEW, 1)
    io.open(FN, "w", encoding="utf-8").write(s)
    print("FALLBACK_OK")
else:
    print("FALLBACK_SKIP")
