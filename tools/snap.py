"""ページを Chrome で開いて1枚撮る。  python tools/snap.py 出力.png 'view.html?cam=...'"""
import base64
import os
import sys

from playwright.sync_api import sync_playwright

out, path = sys.argv[1], sys.argv[2]
url = os.environ.get('BASE', 'http://127.0.0.1:8793/web/') + path
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=False, args=['--window-position=-2400,0', '--ignore-gpu-blocklist'])
    pg = b.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1)
    pg.on('console', lambda m: print('console:', m.text[:300]))
    pg.on('pageerror', lambda e: print('pageerror:', e))
    pg.goto(url)
    pg.wait_for_function('window.ready === true', timeout=120000)
    data = pg.evaluate("document.querySelector('canvas').toDataURL('image/png')")
    open(out, 'wb').write(base64.b64decode(data.split(',')[1]))
    b.close()
