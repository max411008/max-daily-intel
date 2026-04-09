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
    """Add new issue to index.html."""
    index_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'index.html')
    with open(index_path, 'r') as f:
        content = f.read()

    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y/%m/%d (%a)")
    new_entry = f'    <li><a href="{date_str}.html"><span class="date">{date_display}</span><div class="meta">{total_articles} articles</div></a></li>\n    <!-- ISSUES_LIST -->'

    content = content.replace('<!-- ISSUES_LIST -->', new_entry)

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
