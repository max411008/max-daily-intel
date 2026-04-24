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
- title_zh: 繁體中文翻譯過的標題（簡潔有力，≤ 40 字，若原文已中文就原樣回）
- analysis: 繁體中文 2-3 句摘要（第一句發生什麼、第二句為何重要、第三句選用行動建議）
- summary_zh: 繁體中文翻譯過的原文內文（≤ 300 字），不是分析而是把原 summary 翻成中文。若原文是中文就原樣回
- tags: 2-4 個繁體中文標籤（如「地緣政治」「央行」「AI」「半導體」等）

**全部欄位一律繁體中文**，不要留英文原句。專有名詞（公司名/人名/地名）可保留英文但需在括號加中文註，例：「Bitcoin (比特幣)」「Powell (鮑威爾)」。

輸出**純 JSON**，格式：
{{
  "crypto": [{{"idx": 0, "title_zh": "...", "analysis": "...", "summary_zh": "...", "tags": ["...", "..."]}}, ...],
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

    # 2026-04-24 fix-daily-intel-missing: on any claude-CLI failure (non-zero,
    # timeout, empty stdout, or JSON parse error), fall back to raw English
    # articles so generate_report.py still produces a card (degraded but alive).
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "sonnet", "--permission-mode", "bypassPermissions"],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("[analyze] claude failed after 300s — falling back to raw untranslated articles", file=sys.stderr)
        return _fallback_raw(raw)

    if result.returncode != 0:
        print(f"[analyze] claude returned {result.returncode}: {result.stderr[:500]} — falling back to raw untranslated articles", file=sys.stderr)
        return _fallback_raw(raw)

    out = result.stdout.strip()
    if not out:
        print("[analyze] claude produced empty stdout — falling back to raw untranslated articles", file=sys.stderr)
        return _fallback_raw(raw)

    # strip ```json fences if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", out, re.DOTALL)
    if m:
        out = m.group(1)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        print(f"[analyze] claude output not valid JSON ({e}) — falling back to raw untranslated articles", file=sys.stderr)
        return _fallback_raw(raw)


def _fallback_raw(raw):
    """Degraded fallback: emit up to 2 articles per sector using English title/summary
    as if they were pre-translated. generate_report.py only reads the enrich dict for
    idx → title_zh/summary_zh/analysis/tags, so supply those with English content."""
    fallback = {}
    for sect, info in raw.items():
        arts = info.get("articles", []) or []
        picks = []
        for i, a in enumerate(arts[:2]):
            title_en = a.get("title", "") or ""
            summary_en = re.sub(r"<[^>]+>", "", (a.get("summary") or ""))[:400]
            picks.append({
                "idx": i,
                "title_zh": title_en,
                "analysis": "(claude-CLI unavailable — raw English article; 翻譯服務暫停)",
                "summary_zh": summary_en,
                "tags": ["fallback", "untranslated"],
            })
        fallback[sect] = picks
    return fallback


def main():
    raw = json.load(sys.stdin)
    # Sort each sector's raw articles by published DESC before analyzing (newest first).
    for sect, info in raw.items():
        arts = info.get("articles", []) or []
        arts.sort(key=lambda a: a.get("published") or a.get("published_at") or "", reverse=True)
        info["articles"] = arts
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
            if pick.get("title_zh"):
                a["title_zh"] = pick["title_zh"]
            if pick.get("summary_zh"):
                a["summary_zh"] = pick["summary_zh"]
            a["analysis"] = pick.get("analysis", "")
            a["tags"] = pick.get("tags", [])
            # Overwrite raw English summary so no downstream code can leak it.
            # Keep original under a debug field in case needed.
            if pick.get("summary_zh"):
                a["_summary_en_raw"] = a.get("summary", "")
                a["summary"] = pick["summary_zh"]
            new_arts.append(a)
        # Keep newest first in final output too (picks preserve analyzer order; resort)
        new_arts.sort(key=lambda a: a.get("published") or a.get("published_at") or "", reverse=True)
        out[sect] = {"label": info.get("label", sect), "articles": new_arts}
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
