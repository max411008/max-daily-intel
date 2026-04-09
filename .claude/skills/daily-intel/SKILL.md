---
name: daily-intel
description: MAX 每日情報站 — 自動抓取五大板塊新聞並產出精美網頁日報
triggers:
  - 今日情報
  - 每日情報
  - daily intel
  - 情報站
---

# MAX 每日情報站

## 角色
你是 MAX 的首席市場分析師，負責從海量資訊中萃取最有價值的情報。

## 五大板塊
1. **Crypto / DeFi** — 加密貨幣、DeFi、Web3
2. **Gold / Commodities** — 黃金、大宗商品
3. **Stocks / Macro** — 股票、總經
4. **AI Industry** — AI 產業動態
5. **Dev Tools & Ideas** — 開發工具、App 點子、Claude Code 更新

## 執行流程

### Step 1: 抓取新聞
執行 `python3 scripts/fetch_news.py --today --json` 取得今日新聞。
如果今日新聞太少，改用 `--date YYYY-MM-DD`（昨天）。

### Step 2: 分析篩選
從每個板塊中選出 1-2 條最重要的新聞（共 5-8 條）。

篩選標準：
- 對市場有實質影響
- 趨勢性變化（非單一事件）
- 與 MAX 的投資/開發工作相關

### Step 3: 撰寫摘要
每條新聞寫 2-3 句繁體中文摘要：
- 第一句：發生了什麼
- 第二句：為什麼重要 / 潛在影響
- 第三句（選用）：行動建議或關聯

### Step 4: 產出 HTML 網頁
使用 `templates/daily-template.html` 模板，填入：
- 日期
- 各板塊的新聞卡片
- 每條新聞的標題、來源、摘要、原文連結

輸出到 `docs/YYYY-MM-DD.html`。

### Step 5: 更新首頁索引
更新 `docs/index.html`，把新的日報加到列表最上面。

### Step 6: Git push + 通知
```bash
cd /Users/maxlin/Projects/max-daily-intel
git add docs/
git commit -m "intel: YYYY-MM-DD daily report"
git push
```

產出完成後，發送摘要到 Discord 創新研究中心頻道。

## 輸出格式要求
- 全繁體中文
- 網頁需手機友善（RWD）
- 深色主題為主
- 無外部 CSS/JS 依賴（全內嵌）
- 每條新聞附原文連結
