import os
import sys
import json
import requests
import xml.etree.ElementTree as ET
import re
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

KHAN_RSS_FEEDS = {
    "all": "https://www.khan.co.kr/rss/rssdata/total_news.xml",
    "politic": "https://www.khan.co.kr/rss/rssdata/politic_news.xml",
    "economy": "https://www.khan.co.kr/rss/rssdata/economy_news.xml",
    "society": "https://www.khan.co.kr/rss/rssdata/society_news.xml",
    "culture": "https://www.khan.co.kr/rss/rssdata/culture_news.xml",
    "world": "https://www.khan.co.kr/rss/rssdata/kh_world.xml",
    "science": "https://www.khan.co.kr/rss/rssdata/science_news.xml",
    "opinion": "https://www.khan.co.kr/rss/rssdata/opinion_news.xml"
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

def fetch_kyunghyang_rss(category_key="all"):
    feed_url = KHAN_RSS_FEEDS.get(category_key, KHAN_RSS_FEEDS["all"])
    try:
        res = requests.get(feed_url, headers=headers, timeout=6)
        if res.status_code != 200:
            return {"error": f"HTTP {res.status_code}", "articles": []}

        root = ET.fromstring(res.content)
        items = root.findall('.//item')
        parsed = []

        for idx, item in enumerate(items):
            t_el = item.find('title')
            l_el = item.find('link')
            d_el = item.find('description')
            date_el = item.find('{http://purl.org/dc/elements/1.1/}date')
            creator_el = item.find('{http://purl.org/dc/elements/1.1/}creator')
            cat_el = item.find('category')

            title = re.sub(r'<[^>]+>', '', t_el.text).strip() if t_el is not None and t_el.text else ""
            link = l_el.text.strip() if l_el is not None and l_el.text else ""
            desc = re.sub(r'<[^>]+>', '', d_el.text).strip() if d_el is not None and d_el.text else ""
            
            date_str = date_el.text.strip() if date_el is not None and date_el.text else ""
            pub_time = date_str[:16].replace('T', ' ').replace('-', '/') if len(date_str) >= 16 else date_str
            
            creator = creator_el.text.strip() if creator_el is not None and creator_el.text else "경향신문"
            cat_name = cat_el.text.strip() if cat_el is not None and cat_el.text else "뉴스"

            if title:
                parsed.append({
                    "id": f"kyunghyang_{category_key}_{idx}",
                    "title": title,
                    "url": link,
                    "time": pub_time,
                    "publisher": "경향신문",
                    "badge": f"📰 경향신문 · {cat_name}",
                    "creator": creator,
                    "content": desc
                })

        return {
            "category": category_key,
            "feed_url": feed_url,
            "total_count": len(parsed),
            "articles": parsed
        }
    except Exception as e:
        return {"error": str(e), "articles": []}

class KyunghyangTestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        public_dir = os.path.join(os.path.dirname(__file__), "public")
        super().__init__(*args, directory=public_dir, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/test_kyunghyang":
            params = urllib.parse.parse_qs(parsed.query)
            cat = params.get('cat', ['all'])[0]
            data = fetch_kyunghyang_rss(cat)
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

def run(port=8888):
    server_address = ('', port)
    httpd = HTTPServer(server_address, KyunghyangTestHandler)
    print(f"🚀 경향신문 RSS 테스트 서버 시작됨: http://localhost:{port}/test_kyunghyang.html")
    httpd.serve_forever()

if __name__ == "__main__":
    run(8888)
