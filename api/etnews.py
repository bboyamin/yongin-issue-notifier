from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os

# Add project root to sys.path so we can import src.etnews_collector
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.etnews_collector import fetch_etnews_by_date, get_etnews_article_body
except ImportError:
    def fetch_etnews_by_date(ymd_str):
        return {"sections": [], "categorized": {}, "articles": []}
    def get_etnews_article_body(url):
        return None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # Check if requesting article body text
        article_url = params.get('url', [None])[0]
        if article_url:
            content = get_etnews_article_body(article_url)
            response_data = {"url": article_url, "content": content or ""}
        else:
            date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]
            if not date_param:
                from datetime import datetime, timezone, timedelta
                kst = timezone(timedelta(hours=9))
                date_param = datetime.now(kst).strftime("%Y%m%d")
            
            # Clean ymd string
            ymd_str = date_param.replace("-", "").strip()
            result = fetch_etnews_by_date(ymd_str)
            response_data = result

        body = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 's-maxage=1800, stale-while-revalidate=3600')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
