#!/usr/bin/env python3
"""Generate HTML daily report from analyzed news data."""

import json
import sys
import os
from datetime import datetime, timezone, timedelta

TZ_TAIPEI = timezone(timedelta(hours=8))

SECTOR_COLORS = {
    "crypto": "#f7931a",
    "gold": "#ffd700",
    "tw_stocks": "#e53935",
    "us_stocks": "#4caf50",
    "ai": "#7c4dff",
    "dev": "#00bcd4",
}

SECTOR_EMOJI = {
    "crypto": "&#x1f4b0;",
    "gold": "&#x1f947;",
    "tw_stocks": "&#x1f1f9;&#x1f1fc;",
    "us_stocks": "&#x1f1fa;&#x1f1f8;",
    "ai": "&#x1f916;",
    "dev": "&#x1f6e0;&#xfe0f;",
}

SECTOR_LABELS_ZH = {
    "crypto": "加密貨幣",
    "gold": "黃金商品",
    "tw_stocks": "台股",
    "us_stocks": "美股",
    "ai": "AI 產業",
    "dev": "開發靈感",
}


def generate_sector_html(sector_id, label, articles, color):
    """Generate HTML for one sector section."""
    emoji = SECTOR_EMOJI.get(sector_id, "")
    label_zh = SECTOR_LABELS_ZH.get(sector_id, label)
    html = f'''
  <section class="sector" id="{sector_id}">
    <div class="sector-header">
      <div class="indicator" style="background:{color}"></div>
      <h2>{emoji} {label_zh}</h2>
      <span class="badge">{len(articles)} 則</span>
    </div>
'''
    if not articles:
        html += '    <div class="empty">今日暫無相關情報</div>\n'
    else:
        for a in articles:
            source = a.get("source", "")
            title = a.get("title", "")
            link = a.get("link", "#")
            summary = a.get("analysis", a.get("summary", ""))
            # Strip HTML tags from summary
            import re
            summary = re.sub(r'<[^>]+>', '', summary)
            if len(summary) > 300:
                summary = summary[:300] + "..."
            tags_html = ""
            if a.get("tags"):
                tags_html = '<div class="tags">' + "".join(
                    f'<span class="tag">{t}</span>' for t in a["tags"]
                ) + '</div>'

            html += f'''    <div class="news-card">
      <div class="source">{source}</div>
      <h3><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>
      <div class="summary">{summary}</div>
      {tags_html}
    </div>
'''
    html += '  </section>\n'
    return html


def generate_report(analyzed_data, date_str):
    """Generate full HTML report."""
    template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'daily-template.html')
    with open(template_path, 'r') as f:
        template = f.read()

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekdays_zh = ['一', '二', '三', '四', '五', '六', '日']
    date_display = f"{dt.year} 年 {dt.month} 月 {dt.day} 日（{weekdays_zh[dt.weekday()]}）"

    sectors_html = ""
    counts = {}
    for sector_id, info in analyzed_data.items():
        articles = info.get("articles", [])
        color = SECTOR_COLORS.get(sector_id, "#666")
        label = info.get("label", sector_id)
        sectors_html += generate_sector_html(sector_id, label, articles, color)
        counts[sector_id] = len(articles)

    html = template
    html = html.replace("{{DATE}}", date_str)
    html = html.replace("{{DATE_DISPLAY}}", date_display)
    html = html.replace("{{SECTORS_HTML}}", sectors_html)
    html = html.replace("{{CRYPTO_COUNT}}", str(counts.get("crypto", 0)))
    html = html.replace("{{GOLD_COUNT}}", str(counts.get("gold", 0)))
    html = html.replace("{{STOCKS_COUNT}}", str(counts.get("stocks", 0)))
    html = html.replace("{{AI_COUNT}}", str(counts.get("ai", 0)))
    html = html.replace("{{DEV_COUNT}}", str(counts.get("dev", 0)))
    total = sum(counts.values())
    html = html.replace("{{TOTAL_COUNT}}", str(total))

    return html


