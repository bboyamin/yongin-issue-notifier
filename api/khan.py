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
from concurrent.futures import ThreadPoolExecutor

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

def fetch_single_feed(item_tuple):
    section_name, rss_url = item_tuple
    articles = []
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
                if "khan.co.kr" in link and "?" in link:
                    link = link.split("?")[0]
                desc = clean_html(d_el.text) if d_el is not None and d_el.text else title

                kst = timezone(timedelta(hours=9))
                pub_time = datetime.now(kst).strftime("%Y/%m/%d")
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
                    "section": section_name,
                    "item_ymd": item_ymd
                }
                articles.append(article_obj)
    except Exception as e:
        print(f"Kyunghyang RSS feed fetch error ({section_name}):", e)
    return section_name, articles

def categorize_khan_title(t):
    if any(k in t for k in ['정치', '대통령', '국회', '정당', '청와대', '외교', '총리', '장관', '의원', '특검', '계엄', '북한', '통일', '군', 'DMZ']):
        return "정치"
    elif any(k in t for k in ['경제', '금융', '증시', '부동산', '기업', '주식', '은행', '배당', '환율', '금리', '물가', '수출', '무역', '자산']):
        return "경제"
    elif any(k in t for k in ['사회', '검찰', '경찰', '법원', '사건', '수사', '노동', '교육', '복지', '환경']):
        return "사회"
    elif any(k in t for k in ['문화', '연예', '스포츠', '방송', '영화', '공연', '전시', '배우', '가수', '예능', '올림픽', '아시안게임', '선수', '축구', '야구', '골프']):
        return "문화"
    elif any(k in t for k in ['IT', '과학', 'AI', '반도체', '통신', '스마트폰', '우주', '기술']):
        return "IT·과학"
    elif any(k in t for k in ['사설', '칼럼', '오피니언', '시선', '기고', '그림마당', '아침을']):
        return "오피니언"
    return "전체"

def fetch_khan_past_q(q):
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        if res.status_code == 200 and len(res.content) > 100:
            soup = ET.fromstring(res.content)
            return soup.findall('.//item')
    except Exception:
        pass
    return []

def fetch_past_khan(clean_ymd):
    try:
        dt = datetime.strptime(clean_ymd, "%Y%m%d")
        dt_next = dt + timedelta(days=1)
        after_str = dt.strftime("%Y-%m-%d")
        before_str = dt_next.strftime("%Y-%m-%d")
        formatted_date = dt.strftime("%Y/%m/%d")

        queries = [
            f"site:khan.co.kr after:{after_str} before:{before_str}",
            f"site:khan.co.kr (정치 OR 사회 OR 정부 OR 국회 OR 북한 OR 외교) after:{after_str} before:{before_str}",
            f"site:khan.co.kr (경제 OR 금융 OR 금리 OR 환율 OR 증시 OR 주식 OR 부동산) after:{after_str} before:{before_str}",
            f"site:khan.co.kr (문화 OR 스포츠 OR 연예 OR 오피니언 OR 사설 OR 칼럼) after:{after_str} before:{before_str}",
            f"site:khan.co.kr (IT OR 과학 OR AI OR 반도체) after:{after_str} before:{before_str}"
        ]

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(fetch_khan_past_q, queries))

        dedup_items = {}
        for items in results:
            for item in items:
                t_el = item.find('title')
                l_el = item.find('link')
                title = clean_html(t_el.text) if t_el is not None and t_el.text else ""
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                link = l_el.text.strip() if l_el is not None and l_el.text else ""
                if link and title and len(title) >= 4:
                    dedup_items[link] = title

        categorized = {}
        all_articles = []
        for idx, (link, title) in enumerate(dedup_items.items()):
            section = categorize_khan_title(title)
            article_obj = {
                "id": f"khan_past_{clean_ymd}_{idx}",
                "keyword": "경향신문",
                "type": "news",
                "badge": f"🗞️ 경향신문 · {section}",
                "publisher": "경향신문",
                "title": title,
                "time": formatted_date,
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
        print(f"Kyunghyang past date fetch error ({clean_ymd}):", e)

    return fetch_khan_from_naver(clean_ymd)

def fetch_khan_by_date(ymd_str=None):
    kst = timezone(timedelta(hours=9))
    today_ymd = datetime.now(kst).strftime("%Y%m%d")

    clean_ymd = ""
    if ymd_str:
        clean_ymd = ymd_str.replace("-", "").strip()

    is_past_date = bool(clean_ymd and clean_ymd != today_ymd)

    # 1. Today or default -> Concurrent fetch of official RSS Feeds
    if not is_past_date:
        categorized = {}
        all_articles = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = executor.map(fetch_single_feed, KHAN_RSS_FEEDS.items())
            for section_name, articles in results:
                if articles:
                    categorized[section_name] = articles
                    all_articles.extend(articles)

        if all_articles:
            return {
                "sections": list(categorized.keys()),
                "categorized": categorized,
                "articles": all_articles
            }

    # 2. Past Date requested -> Fetch specific past date news
    if is_past_date:
        past_res = fetch_past_khan(clean_ymd)
        if past_res and past_res.get("articles"):
            return past_res

    # Fallback: Naver OpenAPI
    return fetch_khan_from_naver(clean_ymd or today_ymd)

def fetch_khan_from_naver(clean_ymd=None):
    client_id = (os.getenv("NAVER_CLIENT_ID") or "MKJiyEIjWKeda674OX9l").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "Q313QS0JpL").strip('"\'')
    if not client_id or not client_secret:
        return {"sections": [], "categorized": {}, "articles": []}

    url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote('경향신문')}&display=50&sort=date"
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
            if clean_ymd and len(clean_ymd) == 8:
                try:
                    formatted_date = datetime.strptime(clean_ymd, "%Y%m%d").strftime("%Y/%m/%d")
                except Exception:
                    pass

            for idx, item in enumerate(items):
                title = clean_html(item.get("title", ""))
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                if not title or len(title) < 4:
                    continue
                link = item.get("originallink") or item.get("link") or "#"
                desc = clean_html(item.get("description", "")) or title

                section = categorize_khan_title(title)

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
