import os
import sys
import json
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Add src module to python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
try:
    from local_issue_collector import collect_all_issues
except Exception as e:
    print("Collector import notice:", e)
    collect_all_issues = None

class DynamicHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        public_dir = os.path.join(os.path.dirname(__file__), "public")
        super().__init__(*args, directory=public_dir, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/api/collect":
            query_params = urllib.parse.parse_qs(parsed_path.query)
            tab = query_params.get("tab", ["realtime"])[0]
            force_refresh = query_params.get("force", ["false"])[0].lower() == "true"
            output_path = os.path.join(os.path.dirname(__file__), "public", "data", f"issues_{tab}.json")
            
            if "keywords" in query_params:
                kw_param = query_params.get("keywords")[0]
                keywords = [k.strip() for k in kw_param.split(",") if k.strip()]
            else:
                keywords = None

            if os.path.exists(output_path) and not force_refresh:
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        cached_issues = json.load(f)
                    if cached_issues and len(cached_issues) > 0:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps(cached_issues, ensure_ascii=False).encode('utf-8'))
                        return
                except Exception:
                    pass

            print(f"🔄 [/api/collect] 수집 요청 (탭: {tab}, 키워드: {keywords})")
            try:
                import importlib
                import local_issue_collector
                importlib.reload(local_issue_collector)
                issues = local_issue_collector.collect_all_issues(keywords=keywords, tab=tab)
            except Exception as e:
                print("Collector execution error:", e)
                issues = []
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(issues, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(issues, ensure_ascii=False).encode('utf-8'))
            return

        elif parsed_path.path in ["/api/papernews", "/api/etnews", "/api/mknews", "/api/chosun", "/api/joongang", "/api/donga"]:
            query_params = urllib.parse.parse_qs(parsed_path.query)
            provider = query_params.get("provider", ["etnews"])[0]
            if parsed_path.path == "/api/mknews":
                provider = "mknews"
            elif parsed_path.path == "/api/etnews":
                provider = "etnews"
            elif parsed_path.path == "/api/chosun":
                provider = "chosun"
            elif parsed_path.path == "/api/joongang":
                provider = "joongang"
            elif parsed_path.path == "/api/donga":
                provider = "donga"

            ymd = query_params.get("date", [datetime.now().strftime("%Y%m%d")])[0].replace("-", "")
            try:
                from api.papernews import fetch_paper_news
                result = fetch_paper_news(provider=provider, ymd_str=ymd)
            except Exception as e:
                print(f"Paper news fetch error ({provider}):", e)
                result = {"sections": [], "categorized": {}, "articles": []}

            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

if __name__ == "__main__":
    port = 8080
    print(f"🚀 Custom Server running on http://localhost:{port}")
    server = HTTPServer(('0.0.0.0', port), DynamicHTTPHandler)
    server.serve_forever()
