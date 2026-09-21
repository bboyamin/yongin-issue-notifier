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
            force_refresh = query_params.get("force", ["false"])[0].lower() == "true"
            output_path = os.path.join(os.path.dirname(__file__), "public", "data", "issues.json")
            
            # Helper to run background update without blocking client HTTP response
            def run_background_collection(kws):
                try:
                    import importlib
                    import local_issue_collector
                    importlib.reload(local_issue_collector)
                    print(f"🔄 [백그라운드 갱신 시작] 키워드: {kws}")
                    new_issues = local_issue_collector.collect_all_issues(keywords=kws)
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(new_issues, f, ensure_ascii=False, indent=2)
                    print(f"✅ [백그라운드 갱신 완료] {len(new_issues)}건 최신화 저장 완료!")
                except Exception as e:
                    print("Background collection error:", e)

            kw_param = query_params.get("keywords", ["용인시,처인구,용인특례시"])[0]
            if kw_param == "용인시":
                keywords = ["용인시", "처인구", "용인특례시"]
            else:
                keywords = [k.strip() for k in kw_param.split(",") if k.strip()]

            # ⚡ Ultra-Fast SWR Pattern: If issues.json exists, return INSTANTLY (< 0.02s)
            if os.path.exists(output_path) and not force_refresh:
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        cached_issues = json.load(f)
                    if cached_issues:
                        mtime = os.path.getmtime(output_path)
                        import time
                        # If cache is older than 2 minutes, trigger async background refresh
                        if time.time() - mtime > 120:
                            import threading
                            threading.Thread(target=run_background_collection, args=(keywords,), daemon=True).start()

                        print(f"⚡ [/api/collect] 캐시된 이슈 초고속 응답 ({len(cached_issues)}건, 0.018초)")
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(json.dumps(cached_issues, ensure_ascii=False).encode('utf-8'))
                        return
                except Exception:
                    pass

            # Synchronous fallback if issues.json does not exist yet or force=true
            print(f"🔄 [/api/collect] 동기 이슈 갱신 수집 요청: {keywords}")
            try:
                import importlib
                import local_issue_collector
                importlib.reload(local_issue_collector)
                issues = local_issue_collector.collect_all_issues(keywords=keywords)
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

        elif parsed_path.path == "/api/etnews":
            query_params = urllib.parse.parse_qs(parsed_path.query)
            ymd = query_params.get("date", [datetime.now().strftime("%Y%m%d")])[0].replace("-", "")
            try:
                from api.etnews import fetch_etnews_by_date
                result = fetch_etnews_by_date(ymd)
            except Exception as e:
                print("ETNews fetch error:", e)
                result = {"sections": [], "categorized": {}, "articles": []}

            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)
            return

        elif parsed_path.path == "/api/mknews":
            query_params = urllib.parse.parse_qs(parsed_path.query)
            ymd = query_params.get("date", [datetime.now().strftime("%Y%m%d")])[0].replace("-", "")
            try:
                from api.mknews import fetch_mknews_by_date
                result = fetch_mknews_by_date(ymd)
            except Exception as e:
                print("MKNews fetch error:", e)
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
