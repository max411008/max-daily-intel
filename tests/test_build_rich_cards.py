import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

# 匯入 scripts 目錄
scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# 匯入隔離：build_rich_cards 頂層會執行 open / os.makedirs / subprocess.run
# 透過 patch sys.argv、builtins.open、os.makedirs、subprocess.run 達成零副作用
with patch("sys.argv", ["build_rich_cards.py", "2000-01-01"]), \
     patch("os.makedirs"), \
     patch("builtins.open", mock_open(read_data="")), \
     patch("subprocess.run"):
    import build_rich_cards


class TestBuildRichCards(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_docs = build_rich_cards.DOCS
        build_rich_cards.DOCS = self.temp_dir.name

    def tearDown(self):
        build_rich_cards.DOCS = self.orig_docs
        self.temp_dir.cleanup()

    def _write_html(self, date_str, content):
        path = os.path.join(self.temp_dir.name, f"{date_str}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_card_html_rendering(self):
        """測試 card_html 產生 HTML 的格式、日期、星期與板塊徽章"""
        sectors = [
            ("台股", "#e53935", "台股開高走低收黑"),
            ("AI 產業", "#a78bfa", "晶片需求持續強勁"),
        ]
        # 測試週一 (2026-04-13)
        html = build_rich_cards.card_html("2026-04-13", sectors)
        self.assertIn("2026/04/13（一）", html)
        self.assertIn('<span class="badge">2 板塊</span>', html)
        self.assertIn("台股開高走低收黑", html)
        self.assertIn("晶片需求持續強勁", html)
        self.assertIn('style="background:#e53935"', html)
        self.assertIn('style="color:#a78bfa"', html)

        # 測試週日 (2026-04-12)
        html_sun = build_rich_cards.card_html("2026-04-12", [])
        self.assertIn("2026/04/12（日）", html_sun)
        self.assertIn('<span class="badge">0 板塊</span>', html_sun)

    def test_extract_normal_and_sector_mapping(self):
        """測試 extract 正常解析 HTML 標籤及板塊對應"""
        html_content = (
            '<h2>加密貨幣</h2>'
            '<div><h3><a href="https://example.com/btc">比特幣挑戰新高點</a></h3></div>'
            '<div class="sector-header"></div>'
            '<h2>美股市場</h2>'
            '<div><h3><a href="https://example.com/sp500">標普五百指數微跌</a></h3></div>'
            '</body>'
        )
        self._write_html("2026-04-10", html_content)
        sectors = build_rich_cards.extract("2026-04-10")

        self.assertEqual(len(sectors), 2)
        self.assertEqual(sectors[0], ("加密貨幣", "#f7931a", "比特幣挑戰新高點"))
        self.assertEqual(sectors[1], ("美股", "#4caf50", "標普五百指數微跌"))

    def test_extract_title_truncation_and_deduplication(self):
        """測試長標題截斷（>40 字截為 38 字加…）與同 label 板塊去重"""
        long_title = "A" * 45
        expected_title = "A" * 38 + "…"

        html_content = (
            '<h2>AI 科技</h2>'
            f'<div><h3><a href="#">{long_title}</a></h3></div>'
            '<div class="sector-header"></div>'
            '<h2>加密貨幣</h2>'
            '<div><h3><a href="#">第一個加密新聞</a></h3></div>'
            '<div class="sector-header"></div>'
            '<h2>Crypto</h2>'
            '<div><h3><a href="#">第二個加密新聞（重複應略過）</a></h3></div>'
            '</body>'
        )
        self._write_html("2026-04-11", html_content)
        sectors = build_rich_cards.extract("2026-04-11")

        self.assertEqual(len(sectors), 2)
        # 標題截斷檢查
        self.assertEqual(sectors[0][0], "AI 產業")
        self.assertEqual(sectors[0][2], expected_title)
        self.assertEqual(len(sectors[0][2]), 39)  # 38 + 1('…')
        # 去重檢查：Crypto 與 加密貨幣 均對應到 '加密貨幣'，第二筆被略過
        crypto_sectors = [s for s in sectors if s[0] == "加密貨幣"]
        self.assertEqual(len(crypto_sectors), 1)
        self.assertEqual(crypto_sectors[0][2], "第一個加密新聞")

    def test_extract_max_six_sectors_limit(self):
        """測試 extract 最多回傳 6 個板塊的邊界條件"""
        # 7 個具備不同 label 的板塊
        sector_names = ["加密貨幣", "黃金", "台股", "美股", "股票", "AI", "Dev"]
        chunks = []
        for name in sector_names:
            chunks.append(
                f'<h2>{name}</h2><div><h3><a href="#">{name} 標題</a></h3></div>'
            )
        html_content = '<div class="sector-header"></div>'.join(chunks) + "</body>"

        self._write_html("2026-04-12", html_content)
        sectors = build_rich_cards.extract("2026-04-12")

        self.assertEqual(len(sectors), 6)
        labels = [s[0] for s in sectors]
        self.assertNotIn("開發靈感", labels)

    def test_extract_empty_and_missing_fields(self):
        """測試空檔案、無對應板塊、缺標題連結等邊界情況"""
        # 1. 完全空的檔案
        self._write_html("2026-04-13", "")
        self.assertEqual(build_rich_cards.extract("2026-04-13"), [])

        # 2. 包含 h2 但不在 SECTOR_MAP
        html_unmapped = (
            '<h2>未收錄板塊</h2>'
            '<div><h3><a href="#">某某內容</a></h3></div>'
            '</body>'
        )
        self._write_html("2026-04-14", html_unmapped)
        self.assertEqual(build_rich_cards.extract("2026-04-14"), [])

        # 3. 包含板塊但缺 h3 a 標題
        html_no_title = (
            '<h2>台股</h2>'
            '<div><p>只有內文沒有連結標題</p></div>'
            '</body>'
        )
        self._write_html("2026-04-15", html_no_title)
        self.assertEqual(build_rich_cards.extract("2026-04-15"), [])


if __name__ == "__main__":
    unittest.main()
