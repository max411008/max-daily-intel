#!/usr/bin/env python3
"""Build rich daily-intel cards (HTML → PNG) for 4/10-4/13 matching 4/08 style."""
import re, os, subprocess, sys

DOCS = '/Users/maxlin/Projects/max-daily-intel/docs'
DATES = sys.argv[1:] if len(sys.argv) > 1 else ['2026-04-10','2026-04-11','2026-04-12','2026-04-13']
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

SECTOR_MAP = {
    '加密貨幣': ('加密貨幣', '#f7931a'),
    'Crypto': ('加密貨幣', '#f7931a'),
    '黃金': ('黃金商品', '#ffd700'),
    '商品': ('黃金商品', '#ffd700'),
    '台股': ('台股', '#e53935'),
    '美股': ('美股', '#4caf50'),
    '股票': ('股票', '#4caf50'),
    'AI': ('AI 產業', '#a78bfa'),
    'Dev': ('開發靈感', '#22d3ee'),
    '開發': ('開發靈感', '#22d3ee'),
    '工具': ('開發靈感', '#22d3ee'),
}

def extract(date):
    html = open(f'{DOCS}/{date}.html', encoding='utf-8').read()
    sectors = []
    for m in re.finditer(r'<h2>[^<]*?([\u4e00-\u9fff A-Za-z]+?)</h2>(.*?)(?=<div class="sector-header"|</body>)', html, re.DOTALL):
        name = m.group(1).strip()
        body = m.group(2)
        hm = re.search(r'<h3>\s*<a[^>]*>([^<]+)</a>', body)
        if not hm: continue
        title = hm.group(1).strip()
        # Truncate long EN titles
        if len(title) > 40:
            title = title[:38] + '…'
        lbl, col = None, None
        for key, (l, c) in SECTOR_MAP.items():
            if key in name:
                lbl, col = l, c; break
        if not lbl: continue
        if any(s[0]==lbl for s in sectors): continue
        sectors.append((lbl, col, title))
    return sectors[:6]

WEEKDAY_ZH = ['一','二','三','四','五','六','日']

def card_html(date, sectors):
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d')
    wd = WEEKDAY_ZH[dt.weekday()]
    date_disp = f'{dt.year}/{dt.month:02d}/{dt.day:02d}（{wd}）'
    cells = '\n'.join(
        f'<div class="cell"><div class="dot" style="background:{c}"></div><div>'
        f'<div class="label" style="color:{c}">{lbl}</div>'
        f'<div class="headline">{title}</div></div></div>'
        for lbl,c,title in sectors
    )
    return f'''<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:400px;height:280px;font-family:'Noto Sans TC',-apple-system,sans-serif;background:#0f0f1a;color:#fff;overflow:hidden;position:relative}}
.bg-mesh{{position:absolute;inset:0;overflow:hidden;z-index:0}}
.bg-mesh .orb1{{position:absolute;width:250px;height:250px;top:-80px;right:-60px;background:radial-gradient(circle,rgba(167,139,250,0.3) 0%,transparent 65%);border-radius:50%;filter:blur(30px)}}
.bg-mesh .orb2{{position:absolute;width:200px;height:200px;bottom:-60px;left:-50px;background:radial-gradient(circle,rgba(34,211,238,0.2) 0%,transparent 65%);border-radius:50%;filter:blur(30px)}}
.content{{position:relative;z-index:1;padding:18px 20px 14px;height:100%;display:flex;flex-direction:column}}
.top-row{{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px}}
.top-row .title{{font-size:1.1rem;font-weight:900;background:linear-gradient(135deg,#fff 30%,rgba(167,139,250,0.9));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.top-row .date{{font-size:0.65rem;color:rgba(255,255,255,0.4);font-weight:500}}
.divider{{width:100%;height:1px;background:linear-gradient(90deg,rgba(167,139,250,0.4),rgba(34,211,238,0.4),transparent);margin-bottom:12px}}
.grid{{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.cell{{display:flex;gap:6px;align-items:flex-start}}
.cell .dot{{width:4px;height:4px;border-radius:50%;margin-top:6px;flex-shrink:0}}
.cell .label{{font-size:0.5rem;font-weight:700;opacity:0.6;letter-spacing:0.05em;margin-bottom:1px}}
.cell .headline{{font-size:0.68rem;font-weight:700;line-height:1.3}}
.bottom-row{{margin-top:auto;display:flex;align-items:center;justify-content:space-between;padding-top:8px}}
.bottom-row .url{{font-size:0.5rem;color:rgba(255,255,255,0.25)}}
.bottom-row .badge{{font-size:0.5rem;color:rgba(255,255,255,0.4);padding:2px 8px;border-radius:999px;border:1px solid rgba(255,255,255,0.1)}}
</style></head><body>
<div class="bg-mesh"><div class="orb1"></div><div class="orb2"></div></div>
<div class="content">
<div class="top-row"><span class="title">MAX 每日情報</span><span class="date">{date_disp}</span></div>
<div class="divider"></div>
<div class="grid">{cells}</div>
<div class="bottom-row"><span class="url">MAX Daily Intel</span><span class="badge">{len(sectors)} 板塊</span></div>
</div></body></html>'''

os.makedirs(f'{DOCS}/cards', exist_ok=True)
for d in DATES:
    sectors = extract(d)
    if not sectors:
        print(f'{d}: no sectors found, skip'); continue
    card_path = f'{DOCS}/cards/{d}-card.html'
    png_path = f'{DOCS}/cards/{d}.png'
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write(card_html(d, sectors))
    # Render PNG @ 400x280, scale 2x for retina
    r = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
        f'--screenshot={png_path}', '--window-size=400,280', '--default-background-color=0f0f1aff',
        '--force-device-scale-factor=2',
        f'file://{card_path}'],
        capture_output=True, timeout=30)
    if not os.path.exists(png_path):
        print(f'{d}: PNG render FAILED\n{r.stderr.decode()[:300]}')
    else:
        sz = os.path.getsize(png_path)
        print(f'{d}: {len(sectors)} sectors, card html + PNG ({sz}B)')
