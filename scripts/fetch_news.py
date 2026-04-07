#!/usr/bin/env python3
"""MAX Daily Intel — RSS News Fetcher
Fetches news from 5 sectors: Crypto, Gold, Stocks, AI, Dev/Ideas
"""

import feedparser
import json
import sys
import argparse
from datetime import datetime, timedelta, timezone

TZ_TAIPEI = timezone(timedelta(hours=8))

FEEDS = {
    "crypto": [
        {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
        {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
        {"name": "CoinTelegraph", "url": "https://cointelegraph.com/rss"},
    ],
    "gold": [
        {"name": "Kitco News", "url": "https://www.kitco.com/feed/news"},
        {"name": "ForexLive", "url": "https://www.forexlive.com/feed/news"},
    ],
    "stocks": [
        {"name": "WSJ Markets", "url": "https://feeds.wsj.net/wsj/xml/rss/3_7014.xml"},
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
        {"name": "Anthropic Blog", "url": "https://www.anthropic.com/rss.xml"},
    ],
}

SECTOR_LABELS = {
    "crypto": "Crypto / DeFi",
    "gold": "Gold / Commodities",
    "stocks": "Stocks / Macro",
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
    """Fetch and parse a single RSS feed."""
    articles = []
    try:
        feed = feedparser.parse(feed_info["url"])
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
    """Filter articles by target date (Taipei timezone)."""
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


def fetch_all(target_date=None):
    """Fetch news from all sectors, optionally filtered by date."""
    result = {}
    for sector, feeds in FEEDS.items():
        sector_articles = []
        for feed_info in feeds:
            articles = fetch_feed(feed_info)
            if target_date:
                articles = filter_by_date(articles, target_date)
            sector_articles.extend(articles)
        # Sort by date descending
        sector_articles.sort(
            key=lambda a: a.get("published") or "", reverse=True
        )
        result[sector] = {
            "label": SECTOR_LABELS[sector],
            "articles": sector_articles,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description="MAX Daily Intel RSS Fetcher")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--today", action="store_true", help="Fetch today's news")
    parser.add_argument("--all", action="store_true", help="Fetch all without date filter")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.all:
        target_date = None
    elif args.today:
        target_date = datetime.now(TZ_TAIPEI).date()
    elif args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = (datetime.now(TZ_TAIPEI) - timedelta(days=1)).date()

    data = fetch_all(target_date)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        date_str = target_date.strftime("%Y-%m-%d") if target_date else "ALL"
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