def update_index(date_str, total_articles):
    """Idempotently update index.html: dedupe by date, sort desc, keep card entries intact."""
    import re
    index_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
    with open(index_path, 'r') as f:
        content = f.read()

    # Collect existing entries of form: <li><a href="YYYY-MM-DD.html">... </a></li>
    # (the simple-auto-generated ones; preserve the richer "issue-card" entries which have images)
    simple_pat = re.compile(
        r'\s*<li><a href="(\d{4}-\d{2}-\d{2})\.html"><span class="date">[^<]+</span><div class="meta">\d+ articles</div></a></li>\n?'
    )
    # Build map: date -> total_articles (latest wins); also strip all simple entries from content
    existing = {}
    def collect(m):
        existing[m.group(1)] = None  # placeholder, real count extracted below
        return ''
    # First pass: pull real counts
    for m in simple_pat.finditer(content):
        d = m.group(1)
        count_m = re.search(r'<div class="meta">(\d+) articles</div>', m.group(0))
        if count_m:
            existing[d] = int(count_m.group(1))
    # Strip all simple entries
    content = simple_pat.sub('', content)

    # Upsert the new one
    existing[date_str] = total_articles

    # Detect which dates already have a rich card via existing <a class="issue-card">
    rich_cards = set(re.findall(r'<a class="issue-card" href="(\d{4}-\d{2}-\d{2})\.html"', content))

    # Build sorted (desc) block — emit rich card for each entry. If a card png exists,
    # use it; otherwise inline an SVG gradient placeholder so layout matches.
    weekdays_zh = ['一', '二', '三', '四', '五', '六', '日']
    docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
    entries = []
    for d in sorted(existing.keys(), reverse=True):
        if d in rich_cards:
            continue  # preserve hand-curated rich card already in HTML
        dt = datetime.strptime(d, "%Y-%m-%d")
        display = f"{dt.year}/{dt.month:02d}/{dt.day:02d}（{weekdays_zh[dt.weekday()]}）"
        png_rel = f"cards/{d}.png"
        if os.path.exists(os.path.join(docs_dir, png_rel)):
            img_src = png_rel
        else:
            # Inline SVG placeholder — gradient + emoji + date label
            day_label = f"{dt.month}/{dt.day}"
            svg = (
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 220'>"
                "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
                "<stop offset='0%' stop-color='%23a78bfa'/><stop offset='100%' stop-color='%2322d3ee'/>"
                "</linearGradient></defs>"
                "<rect width='600' height='220' fill='url(%23g)'/>"
                f"<text x='30' y='90' fill='white' font-size='32' font-weight='700' font-family='-apple-system,sans-serif'>MAX Daily Intel</text>"
                f"<text x='30' y='160' fill='white' font-size='72' font-weight='800' font-family='-apple-system,sans-serif'>{day_label}</text>"
                "<text x='30' y='200' fill='rgba(255,255,255,0.9)' font-size='18' font-family='-apple-system,sans-serif'>加密 · 黃金 · 股票 · AI · 開發</text>"
                "</svg>"
            )
            img_src = "data:image/svg+xml;utf8," + svg
        entries.append(
            f'    <li><a class="issue-card" href="{d}.html">'
            f'<img src="{img_src}" alt="{d} 每日情報摘要" loading="lazy">'
            f'<div class="info"><span class="date">{display}</span>'
            f'<span class="meta">{existing[d]} 則情報</span></div>'
            f'</a></li>'
        )
    block = '\n'.join(entries) + '\n    <!-- ISSUES_LIST -->'
    content = content.replace('<!-- ISSUES_LIST -->', block)

    with open(index_path, 'w') as f:
        f.write(content)


if __name__ == "__main__":
    data = json.load(sys.stdin)
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d")

    html = generate_report(data, date_str)

    output_path = os.path.join(os.path.dirname(__file__), '..', 'docs', f'{date_str}.html')
    with open(output_path, 'w') as f:
        f.write(html)

    total = sum(len(v.get("articles", [])) for v in data.values())
    update_index(date_str, total)

    print(f"Generated: docs/{date_str}.html ({total} articles)")
