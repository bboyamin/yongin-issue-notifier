from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os
from datetime import datetime, timezone, timedelta

# Add project root and api dir to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
API_DIR = os.path.dirname(os.path.abspath(__file__))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

try:
    from src.local_issue_collector import collect_all_issues
except ImportError:
    def collect_all_issues(keywords=None, tab="realtime"):
        return []

try:
    from api.papernews import fetch_paper_news
except ImportError:
    try:
        from papernews import fetch_paper_news
    except ImportError:
        fetch_paper_news = None

def load_static_issues(tab="realtime"):
    file_map = {
        "exclusive": "issues_exclusive.json",
        "press": "issues_press.json",
        "realtime": "issues_realtime.json"
    }
    target_filename = file_map.get(tab, "issues.json")
    paths = [
        os.path.join(BASE_DIR, "public", "data", target_filename),
        os.path.join(BASE_DIR, "public", "data", "issues.json")
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and data:
                        return data
            except Exception as e:
                print(f"Error loading static issues from {p}: {e}")
    return []

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path_str = parsed.path.lower()
        params = urllib.parse.parse_qs(parsed.query)

        # --------------------------------------------------
        # Paper News Fallback Delegation (100% Backward Compatible)
        # --------------------------------------------------
        is_paper_request = any(k in path_str for k in ["papernews", "etnews", "mknews", "khan"]) or \
                           ('provider' in params) or ('mode' in params)
        if is_paper_request and fetch_paper_news:
            provider = params.get('provider', [None])[0] or params.get('mode', [None])[0]
            if not provider:
                if "mknews" in path_str:
                    provider = "mknews"
                elif "khan" in path_str:
                    provider = "khan"
                else:
                    provider = "etnews"

            date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]
            result = fetch_paper_news(provider=provider, ymd_str=date_param)

            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 's-maxage=300, stale-while-revalidate=600')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # --------------------------------------------------
        # Realtime / Press / Exclusive Issue Collection
        # --------------------------------------------------
        tab = params.get('tab', ['realtime'])[0].lower().strip()
        kw_str = params.get('keywords', [None])[0]
        keywords = [k.strip() for k in kw_str.split(',') if k.strip()] if kw_str else None

        issues = []
        try:
            live_issues = collect_all_issues(keywords=keywords, tab=tab)
            if live_issues and len(live_issues) > 0:
                issues = live_issues
            else:
                issues = load_static_issues(tab=tab) or []
        except Exception as e:
            print("Vercel collect error:", e)
            issues = load_static_issues(tab=tab) or []

        body = json.dumps(issues, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
