from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os
import requests
import urllib3
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/xml,text/xml,text/html;q=0.9,*/*;q=0.8'
}

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def fetch_chosun_sections():
    sections_list = [
        ("종합", "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml"),
        ("정치", "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/?outputType=xml"),
        ("경제", "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
        ("사회", "https://www.chosun.com/arc/outboundfeeds/rss/category/national/?outputType=xml"),
        ("문화·스포츠", "https://www.chosun.com/arc/outboundfeeds/rss/category/sports/?outputType=xml")
    ]
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
                        "id": f"chosun_{section_title}_{idx}",
                        "keyword": "조선일보",
                        "type": "news",
                        "badge": f"🗞️ 조선일보 · {section_title}",
                        "publisher": "조선일보",
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
            print(f"Chosun RSS section ({section_title}) fetch error: {e}")

    return {
        "sections": list(categorized.keys()),
        "categorized": categorized,
        "articles": all_articles
    }

def fetch_chosun_past_date(ymd_str):
    try:
        dt = datetime.strptime(ymd_str, "%Y%m%d")
        dt_next = dt + timedelta(days=1)
        after_str = dt.strftime("%Y-%m-%d")
        before_str = dt_next.strftime("%Y-%m-%d")
        formatted_date = dt.strftime("%Y/%m/%d")

        rss_url = f"https://news.google.com/rss/search?q=site:chosun.com+after:{after_str}+before:{before_str}&hl=ko&gl=KR&ceid=KR:ko"
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
                    "id": f"chosun_past_{ymd_str}_{idx}",
                    "keyword": "조선일보",
                    "type": "news",
                    "badge": f"🗞️ 조선일보 · {section}",
                    "publisher": "조선일보",
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
        print(f"Chosun past date ({ymd_str}) RSS fetch error: {e}")

    return None

def fetch_chosun_by_date(ymd_str):
    kst = timezone(timedelta(hours=9))
    today_ymd = datetime.now(kst).strftime("%Y%m%d")

    if not ymd_str:
        ymd_str = today_ymd

    clean_ymd = ymd_str.replace("-", "").strip()

    if clean_ymd != today_ymd:
        past_res = fetch_chosun_past_date(clean_ymd)
        if past_res and past_res.get("articles"):
            return past_res

    res = fetch_chosun_sections()
    if res and res.get("articles"):
        return res

    return fetch_chosun_past_date(clean_ymd) or {"sections": [], "categorized": {}, "articles": []}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]
        if not date_param:
            kst = timezone(timedelta(hours=9))
            date_param = datetime.now(kst).strftime("%Y%m%d")

        result = fetch_chosun_by_date(date_param)

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
