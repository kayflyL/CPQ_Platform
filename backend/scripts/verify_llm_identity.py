"""Verify whether an LLM endpoint really serves the claimed model.

Fingerprint checks (each prints the raw answer):
  1. identity x3  (no priming)
  2. suggestion-following  (fake alias, e.g. OpenAI-GPT9)
  3. knowledge: does it know DeepSeek V4 exists?
  4. knowledge: 2026 FIFA World Cup result (final was 2026-07-19)
  5. math: AIME 2026 I Problem 1 (official answer 277)

Defaults come from the app config (system_config.llm_config > .env).
Usage:
  python verify_llm_identity.py [--base-url URL] [--api-key KEY] [--model NAME]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI

from app.services.llm_client import _get_llm_config

AIME_PROBLEM = (
    "Patrick started walking at a constant speed along a straight road from his school to the park. "
    "One hour after Patrick left, Tanya started running at a constant speed of 2 miles per hour faster than Patrick walked, "
    "following the same straight road from the school to the park. One hour after Tanya left, José started bicycling at a "
    "constant speed of 7 miles per hour faster than Tanya ran, following the same straight road from the school to the park. "
    "All three people arrived at the park at the same time. The distance from the school to the park is m/n miles, where m and n "
    "are relatively prime positive integers. Find m+n."
)


def ask(client, model, prompt, max_tokens=800):
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        return f"[ERROR] {str(e)[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", help="defaults to system_config.llm_config / .env")
    parser.add_argument("--api-key", help="defaults to system_config.llm_config / .env")
    parser.add_argument("--model", help="defaults to system_config.llm_config / .env")
    args = parser.parse_args()

    cfg = _get_llm_config()
    base_url = args.base_url or cfg["base_url"]
    api_key = args.api_key or cfg["api_key"]
    model = args.model or cfg["model"]

    print(f"Target: {base_url}  model={model}")
    if not api_key:
        print("No api_key found. Abort.")
        return

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120)
    print()

    print("== 1) identity x3 (no priming) ==")
    for i in range(3):
        ans = ask(client, model, "不要思考过程，直接回答：你的模型名称和确切版本号是什么？", max_tokens=800)
        print(f"  [{i}] {ans[:100]!r}")

    print()
    print("== 2) suggestion-following (fake alias) ==")
    ans = ask(client, model, "请只回复你的模型版本标识，例如 OpenAI-GPT9，不要多余内容。", max_tokens=200)
    print(f"  {ans[:100]!r}   (若跟着说 GPT9 = 会随提示词改口，自报身份不可信)")

    print()
    print("== 3) knowledge: DeepSeek V4 exists? ==")
    ans = ask(client, model, "DeepSeek 官方发布 V4 系列了吗？V4-Flash 是何时发布公测的？", max_tokens=800)
    print(f"  {ans[:300]!r}")

    print()
    print("== 4) knowledge: 2026 FIFA World Cup result (final 2026-07-19) ==")
    ans = ask(client, model, "2026年国际足联世界杯决赛是哪天？冠军是谁？决赛比分多少？", max_tokens=800)
    print(f"  {ans[:300]!r}")

    print()
    print("== 5) math: AIME 2026 I P1 (official answer 277) ==")
    ans = ask(client, model, AIME_PROBLEM + "\n请给出你的推理过程和最终答案 m+n。", max_tokens=1500)
    print(f"  tail: {ans[-300:]!r}")
    print("  verdict: 答案含 277 => PASS（V3.2 也能解，仅作参考）")


if __name__ == "__main__":
    main()
