#!/usr/bin/env python3
"""Analyze fetched news: filter top 1-2 per sector, add Chinese summary + tags via Claude."""
import json
import subprocess
import sys
import re


def analyze_batch(raw):
    """Send all articles to Claude in one call, parse back enriched JSON."""
    candidates = {}
    for sect, info in raw.items():
        arts = info.get("articles", [])[:5]  # cap at 5 per sector for prompt budget
        candidates[sect] = [
            {"idx": i, "title": a.get("title", ""), "source": a.get("source", ""),
             "summary": re.sub(r"<[^>]+>", "", (a.get("summary") or ""))[:400]}
            for i, a in enumerate(arts)
        ]

    prompt = f"""你是 MAX 的首席市場分析師。下面是今日各板塊新聞候選（最多各 5 則）。請為每個板塊挑選 **最多 2 則最重要** 的新聞，並為每則產出：
- analysis: 繁體中文 2-3 句摘要（第一句發生什麼、第二句為何重要、第三句選用行動建議）
- tags: 2-4 個繁體中文標籤（如「地緣政治」「央行」「AI」「半導體」等）

輸出**純 JSON**，格式：
{{
  "crypto": [{{"idx": 0, "analysis": "...", "tags": ["...", "..."]}}, ...],
  "gold": [...],
  "tw_stocks": [...],
  "us_stocks": [...],
  "ai": [...],
  "dev": [...]
}}

如果某板塊完全沒值得報的，回空陣列。只輸出 JSON 不要任何其他文字。

原始候選：
{json.dumps(candidates, ensure_ascii=False, indent=2)}
"""

    result = subprocess.run(
        ["claude", "-p", prompt, "--model", "sonnet", "--permission-mode", "bypassPermissions"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"[analyze] claude failed: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)
    out = result.stdout.strip()
    # strip ```json fences if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", out, re.DOTALL)
    if m:
        out = m.group(1)
    return json.loads(out)


def main():
    raw = json.load(sys.stdin)
    enrich = analyze_batch(raw)

    out = {}
    for sect, info in raw.items():
        picks = enrich.get(sect, [])
        arts_src = info.get("articles", [])
        new_arts = []
        for pick in picks[:2]:
            idx = pick.get("idx")
            if idx is None or idx >= len(arts_src):
                continue
            a = dict(arts_src[idx])
            a["analysis"] = pick.get("analysis", "")
            a["tags"] = pick.get("tags", [])
            new_arts.append(a)
        out[sect] = {"label": info.get("label", sect), "articles": new_arts}
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
