from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.local_issue_collector import collect_all_issues
except ImportError:
    def collect_all_issues(keywords=None):
        return []

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # 1. Handle API requests (path starting with /api or query with keywords)
        if path.startswith("/api") or "keywords" in parsed.query:
            params = urllib.parse.parse_qs(parsed.query)
            kw_str = params.get('keywords', ['용인시,처인구'])[0]
            keywords = [k.strip() for k in kw_str.split(',') if k.strip()]
            
            try:
                issues = collect_all_issues(keywords=keywords)
            except Exception as e:
                print("Vercel collect error:", e)
                issues = []

            body = json.dumps(issues, ensure_ascii=False).encode('utf-8')
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 2. Serve static assets (CSS, JS, PNG, JSON, SW)
        if path.startswith("/css/") or path.startswith("/js/") or path.startswith("/data/") or path in ["/manifest.json", "/sw.js", "/yongin_logo.png"]:
            file_path = os.path.join(base_dir, path.lstrip("/"))
            if os.path.exists(file_path):
                content_type = "text/plain"
                if path.endswith(".css"): content_type = "text/css; charset=utf-8"
                elif path.endswith(".js"): content_type = "application/javascript; charset=utf-8"
                elif path.endswith(".png"): content_type = "image/png"
                elif path.endswith(".json"): content_type = "application/json; charset=utf-8"

                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # 3. Default fallback: Serve index.html for root / and all other paths
        html_path = os.path.join(base_dir, "index.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read().encode("utf-8")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_response(404)
        self.end_headers()
