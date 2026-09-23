from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os
from datetime import datetime, timezone, timedelta

# Ensure api directory is in python module path for Vercel
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Top-level imports for Vercel Python bundler
try:
    from api.etnews import fetch_etnews_by_date
except ImportError:
    try:
        from etnews import fetch_etnews_by_date
    except ImportError:
        fetch_etnews_by_date = None

try:
    from api.mknews import fetch_mknews_by_date
except ImportError:
    try:
        from mknews import fetch_mknews_by_date
    except ImportError:
        fetch_mknews_by_date = None

try:
    from api.khan import fetch_khan_by_date
except ImportError:
    try:
        from khan import fetch_khan_by_date
    except ImportError:
        fetch_khan_by_date = None


def fetch_paper_news(provider="etnews", ymd_str=None):
    if not ymd_str:
        kst = timezone(timedelta(hours=9))
        ymd_str = datetime.now(kst).strftime("%Y%m%d")

    clean_ymd = ymd_str.replace("-", "").strip()
    provider = (provider or "etnews").lower().strip()

    # 1. ETNews
    if provider == "etnews" and fetch_etnews_by_date:
        try:
            return fetch_etnews_by_date(clean_ymd)
        except Exception as e:
            print("etnews dispatch error:", e)

    # 2. MKNews
    elif provider == "mknews" and fetch_mknews_by_date:
        try:
            return fetch_mknews_by_date(clean_ymd)
        except Exception as e:
            print("mknews dispatch error:", e)

    # 3. Khan (경향신문)
    elif provider in ["khan", "kyunghyang"] and fetch_khan_by_date:
        try:
            return fetch_khan_by_date(clean_ymd)
        except Exception as e:
            print("khan dispatch error:", e)

    return {"sections": [], "categorized": {}, "articles": []}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        provider = params.get('provider', ['etnews'])[0]
        date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]

        if not date_param:
            kst = timezone(timedelta(hours=9))
            date_param = datetime.now(kst).strftime("%Y%m%d")

        result = fetch_paper_news(provider=provider, ymd_str=date_param)

        body = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
