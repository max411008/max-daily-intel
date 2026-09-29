import os
import sys
import unittest
import tempfile
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# 確保在匯入 fetch_news 前隔離外部依賴，避免需要外部套件或外部專案目錄
if "feedparser" not in sys.modules:
    sys.modules["feedparser"] = MagicMock()
if "utils" not in sys.modules:
    sys.modules["utils"] = MagicMock()
if "utils.robust_fetch" not in sys.modules:
    mock_rf_module = MagicMock()
    sys.modules["utils.robust_fetch"] = mock_rf_module
    sys.modules["utils"].robust_fetch = mock_rf_module

# 依規範將 scripts 加入 sys.path 並以頂層名稱匯入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_news


class TestFetchNews(unittest.TestCase):
    def test_parse_date_precedence_and_fallback(self):
        """測試 parse_date：published_parsed 優先、退回 updated_parsed、無有效日期回傳 None"""
        # 1. 正常 published_parsed
        entry_pub = MagicMock()
        entry_pub.published_parsed = (2026, 4, 18, 10, 30, 0, 0, 0, 0)
        entry_pub.updated_parsed = (2026, 4, 18, 11, 0, 0, 0, 0, 0)
        dt = fetch_news.parse_date(entry_pub)
        self.assertEqual(dt, datetime(2026, 4, 18, 10, 30, 0, tzinfo=timezone.utc))

        # 2. 只有 updated_parsed (published_parsed 為 None)
        entry_upd = MagicMock()
        entry_upd.published_parsed = None
        entry_upd.updated_parsed = (2026, 4, 18, 12, 15, 30, 0, 0, 0)
        dt_upd = fetch_news.parse_date(entry_upd)
        self.assertEqual(dt_upd, datetime(2026, 4, 18, 12, 15, 30, tzinfo=timezone.utc))

        # 3. 缺欄位 / 空 entry / 異常值
        entry_empty = MagicMock(spec=[])
        self.assertIsNone(fetch_news.parse_date(entry_empty))

        entry_invalid = MagicMock()
        entry_invalid.published_parsed = "invalid_tuple"
        entry_invalid.updated_parsed = None
        self.assertIsNone(fetch_news.parse_date(entry_invalid))

    def test_fetch_feed_limits_and_summary_truncation(self):
        """測試 fetch_feed：res.ok 為 False 回傳空清單、限制最多 15 則、summary 截斷至 500 字"""
        feed_info = {"name": "TestFeed", "url": "https://example.com/rss"}

        # 1. 失敗情境 (res.ok = False)
        mock_fail_res = MagicMock()
        mock_fail_res.ok = False
        mock_fail_res.error = "Connection timeout"
        with patch.object(fetch_news, "robust_fetch_feed", return_value=mock_fail_res):
            articles = fetch_news.fetch_feed(feed_info)
            self.assertEqual(articles, [])

        # 2. 成功情境：產生 20 則 entry，其中一則含 600 字 summary
        entries = []
        for i in range(20):
            entry = {
                "title": f"Title {i}",
                "link": f"https://example.com/item/{i}",
                "summary": "A" * 600 if i == 0 else f"Short summary {i}",
            }
            mock_entry = MagicMock()
            mock_entry.get.side_effect = lambda k, default=None, d=entry: d.get(k, default)
            mock_entry.published_parsed = (2026, 4, 18, 8, i, 0, 0, 0, 0)
            mock_entry.updated_parsed = None
            entries.append(mock_entry)

        mock_feed = MagicMock()
        mock_feed.entries = entries
        mock_success_res = MagicMock()
        mock_success_res.ok = True
        mock_success_res.parsed = mock_feed

        with patch.object(fetch_news, "robust_fetch_feed", return_value=mock_success_res):
            articles = fetch_news.fetch_feed(feed_info)
            # 限制前 15 則
            self.assertEqual(len(articles), 15)
            # 第一則 summary 截斷至 500 字
            self.assertEqual(len(articles[0]["summary"]), 500)
            self.assertEqual(articles[0]["summary"], "A" * 500)
            self.assertEqual(articles[0]["source"], "TestFeed")
            self.assertEqual(articles[0]["title"], "Title 0")
            self.assertEqual(articles[0]["link"], "https://example.com/item/0")
            self.assertEqual(articles[0]["published"], "2026-04-18T08:00:00+00:00")

    def test_filter_by_date_taipei_boundary(self):
        """測試 filter_by_date：台北時區 UTC+8 換日邊界值與無效日期過濾"""
        # UTC 2026-04-18 15:59:00 -> 台北時間 2026-04-18 23:59:00 (屬於 2026-04-18)
        # UTC 2026-04-18 16:00:00 -> 台北時間 2026-04-19 00:00:00 (屬於 2026-04-19)
        articles = [
            {
                "title": "Item A (Taipei 04-18)",
                "published": "2026-04-18T15:59:00+00:00",
            },
            {
                "title": "Item B (Taipei 04-19)",
                "published": "2026-04-18T16:00:00+00:00",
            },
            {
                "title": "Item C (No published)",
                "published": None,
            },
            {
                "title": "Item D (Malformed date)",
                "published": "invalid-iso-string",
            },
        ]

        target_0418 = date(2026, 4, 18)
        filtered_0418 = fetch_news.filter_by_date(articles, target_0418)
        self.assertEqual(len(filtered_0418), 1)
        self.assertEqual(filtered_0418[0]["title"], "Item A (Taipei 04-18)")

        target_0419 = date(2026, 4, 19)
        filtered_0419 = fetch_news.filter_by_date(articles, target_0419)
        self.assertEqual(len(filtered_0419), 1)
        self.assertEqual(filtered_0419[0]["title"], "Item B (Taipei 04-19)")

    def test_filter_by_window_rules(self):
        """測試 filter_by_window：註解明寫之滾動 N 小時視窗規則、邊界值及略過無 published 項目"""
        fixed_now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=fetch_news.TZ_TAIPEI)

        # window_hours = 24，cutoff 為 2026-04-17 12:00:00+08:00
        articles = [
            # 剛好在 cutoff 上 (保留)
            {
                "title": "At cutoff",
                "published": (fixed_now - timedelta(hours=24)).isoformat(),
            },
            # 在 cutoff 內 1 小時 (保留)
            {
                "title": "Inside window",
                "published": (fixed_now - timedelta(hours=23)).isoformat(),
            },
            # 在 cutoff 外 1 秒 (濾除)
            {
                "title": "Outside window",
                "published": (fixed_now - timedelta(hours=24, seconds=1)).isoformat(),
            },
            # 無日期 / 格式無效 (略過)
            {
                "title": "No date",
                "published": None,
            },
            {
                "title": "Corrupted date",
                "published": "not-a-valid-date",
            },
        ]

        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        with patch.object(fetch_news, "datetime", MockDateTime):
            kept = fetch_news.filter_by_window(articles, window_hours=24)
            kept_titles = [a["title"] for a in kept]
            self.assertEqual(kept_titles, ["At cutoff", "Inside window"])

    def test_fetch_all_sorting_and_log_isolation(self):
        """測試 fetch_all：依 published 降冪排序、分類結構正確、log 寫入至暫存檔隔離"""
        fake_feeds = {
            "ai": [
                {"name": "Feed AI", "url": "https://example.com/ai"},
            ],
            "crypto": [
                {"name": "Feed Crypto", "url": "https://example.com/crypto"},
            ],
        }

        # 模擬 fetch_feed 回傳無序的文章清單
        mock_articles = [
            {
                "source": "Feed AI",
                "title": "Old News",
                "link": "https://example.com/1",
                "summary": "Sum 1",
                "published": "2026-04-17T01:00:00+08:00",
            },
            {
                "source": "Feed AI",
                "title": "New News",
                "link": "https://example.com/2",
                "summary": "Sum 2",
                "published": "2026-04-18T10:00:00+08:00",
            },
            {
                "source": "Feed AI",
                "title": "Middle News",
                "link": "https://example.com/3",
                "summary": "Sum 3",
                "published": "2026-04-17T12:00:00+08:00",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_log_path = os.path.join(tmpdir, "test-twstock.log")

            with patch.dict(fetch_news.FEEDS, fake_feeds, clear=True), \
                 patch.object(fetch_news, "fetch_feed", return_value=list(mock_articles)), \
                 patch.object(fetch_news.os.path, "expanduser", return_value=temp_log_path):

                result = fetch_news.fetch_all(target_date=None, window_hours=None)

                # 驗證結構
                self.assertIn("ai", result)
                self.assertIn("crypto", result)
                self.assertEqual(result["ai"]["label"], fetch_news.SECTOR_LABELS["ai"])

                # 驗證降冪排序 (New News -> Middle News -> Old News)
                ai_titles = [a["title"] for a in result["ai"]["articles"]]
                self.assertEqual(ai_titles, ["New News", "Middle News", "Old News"])

                # 驗證 log 寫入 temp_log_path，且內容包含監控資訊
                self.assertTrue(os.path.exists(temp_log_path))
                with open(temp_log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.assertIn('"mode": "all"', content)
                    self.assertIn('"sector_counts"', content)


if __name__ == "__main__":
    unittest.main()
