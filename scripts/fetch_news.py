#!/usr/bin/env python3
"""MAX Daily Intel — RSS News Fetcher
Fetches news from 5 sectors: Crypto, Gold, Stocks, AI, Dev/Ideas
"""

import feedparser
import json
import sys
import argparse
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Volumes/DATA/mac-offload/Projects/hydra-v3")
from utils.robust_fetch import robust_fetch_feed

TZ_TAIPEI = timezone(timedelta(hours=8))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

# 2026-04-16 audit (dispatch news-scraper-all-failing): 移除 5 個死掉的 feed
# (Kitco/cnyes/工商時報/MoneyDJ/Anthropic Blog 全 404/403/SSL fail)；WSJ 換 dowjones 新 endpoint
FEEDS = {
    "crypto": [
        {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
        {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    ],
    "gold": [
        {"name": "ForexLive", "url": "https://www.forexlive.com/feed/news"},
    ],
    "tw_stocks": [
        {"name": "經濟日報", "url": "https://money.udn.com/rssfeed/news/1001/5590?ch=money"},
    ],
    "us_stocks": [
        {"name": "WSJ Markets", "url": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"},
        {"name": "MarketWatch", "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
    ],
    "ai": [
        {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
        {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
        {"name": "Ars Technica AI", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    ],
    "dev": [
        {"name": "Hacker News Best", "url": "https://hnrss.org/best?q=AI+OR+claude+OR+LLM+OR+agent&count=20"},
        {"name": "Product Hunt", "url": "https://www.producthunt.com/feed"},
    ],
}

SECTOR_LABELS = {
    "crypto": "Crypto / DeFi",
    "gold": "Gold / Commodities",
    "tw_stocks": "台股",
    "us_stocks": "美股",
    "ai": "AI Industry",
    "dev": "Dev Tools & Ideas",
}


def parse_date(entry):
    """Extract published date from feed entry."""
    for field in ["published_parsed", "updated_parsed"]:
        parsed = getattr(entry, field, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def fetch_feed(feed_info):
    """Fetch and parse a single RSS feed via robust_fetch_feed (retry + UA rotation + Discord alert)."""
    articles = []
    try:
        res = robust_fetch_feed(feed_info["url"], label=feed_info["name"], max_retries=3, base_timeout=12)
        feed = res.parsed if res.ok else None
        if feed is None:
            print(f"[WARN] robust_fetch_feed failed for {feed_info['name']}: {res.error}", file=sys.stderr)
            return articles
        for entry in feed.entries[:15]:
            pub_date = parse_date(entry)
            summary = entry.get("summary", entry.get("description", ""))
            if summary:
                summary = summary[:500]
            articles.append({
                "source": feed_info["name"],
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": summary,
                "published": pub_date.isoformat() if pub_date else None,
            })
    except Exception as e:
        print(f"[WARN] Failed to fetch {feed_info['name']}: {e}", file=sys.stderr)
    return articles


def filter_by_date(articles, target_date):
    """Filter articles by strict target date (Taipei timezone, legacy path)."""
    filtered = []
    for a in articles:
        if not a["published"]:
            continue
        try:
            pub = datetime.fromisoformat(a["published"])
            pub_taipei = pub.astimezone(TZ_TAIPEI).date()
            if pub_taipei == target_date:
                filtered.append(a)
        except Exception:
            continue
    return filtered


def filter_by_window(articles, window_hours):
    """Filter articles by rolling N-hour window back from now (Taipei TZ).

    2026-04-18 fix-daily-intel-twstock-empty: strict-date filter (filter_by_date)
    was losing items from fast-rotating feeds like UDN money (20-slot RSS,
    rotates every ~12h). By 06:53 cron-fire, yesterday's TW articles are
    already flushed → tw_stocks bucket returned 0. Rolling window catches
    items from both "yesterday's leftovers" and "today's new" so the bucket
    stays populated as long as the feed has *anything* fresh in the last N
    hours. Items without a parseable pubDate are skipped (cannot window-check).
    """
    cutoff = datetime.now(TZ_TAIPEI) - timedelta(hours=window_hours)
    filtered = []
    for a in articles:
        if not a["published"]:
            continue
        try:
            pub = datetime.fromisoformat(a["published"]).astimezone(TZ_TAIPEI)
            if pub >= cutoff:
                filtered.append(a)
        except Exception:
            continue
    return filtered


def fetch_all(target_date=None, window_hours=None):
    """Fetch news from all sectors.

    Filter mode precedence:
      - target_date (strict YYYY-MM-DD match) — legacy, for --date / --today
      - window_hours (rolling N-hour window from now) — preferred for daily cron
      - neither → no filter (--all)
    """
    result = {}
    summary = {}
    for sector, feeds in FEEDS.items():
        sector_articles = []
        source_counts = {}
        for feed_info in feeds:
            articles = fetch_feed(feed_info)
            raw_count = len(articles)
            if target_date is not None:
                articles = filter_by_date(articles, target_date)
            elif window_hours is not None:
                articles = filter_by_window(articles, window_hours)
            source_counts[feed_info["name"]] = {"raw": raw_count, "kept": len(articles)}
            sector_articles.extend(articles)
        # Sort by date descending
        sector_articles.sort(
            key=lambda a: a.get("published") or "", reverse=True
        )
        result[sector] = {
            "label": SECTOR_LABELS[sector],
            "articles": sector_articles,
        }
        summary[sector] = {"count": len(sector_articles), "sources": source_counts}
    # Emit structured monitoring log line (machine-readable, per-sector + per-source)
    log_line = {
        "ts": datetime.now(TZ_TAIPEI).isoformat(timespec="seconds"),
        "mode": "strict" if target_date is not None else ("window" if window_hours else "all"),
        "target_date": target_date.isoformat() if target_date else None,
        "window_hours": window_hours,
        "sector_counts": {s: summary[s]["count"] for s in summary},
        "source_detail": {s: summary[s]["sources"] for s in summary},
    }
    try:
        log_path = os.path.expanduser("~/Library/Logs/daily-intel-twstock.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(log_line, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] failed to write monitoring log: {e}", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description="MAX Daily Intel RSS Fetcher")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (strict, legacy)")
    parser.add_argument("--today", action="store_true", help="Fetch today's news (strict)")
    parser.add_argument("--all", action="store_true", help="Fetch all without date filter")
    parser.add_argument(
        "--window-hours",
        type=int,
        default=36,
        help="Rolling window in hours back from now (default 36). Ignored if --date/--today/--all.",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # 2026-04-18 default changed from "yesterday (strict)" to "last 36h
    # rolling window" — fast-rotating feeds like UDN money were losing
    # yesterday's items by cron-fire time, leaving tw_stocks empty.
    target_date = None
    window_hours = None
    if args.all:
        pass
    elif args.today:
        target_date = datetime.now(TZ_TAIPEI).date()
    elif args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        window_hours = args.window_hours

    data = fetch_all(target_date=target_date, window_hours=window_hours)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if target_date:
            date_str = target_date.strftime("%Y-%m-%d")
        elif window_hours:
            date_str = f"last {window_hours}h"
        else:
            date_str = "ALL"
        print(f"MAX Daily Intel — {date_str}")
        print("=" * 50)
        for sector, info in data.items():
            print(f"\n{'='*3} {info['label']} {'='*3}")
            if not info["articles"]:
                print("  (no articles found)")
                continue
            for i, a in enumerate(info["articles"][:5], 1):
                print(f"  {i}. [{a['source']}] {a['title']}")
                if a["link"]:
                    print(f"     {a['link']}")

    # Summary stats
    total = sum(len(v["articles"]) for v in data.values())
    print(f"\nTotal articles: {total}", file=sys.stderr)


if __name__ == "__main__":
    main()
