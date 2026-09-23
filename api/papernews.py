import os
import sys
import json
import urllib.parse
import requests
import urllib3
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ensure api directory is in python module path for Vercel
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/xml,text/xml,text/html;q=0.9,*/*;q=0.8'
}

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def fetch_rss_sections(sections_list, publisher_name, badge_prefix, provider_key):
    categorized = {}
    all_articles = []
    formatted_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")

    for section_title, rss_url in sections_list:
        try:
            res = requests.get(rss_url, headers=headers, timeout=4, verify=False)
            if res.status_code == 200 and len(res.content) > 200:
                root = ET.fromstring(res.content)
                items = root.findall('.//item')[:25]
                sec_articles = []

                for idx, item in enumerate(items):
                    t_el = item.find('title')
                    l_el = item.find('link')
                    d_el = item.find('description')

                    title = clean_html(t_el.text) if t_el is not None and t_el.text else ""
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0].strip()
                    if not title or len(title) < 4:
                        continue

                    link = l_el.text.strip() if l_el is not None and l_el.text else "#"
                    desc = clean_html(d_el.text) if d_el is not None and d_el.text else title

                    article_obj = {
                        "id": f"{provider_key}_{section_title}_{idx}",
                        "keyword": publisher_name,
                        "type": "news",
                        "badge": f"{badge_prefix} · {section_title}",
                        "publisher": publisher_name,
                        "title": title,
                        "time": formatted_date,
                        "url": link,
                        "content": desc or title,
                        "section": section_title
                    }
                    sec_articles.append(article_obj)
                    all_articles.append(article_obj)

                if sec_articles:
                    categorized[section_title] = sec_articles
        except Exception as e:
            print(f"Direct RSS section ({section_title}) fetch error: {e}")

    return {
        "sections": list(categorized.keys()),
        "categorized": categorized,
        "articles": all_articles
    }

def fetch_past_date_rss(domain, publisher_name, badge_prefix, provider_key, ymd_str):
    try:
        dt = datetime.strptime(ymd_str, "%Y%m%d")
        dt_next = dt + timedelta(days=1)
        after_str = dt.strftime("%Y-%m-%d")
        before_str = dt_next.strftime("%Y-%m-%d")
        formatted_date = dt.strftime("%Y/%m/%d")

        rss_url = f"https://news.google.com/rss/search?q=site:{domain}+after:{after_str}+before:{before_str}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and len(res.content) > 200:
            root = ET.fromstring(res.content)
            items = root.findall('.//item')
            categorized = {}
            all_articles = []

            for idx, item in enumerate(items):
                t_el = item.find('title')
                l_el = item.find('link')
                d_el = item.find('description')

                title = clean_html(t_el.text) if t_el is not None and t_el.text else ""
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if not title or len(title) < 4:
                    continue

                link = l_el.text.strip() if l_el is not None and l_el.text else "#"
                desc = clean_html(d_el.text) if d_el is not None and d_el.text else title

                section = "종합"
                if any(w in title for w in ['정치', '대통령', '국회', '정당', '여당', '야당']): section = "정치"
                elif any(w in title for w in ['경제', '금융', '증시', '주식', '금리', '부동산', '기업']): section = "경제"
                elif any(w in title for w in ['사회', '검찰', '경찰', '법원', '사건', '사고']): section = "사회"
                elif any(w in title for w in ['IT', 'AI', '과학', '반도체', '기술']): section = "IT·과학"
                elif any(w in title for w in ['문화', '연예', '스포츠', '축구', '야구', '방송']): section = "문화·스포츠"

                article_obj = {
                    "id": f"{provider_key}_past_{ymd_str}_{idx}",
                    "keyword": publisher_name,
                    "type": "news",
                    "badge": f"{badge_prefix} · {section}",
                    "publisher": publisher_name,
                    "title": title,
                    "time": formatted_date,
                    "url": link,
                    "content": desc or title,
                    "section": section
                }
                all_articles.append(article_obj)
                if section not in categorized:
                    categorized[section] = []
                categorized[section].append(article_obj)

            if all_articles:
                return {
                    "sections": list(categorized.keys()),
                    "categorized": categorized,
                    "articles": all_articles
                }
    except Exception as e:
        print(f"Past date ({ymd_str}) RSS fetch error for {provider_key}: {e}")

    return None

def fetch_paper_news(provider="etnews", ymd_str=None):
    kst = timezone(timedelta(hours=9))
    today_ymd = datetime.now(kst).strftime("%Y%m%d")

    if not ymd_str:
        ymd_str = today_ymd

    clean_ymd = ymd_str.replace("-", "").strip()
    provider = (provider or "etnews").lower().strip()

    # 1. ETNews (전자신문)
    if provider == "etnews":
        try:
            try:
                from etnews import fetch_etnews_by_date
            except ImportError:
                from api.etnews import fetch_etnews_by_date
            return fetch_etnews_by_date(clean_ymd)
        except Exception as e:
            print("etnews paper fetch error:", e)

    # 2. MKNews (매일경제)
    elif provider == "mknews":
        try:
            try:
                from mknews import fetch_mknews_by_date
            except ImportError:
                from api.mknews import fetch_mknews_by_date
            return fetch_mknews_by_date(clean_ymd)
        except Exception as e:
            print("mknews paper fetch error:", e)

    # 3. Chosun (조선일보)
    elif provider == "chosun":
        if clean_ymd != today_ymd:
            past_res = fetch_past_date_rss("chosun.com", "조선일보", "🗞️ 조선일보", "chosun", clean_ymd)
            if past_res and past_res.get("articles"):
                return past_res

        sections = [
            ("종합", "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml"),
            ("정치", "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/?outputType=xml"),
            ("경제", "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
            ("사회", "https://www.chosun.com/arc/outboundfeeds/rss/category/national/?outputType=xml"),
            ("문화·스포츠", "https://www.chosun.com/arc/outboundfeeds/rss/category/sports/?outputType=xml")
        ]
        return fetch_rss_sections(sections, "조선일보", "🗞️ 조선일보", "chosun")

    # 4. Donga (동아일보)
    elif provider == "donga":
        if clean_ymd != today_ymd:
            past_res = fetch_past_date_rss("donga.com", "동아일보", "📰 동아일보", "donga", clean_ymd)
            if past_res and past_res.get("articles"):
                return past_res

        sections = [
            ("종합", "https://rss.donga.com/total.xml"),
            ("정치", "https://rss.donga.com/politics.xml"),
            ("경제", "https://rss.donga.com/economy.xml"),
            ("사회", "https://rss.donga.com/national.xml"),
            ("문화·스포츠", "https://rss.donga.com/sports.xml")
        ]
        return fetch_rss_sections(sections, "동아일보", "📰 동아일보", "donga")

    # 5. Joongang (중앙일보)
    elif provider == "joongang":
        return fetch_past_date_rss("joongang.co.kr", "중앙일보", "🏢 중앙일보", "joongang", clean_ymd) or {
            "sections": [], "categorized": {}, "articles": []
        }

    return {
        "sections": [],
        "categorized": {},
        "articles": []
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
