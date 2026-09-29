#!/usr/bin/env python3
"""Unit tests for scripts/generate_report.py."""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

# Import target module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import generate_report


class TestGenerateReport(unittest.TestCase):

    def test_generate_sector_html_empty(self):
        """Test sector HTML generation with empty articles and fallback sector info."""
        html = generate_report.generate_sector_html("custom_sector", "自訂板塊", [], "#123456")
        self.assertIn('id="custom_sector"', html)
        self.assertIn("今日暫無相關情報", html)
        self.assertIn('<span class="badge">0 則</span>', html)
        self.assertIn("自訂板塊", html)
        self.assertIn("background:#123456", html)

    def test_generate_sector_html_summary_priority_and_tag_strip(self):
        """Test summary priority (analysis > summary_zh > summary) and HTML tag stripping."""
        articles = [
            {
                "title_zh": "中文標題",
                "title": "English Title",
                "analysis": "<b>深度分析內容</b>",
                "summary_zh": "中文摘要",
                "summary": "英文摘要",
                "source": "TechNews",
                "link": "https://example.com/1",
            },
            {
                "title": "Fallback Title",
                "summary_zh": "<i>第二篇摘要</i>",
                "summary": "Second Summary",
                "source": "CoinDesk",
            },
            {
                "title": "Last Resort Title",
                "summary": "Only english summary",
            },
        ]
        html = generate_report.generate_sector_html("crypto", "加密貨幣", articles, "#f7931a")

        # Article 1: analysis wins, HTML tags stripped, title_zh wins
        self.assertIn("深度分析內容", html)
        self.assertNotIn("<b>", html)
        self.assertNotIn("中文摘要", html)
        self.assertIn("中文標題", html)
        self.assertNotIn("English Title", html)

        # Article 2: summary_zh wins over summary, tags stripped, fallback title
        self.assertIn("第二篇摘要", html)
        self.assertNotIn("<i>", html)
        self.assertNotIn("Second Summary", html)
        self.assertIn("Fallback Title", html)

        # Article 3: summary as last resort
        self.assertIn("Only english summary", html)
        self.assertIn("Last Resort Title", html)
        self.assertIn('<span class="badge">3 則</span>', html)

    def test_generate_sector_html_boundary_truncation_and_tags(self):
        """Test 300-char truncation boundary and tags rendering."""
        summary_300 = "A" * 300
        summary_301 = "B" * 301

        articles = [
            {
                "title": "Exact 300",
                "summary": summary_300,
                "tags": ["AI", "LLM"],
            },
            {
                "title": "Over 300",
                "summary": summary_301,
            },
        ]
        html = generate_report.generate_sector_html("ai", "AI 產業", articles, "#7c4dff")

        # Exactly 300 characters should NOT be truncated with "..."
        self.assertIn(f'<div class="summary">{summary_300}</div>', html)
        # 301 characters should be truncated to 300 + "..."
        expected_truncated = "B" * 300 + "..."
        self.assertIn(f'<div class="summary">{expected_truncated}</div>', html)

        # Tags rendering
        self.assertIn('<span class="tag">AI</span>', html)
        self.assertIn('<span class="tag">LLM</span>', html)

    def test_generate_report_rendering(self):
        """Test full HTML report templating, Chinese date formatting, and counts calculation."""
        template_content = (
            "DATE: {{DATE}}\n"
            "DISPLAY: {{DATE_DISPLAY}}\n"
            "CRYPTO: {{CRYPTO_COUNT}}\n"
            "GOLD: {{GOLD_COUNT}}\n"
            "TOTAL: {{TOTAL_COUNT}}\n"
            "SECTORS: {{SECTORS_HTML}}"
        )
        analyzed_data = {
            "crypto": {
                "label": "加密貨幣",
                "articles": [{"title": "BTC", "summary": "Bitcoin hit high"}],
            },
            "gold": {
                "label": "黃金商品",
                "articles": [
                    {"title": "Gold 1", "summary": "Summary 1"},
                    {"title": "Gold 2", "summary": "Summary 2"},
                ],
            },
        }

        # 2026-09-30 is Wednesday (三)
        date_str = "2026-09-30"
        with patch("builtins.open", mock_open(read_data=template_content)):
            rendered = generate_report.generate_report(analyzed_data, date_str)

        self.assertIn("DATE: 2026-09-30", rendered)
        self.assertIn("DISPLAY: 2026 年 9 月 30 日（三）", rendered)
        self.assertIn("CRYPTO: 1", rendered)
        self.assertIn("GOLD: 2", rendered)
        self.assertIn("TOTAL: 3", rendered)
        self.assertIn('id="crypto"', rendered)
        self.assertIn('id="gold"', rendered)

    def test_update_index_sorting_and_svg_placeholder(self):
        """Test update_index idempotency, DESC sorting, and SVG placeholder generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = os.path.join(tmpdir, "scripts")
            docs_dir = os.path.join(tmpdir, "docs")
            os.makedirs(scripts_dir)
            os.makedirs(docs_dir)

            fake_script = os.path.join(scripts_dir, "generate_report.py")
            index_path = os.path.join(docs_dir, "index.html")

            initial_content = (
                "<html><body>\n"
                "<ul>\n"
                '    <li><a class="issue-card" href="2026-09-28.html">'
                '<div class="info"><span class="date">2026/09/28（一）</span>'
                '<span class="meta">2 則情報</span></div></a></li>\n'
                "    <!-- ISSUES_LIST -->\n"
                "</ul></body></html>"
            )
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(initial_content)

            with patch.object(generate_report, "__file__", fake_script):
                # Update with 2026-09-30 (newer date)
                generate_report.update_index("2026-09-30", 5)

                with open(index_path, "r", encoding="utf-8") as f:
                    updated_content = f.read()

                # Verify DESC ordering: 2026-09-30 appears before 2026-09-28
                pos_30 = updated_content.find("2026-09-30.html")
                pos_28 = updated_content.find("2026-09-28.html")
                self.assertNotEqual(pos_30, -1)
                self.assertNotEqual(pos_28, -1)
                self.assertLess(pos_30, pos_28)

                # Verify count updated
                self.assertIn("5 則情報", updated_content)
                self.assertIn("2 則情報", updated_content)

                # Verify SVG fallback placeholder is inlined when PNG card does not exist
                self.assertIn("data:image/svg+xml;utf8,<svg", updated_content)


if __name__ == "__main__":
    unittest.main()
