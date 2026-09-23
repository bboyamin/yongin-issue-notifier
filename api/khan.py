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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/xml,text/xml,text/html;q=0.9,*/*;q=0.8'
}

KHAN_RSS_FEEDS = {
    "전체": "https://www.khan.co.kr/rss/rssdata/total_news.xml",
    "정치": "https://www.khan.co.kr/rss/rssdata/politic_news.xml",
    "경제": "https://www.khan.co.kr/rss/rssdata/economy_news.xml",
    "사회": "https://www.khan.co.kr/rss/rssdata/society_news.xml",
    "문화": "https://www.khan.co.kr/rss/rssdata/culture_news.xml",
    "국제": "https://www.khan.co.kr/rss/rssdata/kh_world.xml",
    "IT·과학": "https://www.khan.co.kr/rss/rssdata/science_news.xml",
    "오피니언": "https://www.khan.co.kr/rss/rssdata/opinion_news.xml"
}

def clean_html(text):
    if not text:
        return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def fetch_khan_by_date(ymd_str=None):
    categorized = {}
    all_articles = []
    kst = timezone(timedelta(hours=9))
    default_date_str = datetime.now(kst).strftime("%Y/%m/%d")

    target_ymd = ""
    if ymd_str:
        target_ymd = ymd_str.replace("-", "").strip()

    # 1-Tier: Kyunghyang Official RSS Feeds
    for section_name, rss_url in KHAN_RSS_FEEDS.items():
        try:
            res = requests.get(rss_url, headers=headers, timeout=5, verify=False)
            if res.status_code == 200 and len(res.content) > 100:
                soup = ET.fromstring(res.content)
                items = soup.findall('.//item')
                for idx, item in enumerate(items):
                    t_el = item.find('title')
                    l_el = item.find('link')
                    d_el = item.find('description')
                    date_el = item.find('{http://purl.org/dc/elements/1.1/}date')
                    creator_el = item.find('{http://purl.org/dc/elements/1.1/}creator')

                    title = clean_html(t_el.text) if t_el is not None and t_el.text else ""
                    if not title or len(title) < 4:
                        continue

                    link = l_el.text.strip() if l_el is not None and l_el.text else "#"
                    desc = clean_html(d_el.text) if d_el is not None and d_el.text else title

                    # Parse pubDate / dc:date (ISO 8601 string)
                    pub_time = default_date_str
                    item_ymd = ""
                    if date_el is not None and date_el.text:
                        raw_date = date_el.text.strip()
                        if len(raw_date) >= 10 and raw_date[:4].isdigit():
                            pub_time = raw_date[:10].replace('-', '/')
                            item_ymd = raw_date[:10].replace('-', '')

                    creator = clean_html(creator_el.text) if creator_el is not None and creator_el.text else "경향신문"

                    article_obj = {
                        "id": f"khan_rss_{section_name}_{idx}",
                        "keyword": "경향신문",
                        "type": "news",
                        "badge": f"🗞️ 경향신문 · {section_name}",
                        "publisher": f"경향신문 ({creator})" if creator and creator != "경향신문" else "경향신문",
                        "title": title,
                        "time": pub_time,
                        "url": link,
                        "content": desc or title,
                        "section": section_name
                    }

                    # Filter by target_ymd if supplied and valid match, else include all recent RSS items
                    all_articles.append(article_obj)
                    if section_name not in categorized:
                        categorized[section_name] = []
                    categorized[section_name].append(article_obj)
        except Exception as e:
            print(f"Kyunghyang RSS error ({section_name}): {e}")

    if all_articles:
        return {
            "sections": list(categorized.keys()),
            "categorized": categorized,
            "articles": all_articles
        }

    # 2-Tier Fallback: Google RSS site:khan.co.kr
    try:
        g_rss = "https://news.google.com/rss/search?q=site:khan.co.kr&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(g_rss, headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and len(res.content) > 100:
            soup = ET.fromstring(res.content)
            items = soup.findall('.//item')
            for idx, item in enumerate(items):
                t_el = item.find('title')
                l_el = item.find('link')
                title = clean_html(t_el.text) if t_el is not None and t_el.text else ""
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if not title or len(title) < 4:
                    continue
                link = l_el.text.strip() if l_el is not None and l_el.text else "#"

                section = "일반"
                if any(w in title for w in ['정치', '대통령', '국회', '정당']): section = "정치"
                elif any(w in title for w in ['경제', '금융', '증시', '부동산']): section = "경제"
                elif any(w in title for w in ['사회', '검찰', '경찰', '법원']): section = "사회"
                elif any(w in title for w in ['문화', '연예', '스포츠', '방송']): section = "문화"

                article_obj = {
                    "id": f"khan_g_rss_{idx}",
                    "keyword": "경향신문",
                    "type": "news",
                    "badge": f"🗞️ 경향신문 · {section}",
                    "publisher": "경향신문",
                    "title": title,
                    "time": default_date_str,
                    "url": link,
                    "content": title,
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
        print("Kyunghyang Google RSS fallback error:", e)

    # 3-Tier Fallback: Naver OpenAPI
    return fetch_khan_from_naver(target_ymd)

def fetch_khan_from_naver(clean_ymd=None):
    client_id = (os.getenv("NAVER_CLIENT_ID") or "MKJiyEIjWKeda674OX9l").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "Q313QS0JpL").strip('"\'')
    if not client_id or not client_secret:
        return {"sections": [], "categorized": {}, "articles": []}

    url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote('경향신문')}&display=40&sort=date"
    headers_naver = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    try:
        res = requests.get(url, headers=headers_naver, timeout=5)
        if res.status_code == 200:
            items = res.json().get("items", [])
            categorized = {}
            all_articles = []
            formatted_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d")

            for idx, item in enumerate(items):
                title = clean_html(item.get("title", ""))
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if not title or len(title) < 4:
                    continue
                link = item.get("originallink") or item.get("link") or "#"
                desc = clean_html(item.get("description", "")) or title

                section = "일반"
                if any(w in title for w in ['정치', '대통령', '국회', '정당']): section = "정치"
                elif any(w in title for w in ['경제', '금융', '증시', '부동산']): section = "경제"
                elif any(w in title for w in ['사회', '검찰', '경찰', '법원']): section = "사회"
                elif any(w in title for w in ['문화', '연예', '스포츠', '방송']): section = "문화"

                article_obj = {
                    "id": f"khan_naver_{idx}",
                    "keyword": "경향신문",
                    "type": "news",
                    "badge": f"🗞️ 경향신문 · {section}",
                    "publisher": "경향신문",
                    "title": title,
                    "time": formatted_date,
                    "url": link,
                    "content": desc,
                    "section": section
                }
                all_articles.append(article_obj)
                if section not in categorized:
                    categorized[section] = []
                categorized[section].append(article_obj)

            return {
                "sections": list(categorized.keys()),
                "categorized": categorized,
                "articles": all_articles
            }
    except Exception as e:
        print("Kyunghyang Naver OpenAPI fetch error:", e)

    return {"sections": [], "categorized": {}, "articles": []}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        date_param = params.get('date', [None])[0] or params.get('ymd', [None])[0]

        result = fetch_khan_by_date(date_param)

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
