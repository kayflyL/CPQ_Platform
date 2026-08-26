# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()

helper = r'''def _extract_json_object(text: str) -> Optional[dict]:
    """从 final answer 里抽取 JSON 对象（允许前后有说明文字）。"""
    if not text:
        return None
    t = str(text).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except Exception:
        pass
    s = t.find("{")
    e = t.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            v = json.loads(t[s:e + 1])
            return v if isinstance(v, dict) else None
        except Exception:
            return None
    return None


'''
anchor = "def _dig_path(obj: Any, dotted: str, default: Optional[Any] = None):"
assert anchor in text
text = text.replace(anchor, helper + anchor, 1)

old_parse = '''    structured: Optional[dict] = None
    if answer:
        try:
            parsed = json.loads(answer)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            structured = parsed'''
new_parse = '''    structured: Optional[dict] = None
    if answer:
        parsed = _extract_json_object(answer)
        if isinstance(parsed, dict):
            structured = parsed'''
assert old_parse in text, "parse anchor missing"
text = text.replace(old_parse, new_parse, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("json extract patched OK")
