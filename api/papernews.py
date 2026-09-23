import os
import sys
import json
import urllib.parse
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure api directory is in python module path for Vercel
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def fetch_paper_news(provider="etnews", ymd_str=None):
    if not ymd_str:
        kst = timezone(timedelta(hours=9))
        ymd_str = datetime.now(kst).strftime("%Y%m%d")

    clean_ymd = ymd_str.replace("-", "").strip()
    provider = (provider or "etnews").lower().strip()

    # 1. ETNews (전자신문) -> Direct PDF paper fetcher (pdf.etnews.com)
    if provider == "etnews":
        try:
            try:
                from etnews import fetch_etnews_by_date
            except ImportError:
                from api.etnews import fetch_etnews_by_date
            res = fetch_etnews_by_date(clean_ymd)
            if res and res.get("articles"):
                return res
        except Exception as e:
            print("etnews paper fetch error:", e)

    # 2. MKNews (매일경제) -> Direct MK RSS fetcher (mk.co.kr)
    elif provider == "mknews":
        try:
            try:
                from mknews import fetch_mknews_by_date
            except ImportError:
                from api.mknews import fetch_mknews_by_date
            res = fetch_mknews_by_date(clean_ymd)
            if res and res.get("articles"):
                return res
        except Exception as e:
            print("mknews paper fetch error:", e)

    # 3. Chosun (조선일보), Joongang (중앙일보), Donga (동아일보) -> Direct Official Fast RSS
    press_configs = {
        "chosun": {
            "name": "조선일보",
            "badge": "🗞️ 조선일보",
            "urls": [
                "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml",
                "https://news.google.com/rss/search?q=site:chosun.com&hl=ko&gl=KR&ceid=KR:ko"
            ]
        },
        "joongang": {
            "name": "중앙일보",
            "badge": "🏢 중앙일보",
            "urls": [
                "https://news.google.com/rss/search?q=site:joongang.co.kr&hl=ko&gl=KR&ceid=KR:ko"
            ]
        },
        "donga": {
            "name": "동아일보",
            "badge": "📰 동아일보",
            "urls": [
                "https://rss.donga.com/total.xml",
                "https://news.google.com/rss/search?q=site:donga.com&hl=ko&gl=KR&ceid=KR:ko"
            ]
        }
    }

    if provider not in press_configs:
        provider = "chosun"

    config = press_configs[provider]
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    cur_fmt_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")
    articles = []
    categorized = {}

    for url in config["urls"]:
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=4)
            if res.status_code == 200 and len(res.text) > 200:
                soup = BeautifulSoup(res.text, "xml")
                items = soup.find_all("item")
                if not items:
                    soup = BeautifulSoup(res.text, "html.parser")
                    items = soup.find_all("item")

                for idx, item in enumerate(items):
                    title = item.title.text.strip() if item.title else ""
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0].strip()
                    if not title or len(title) < 4:
                        continue

                    link = item.link.text.strip() if item.link else ""
                    desc = item.description.text.strip() if item.description else title
                    clean_desc = BeautifulSoup(desc, "html.parser").text.strip()

                    # Section categorization
                    section = "주요뉴스"
                    if any(w in title for w in ['정치', '대통령', '국회', '정당', '여당', '야당', '총리', '선거']):
                        section = "정치면"
                    elif any(w in title for w in ['경제', '금융', '증시', '주식', '금리', '부동산', '기업', '산업', '시황']):
                        section = "경제면"
                    elif any(w in title for w in ['사회', '검찰', '경찰', '법원', '사건', '사고', '교육', '복지']):
                        section = "사회면"
                    elif any(w in title for w in ['IT', 'AI', '과학', '반도체', '기술', '모바일', '통신', '로봇']):
                        section = "IT·과학면"
                    elif any(w in title for w in ['문화', '연예', '스포츠', '축구', '야구', '방송', '영화', '공연']):
                        section = "문화·스포츠면"

                    article_obj = {
                        "id": f"{provider}_{section}_{idx}",
                        "keyword": config["name"],
                        "type": "news",
                        "badge": f"{config['badge']} · {section}",
                        "publisher": config["name"],
                        "title": title,
                        "time": cur_fmt_date,
                        "url": link,
                        "content": clean_desc or title,
                        "section": section
                    }
                    articles.append(article_obj)
                    if section not in categorized:
                        categorized[section] = []
                    categorized[section].append(article_obj)

                if articles:
                    return {
                        "sections": list(categorized.keys()),
                        "categorized": categorized,
                        "articles": articles
                    }
        except Exception as e:
            print(f"Direct RSS fetch error for {provider} ({url}):", e)

    return {
        "sections": list(categorized.keys()),
        "categorized": categorized,
        "articles": articles
    }

from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        provider = params.get('provider', ['chosun'])[0]
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
