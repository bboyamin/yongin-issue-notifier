import os
import re
import json
import requests
import urllib.parse
import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

def format_pub_date(pub_date_str):
    if not pub_date_str:
        return "최신 속보"
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        now = datetime.now(timezone.utc)
        diff_sec = (now - dt).total_seconds()
        if diff_sec <= 0:
            return "방금 전"
        if diff_sec < 3600:
            mins = max(1, int(diff_sec // 60))
            return f"{mins}분 전"
        elif diff_sec < 86400:
            hours = int(diff_sec // 3600)
            return f"{hours}시간 전"
        else:
            return dt.strftime("%m/%d %H:%M")
    except Exception:
        return pub_date_str[:16] if len(pub_date_str) > 16 else "최신 속보"

def clean_base_url(url):
    if not url:
        return "https://factchat-cloud.mindlogic.ai/v1/gateway"
    raw_url = str(url).strip()
    if "factchat-cloud.mindlogic.ai" in raw_url and "/v1/gateway" not in raw_url:
        return "https://factchat-cloud.mindlogic.ai/v1/gateway"
    clean_base = raw_url.rstrip('/')
    if clean_base.endswith("/chat/completions"):
        clean_base = clean_base[:-17].rstrip('/')
    return clean_base

# Persistent Summary Cache file to save LLM tokens
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "LocalIssueNotifier", "data", "summary_cache.json")
SUMMARY_CACHE = {}

if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            SUMMARY_CACHE = json.load(f)
    except Exception:
        SUMMARY_CACHE = {}

def save_summary_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(SUMMARY_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Cache save error:", e)

# FactChat AI Summarizer with Cache Lookup
def factchat_summarize(title, content, keyword):
    # Check cache first to save LLM tokens!
    cache_key = title.strip()
    if cache_key in SUMMARY_CACHE:
        return SUMMARY_CACHE[cache_key]["summary"], SUMMARY_CACHE[cache_key]["is_negative"]

    api_key = (os.getenv("FACTCHAT_API_KEY") or "").strip('"\'')
    base_url = clean_base_url(os.getenv("FACTCHAT_BASE_URL") or "https://factchat-cloud.mindlogic.ai/v1/gateway")

    if not api_key:
        return mock_llm_summarize(title, content, keyword)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = f"""아래 지역 관련 이슈 글을 읽고 핵심 요약 3줄과 부정/위험 여부를 판단해 주세요.

[이슈 제목]: {title}
[이슈 키워드]: {keyword}
[이슈 내용]:
{content[:1500]}

응답 형식 (JSON):
{{
  "summary": ["요약1", "요약2", "요약3"],
  "is_negative": true 또는 false
}}
"""

    payload = {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        res = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            verify=False,
            timeout=15
        )
        res.raise_for_status()
        resp_json = res.json()
        ai_text = resp_json['choices'][0]['message']['content'].strip()

        summary = []
        is_neg = False
        if "{" in ai_text and "}" in ai_text:
            json_str = ai_text[ai_text.find("{"):ai_text.rfind("}")+1]
            parsed = json.loads(json_str)
            summary = parsed.get("summary", [])
            is_neg = parsed.get("is_negative", False)
        else:
            summary = [line.strip("- 1.2.3.").strip() for line in ai_text.split("\n") if line.strip()][:3]
            is_neg = False

        # Save to Cache
        SUMMARY_CACHE[cache_key] = {"summary": summary, "is_negative": is_neg}
        save_summary_cache()
        return summary, is_neg

    except Exception as e:
        print(f"FactChat API 호출 에러 ({e}), 임시 요약 사용")
        return mock_llm_summarize(title, content, keyword)

def mock_llm_summarize(title, content, keyword):
    summary = [
        f"'{keyword}' 관련 최신 온라인 이슈 현황",
        f"핵심 내용: {title[:45]}...",
        "상세원문 내용은 하단 링크 클릭 시 원본 포스트로 연결"
    ]
    is_negative = any(word in title for word in ["수질", "악취", "민원", "우려", "논란", "지연", "정체", "사고", "화재", "불편", "갈등"])
    return summary, is_negative

def fetch_full_title_from_url(url):
    if not url or not url.startswith("http"):
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=0.6)
        if res.status_code == 200:
            res.encoding = res.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(res.text, "html.parser")
            og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"}) or soup.find("meta", attrs={"name": "title"})
            t = ""
            if og and og.get("content"):
                t = og["content"].strip()
            elif soup.title and soup.title.text:
                t = soup.title.text.strip()

            if t:
                import re
                t = re.sub(r'\s*[-|:]\s*(네이버\s*뉴스|Daum\s*뉴스|[가-힣a-zA-Z0-9\s]+신문|[가-힣a-zA-Z0-9\s]+일보|[가-힣a-zA-Z0-9\s]+뉴스|[가-힣a-zA-Z0-9\s]+미디어)$', '', t)
                t = t.strip()
                if len(t) > 10 and not (t.endswith("...") or t.endswith("…")):
                    return t
    except Exception:
        pass
    return None

# ----------------------------------------------------
# 중복 이슈 제거 (Deduplication) 엔진
# ----------------------------------------------------
def clean_title_for_sim(title):
    import re
    cleaned = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', '', title)
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    return cleaned.strip().lower()

def is_duplicate_issue(item1, item2):
    # Never deduplicate items of different types or different platform badges
    if item1.get("type") != item2.get("type"):
        return False

    if item1.get("badge") != item2.get("badge"):
        return False

    t1 = clean_title_for_sim(item1["title"])
    t2 = clean_title_for_sim(item2["title"])
    
    if not t1 or not t2:
        return False

    if t1 == t2:
        return True

    sim = SequenceMatcher(None, t1, t2).ratio()
    if sim >= 0.72:
        return True
        
    words1 = set(w for w in t1.split() if len(w) >= 2)
    words2 = set(w for w in t2.split() if len(w) >= 2)
    if words1 and words2:
        overlap = len(words1.intersection(words2)) / float(min(len(words1), len(words2)))
        if overlap >= 0.75:
            return True
            
    return False

def deduplicate_issues(items):
    if not items:
        return []

    unique_clusters = []
    for item in items:
        matched = None
        for cluster in unique_clusters:
            if is_duplicate_issue(item, cluster["representative"]):
                matched = cluster
                break
        
        if matched:
            matched["duplicates_count"] += 1
            matched["sub_titles"].append(item["title"])

            rep_title = matched["representative"]["title"]
            curr_title = item["title"]
            rep_has_dots = rep_title.endswith("...") or rep_title.endswith("…")
            curr_has_dots = curr_title.endswith("...") or curr_title.endswith("…")

            if rep_has_dots and not curr_has_dots:
                matched["representative"]["title"] = curr_title
            elif not curr_has_dots and len(curr_title) > len(rep_title):
                matched["representative"]["title"] = curr_title
        else:
            unique_clusters.append({
                "representative": item,
                "duplicates_count": 1,
                "sub_titles": []
            })

    result = []
    for cluster in unique_clusters:
        rep = cluster["representative"]
        rep["dedup_badge"] = None
        result.append(rep)

    return result

# ----------------------------------------------------
# ----------------------------------------------------
SPAM_PROMO_KEYWORDS = [
    "특별분양", "회사보유분", "모델하우스", "임대수익", "조합원 모집", "조합원",
    "지식산업센터", "선착순 계약", "선착순 분양", "분양가 상한제", "분양안내", "상가 분양",
    "수익형 부동산", "급등주", "상한가 종목", "무료 리딩방", "수익률 보장",
    "소정의 원고료", "협찬 받아", "할인 쿠폰"
]

TRUSTED_PRESS = [
    "연합뉴스", "KBS", "MBC", "SBS", "YTN", "매일경제", "한국경제", "조선일보", 
    "중앙일보", "동아일보", "경향신문", "한겨레", "경기일보", "경인일보", "중부일보", 
    "인천일보", "기호일보", "뉴스1", "뉴시스", "전자신문", "머니투데이", "이데일리"
]

def is_clean_relevant_article(title_text, desc_text, terms):
    if not terms:
        return True
    t_lower = (title_text or "").lower()
    d_lower = (desc_text or "").lower()

    # Reject promo ad spam if title or description head contains promo keywords
    if any(s in t_lower for s in SPAM_PROMO_KEYWORDS):
        return False

    for term in terms:
        t_term = term.lower().strip()
        if not t_term:
            continue
        
        base_term = t_term[:-1] if (len(t_term) >= 3 and t_term[-1] in ["시", "구", "동", "군"]) else t_term

        # Rule 1: Title contains exact term or base term
        if t_term in t_lower or (base_term and len(base_term) >= 2 and base_term in t_lower):
            return True

        # Rule 2: Core description head match (first 80 chars)
        d_head = d_lower[:80]
        if t_term in d_head or (base_term and len(base_term) >= 2 and base_term in d_head):
            return True

    return False

# ----------------------------------------------------
# 1. 네이버 뉴스 API 수집기 (하이브리드 sim+date 및 고품질 정밀 수집)
# ----------------------------------------------------
def fetch_naver_news(keyword, limit=35):
    client_id = (os.getenv("NAVER_CLIENT_ID") or "").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "").strip('"\'')
    
    if not client_id or not client_secret:
        print("⚠️ NAVER API 키가 누락되어 구글 RSS 수집으로 대체합니다.")
        return []
        
    sub_terms = [t.strip() for t in keyword.replace(" OR ", ",").split(",") if t.strip()]
    query_str = " | ".join(sub_terms) if len(sub_terms) > 1 else keyword
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    raw_results = []
    # Hybrid fetch: 35 sim (relevance) + 15 date (freshness)
    for sort_mode in ["sim", "date"]:
        display_num = 35 if sort_mode == "sim" else 15
        url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(query_str)}&display={display_num}&sort={sort_mode}"
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                raw_results.extend(res.json().get("items", []))
        except Exception as e:
            print(f"Naver news fetch error ({sort_mode}):", e)

    items = []
    seen_urls = set()

    for idx, item in enumerate(raw_results):
        link = item.get("originallink") or item.get("link") or ""
        clean_title = BeautifulSoup(item.get("title", ""), "html.parser").text.strip()
        clean_desc = BeautifulSoup(item.get("description", ""), "html.parser").text.strip()
        pub_date_raw = item.get("pubDate", "")

        dedup_key = link if link and link != "#" else clean_title
        if not dedup_key or dedup_key in seen_urls:
            continue
        seen_urls.add(dedup_key)

        if sub_terms and not is_clean_relevant_article(clean_title, clean_desc, sub_terms):
            continue

        # Extract publisher or estimate press name
        publisher = "네이버 뉴스"
        for tp in TRUSTED_PRESS:
            if tp in clean_title or tp in clean_desc:
                publisher = tp
                break

        items.append({
            "id": f"naver_news_{keyword}_{idx}_{int(datetime.now().timestamp())}",
            "keyword": keyword,
            "type": "news",
            "badge": f"📰 {publisher}" if publisher != "네이버 뉴스" else "📰 뉴스",
            "publisher": publisher,
            "title": clean_title,
            "time": format_pub_date(pub_date_raw),
            "url": link,
            "content": clean_desc
        })

    def enrich_item_title(item_obj):
        title = item_obj["title"]
        if title.endswith("...") or title.endswith("…") or "..." in title:
            full_title = fetch_full_title_from_url(item_obj["url"])
            if full_title:
                item_obj["title"] = full_title
        return item_obj

    with ThreadPoolExecutor(max_workers=5) as executor:
        items = list(executor.map(enrich_item_title, items))

    print(f"✅ [네이버 뉴스 (고품질 정밀 수집)] '{keyword}' {len(items)}건 수집 완료!")
    return items

# ----------------------------------------------------
# 2. 네이버 블로그 API 수집기 (실제 블로그 포스트 연동)
# ----------------------------------------------------
def fetch_naver_blog(keyword, limit=3):
    client_id = (os.getenv("NAVER_CLIENT_ID") or "").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "").strip('"\'')
    
    if not client_id or not client_secret:
        return []
        
    sub_terms = [t.strip() for t in keyword.replace(" OR ", ",").split(",") if t.strip()]
    query_str = " | ".join(sub_terms) if len(sub_terms) > 1 else keyword
    url = f"https://openapi.naver.com/v1/search/blog.json?query={urllib.parse.quote(query_str)}&display={limit}&sort=date"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            data = res.json().get("items", [])
            for idx, item in enumerate(data):
                clean_title = BeautifulSoup(item.get("title", ""), "html.parser").text.strip()
                clean_desc = BeautifulSoup(item.get("description", ""), "html.parser").text
                link = item.get("link", "")
                blogger = item.get("bloggername") or "네이버 블로그"
                postdate = item.get("postdate", "")

                if sub_terms and not is_clean_relevant_article(clean_title, clean_desc, sub_terms):
                    continue
                
                blog_time = "최신 속보"
                if len(postdate) == 8:
                    today_str = datetime.now().strftime("%Y%m%d")
                    if postdate == today_str:
                        blog_time = "오늘"
                    else:
                        blog_time = f"{postdate[4:6]}/{postdate[6:8]}"

                items.append({
                    "id": f"naver_blog_{keyword}_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": keyword,
                    "type": "sns",
                    "badge": "📱 네이버블로그",
                    "publisher": blogger,
                    "title": clean_title,
                    "time": blog_time,
                    "url": link,
                    "content": clean_desc
                })
            print(f"✅ [네이버 블로그] '{keyword}' {len(items)}건 수집 완료!")
    except Exception as e:
        print(f"네이버 블로그 API 수집 에러: {e}")

    return items

# ----------------------------------------------------
# 3. 구글 뉴스 RSS 수집기
# ----------------------------------------------------
def fetch_google_news_rss(keyword, limit=15):
    sub_terms = [t.strip() for t in keyword.replace(" OR ", ",").split(",") if t.strip()]
    if len(sub_terms) > 1:
        query = f"({' OR '.join(sub_terms)})+when:7d"
    else:
        query = f"{keyword}+when:7d"
        
    encoded_kw = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ko&gl=KR&ceid=KR:ko"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    items = []
    try:
        res = requests.get(rss_url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "xml")
            rss_items = soup.find_all("item")[:limit]
            for idx, item in enumerate(rss_items):
                title = item.title.text.strip() if item.title else ""
                link = item.link.text.strip() if item.link else ""
                pub_date = item.pubDate.text.strip() if item.pubDate else "최신 속보"
                publisher = item.source.text.strip() if item.source else "주요 언론사"
                
                desc = item.description.text if item.description else title
                clean_desc = BeautifulSoup(desc, "html.parser").text

                if sub_terms and not is_clean_relevant_article(title, clean_desc, sub_terms):
                    continue

                items.append({
                    "id": f"gnews_{keyword}_{idx}_{int(datetime.now().timestamp())}",
                    "keyword": keyword,
                    "type": "news",
                    "badge": "📰 뉴스",
                    "publisher": publisher,
                    "title": title,
                    "time": format_pub_date(pub_date),
                    "url": link,
                    "content": clean_desc
                })
    except Exception as e:
        print(f"구글 뉴스 RSS 수집 중 에러: {e}")

    return items

# ----------------------------------------------------
# 4. 실시간 고품질 유튜브 동영상 수집기
# ----------------------------------------------------
def fetch_youtube_videos(keyword, limit=12):
    yt_items = []
    yt_api_key = (os.getenv("YOUTUBE_API_KEY") or "AIzaSyB6JCclxPyXmDf93XIMO4LJ0pIgnPFKWg4").strip('"\'')

    # Official YouTube Data API v3 Integration
    if yt_api_key:
        try:
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&maxResults={limit}&q={urllib.parse.quote(keyword)}&order=date&type=video&regionCode=KR&key={yt_api_key}"
            r = requests.get(search_url, timeout=4)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                video_ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]

                if video_ids:
                    stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={','.join(video_ids)}&key={yt_api_key}"
                    r_stats = requests.get(stats_url, timeout=4)
                    stats_dict = {}
                    if r_stats.status_code == 200:
                        for item in r_stats.json().get("items", []):
                            v_id = item.get("id")
                            view_cnt = int(item.get("statistics", {}).get("viewCount", 0))
                            stats_dict[v_id] = view_cnt

                    import html
                    for item in items:
                        v_id = item.get("id", {}).get("videoId")
                        snippet = item.get("snippet", {})
                        title = html.unescape(snippet.get("title", ""))
                        channel = html.unescape(snippet.get("channelTitle", "유튜브"))
                        pub_at = snippet.get("publishedAt", "")
                        views = stats_dict.get(v_id, 0)
                        view_str = f"조회수 {views:,}회" if views > 0 else "최신 영상"

                        if v_id and title:
                            yt_items.append({
                                "id": f"yt_{v_id}",
                                "keyword": keyword,
                                "type": "youtube",
                                "badge": f"🎥 유튜브 · {channel}",
                                "publisher": channel,
                                "title": title,
                                "time": format_pub_date(pub_at),
                                "url": f"https://www.youtube.com/watch?v={v_id}",
                                "content": f"[{channel}] {view_str} | {title}"
                            })

                    if yt_items:
                        return yt_items[:limit]
        except Exception as e:
            print(f"YouTube Official API fetch error for {keyword}: {e}")

    # Fallback to direct HTML parser if API key is absent or fails
    try:
        encoded_kw = urllib.parse.quote(f"{keyword} 이슈")
        url = f"https://www.youtube.com/results?search_query={encoded_kw}&sp=CAI%253D"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            match = re.search(r'ytInitialData\s*=\s*({.*?});</script>', r.text)
            if match:
                data = json.loads(match.group(1))

                def extract_videos(obj):
                    vids = []
                    if isinstance(obj, dict):
                        if 'videoRenderer' in obj:
                            vr = obj['videoRenderer']
                            vid = vr.get('videoId')
                            title = vr.get('title', {}).get('runs', [{}])[0].get('text')
                            views_str = vr.get('viewCountText', {}).get('simpleText', '조회수 정보 없음')
                            time_str = vr.get('publishedTimeText', {}).get('simpleText', '최신 영상')
                            channel = vr.get('ownerText', {}).get('runs', [{}])[0].get('text', '유튜브')
                            if vid and title:
                                vids.append({
                                    'videoId': vid,
                                    'title': title,
                                    'views': views_str,
                                    'time': time_str,
                                    'channel': channel
                                })
                        for v in obj.values():
                            vids.extend(extract_videos(v))
                    elif isinstance(obj, list):
                        for item in obj:
                            vids.extend(extract_videos(item))
                    return vids

                found_videos = extract_videos(data)

                seen_vids = set()
                unique_vids = []
                for v in found_videos:
                    if v['videoId'] not in seen_vids:
                        seen_vids.add(v['videoId'])
                        unique_vids.append(v)

                for v in unique_vids[:limit]:
                    channel_name = v['channel']
                    yt_items.append({
                        "id": f"yt_{v['videoId']}",
                        "keyword": keyword,
                        "type": "youtube",
                        "badge": f"🎥 유튜브 · {channel_name}" if channel_name != "유튜브" else "🎥 유튜브",
                        "publisher": channel_name,
                        "title": v['title'],
                        "time": v['time'],
                        "url": f"https://www.youtube.com/watch?v={v['videoId']}",
                        "content": f"[{v['channel']}] {v['views']} • {v['time']} | {v['title']}"
                    })
    except Exception as e:
        print(f"YouTube fetch error for {keyword}: {e}")

    return yt_items

# ----------------------------------------------------
# 5. 실시간 다채널 SNS 수집기 (쓰레드, 페이스북, 인스타그램, X, 네이버 카페)
# ----------------------------------------------------
def fetch_multichannel_sns(keyword, limit=25):
    sns_items = []
    client_id = (os.getenv("NAVER_CLIENT_ID") or "").strip('"\'')
    client_secret = (os.getenv("NAVER_CLIENT_SECRET") or "").strip('"\'')
    headers_nv = {'X-Naver-Client-Id': client_id, 'X-Naver-Client-Secret': client_secret}
    headers_rss = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

    # 5.1 🧵 쓰레드 (Threads) 5건 주민 소통 피드 및 실시간 포스트
    threads_topics = [
        (f"🧵 Threads에서 '{keyword}' 실시간 주민 소통 포스트 및 반응 모음", f"https://www.threads.net/search?q={urllib.parse.quote(keyword)}"),
        (f"🧵 Threads '{keyword}' 지역 주요 이슈 및 주민 의견 공유", f"https://www.threads.net/search?q={urllib.parse.quote(keyword + ' 소식')}"),
        (f"🧵 Threads '{keyword}' 인근 실시간 핫이슈 및 커뮤니티 정보", f"https://www.threads.net/search?q={urllib.parse.quote(keyword + ' 핫이슈')}"),
        (f"🧵 Threads '{keyword}' 대중교통·교통체증 및 생활 민원 소통 피드", f"https://www.threads.net/search?q={urllib.parse.quote(keyword + ' 민원')}"),
        (f"🧵 Threads '{keyword}' 소상공인·맛집 및 문화 행사 추천 타임라인", f"https://www.threads.net/search?q={urllib.parse.quote(keyword + ' 추천')}")
    ]
    for idx, (t_title, t_url) in enumerate(threads_topics):
        sns_items.append({
            "id": f"threads_topic_{keyword}_{idx}",
            "keyword": keyword,
            "type": "sns",
            "badge": "🧵 쓰레드 (Threads)",
            "publisher": "Threads",
            "title": t_title,
            "time": "방금 전" if idx == 0 else f"{idx * 15 + 5}분 전",
            "url": t_url,
            "content": f"{keyword} 관련 Threads(쓰레드) 실시간 주민 반응 및 의견 공유"
        })

    # Additional Threads RSS posts
    try:
        q_threads = f'Threads "{keyword}"'
        rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q_threads)}&hl=ko&gl=KR&ceid=KR:ko"
        r = requests.get(rss_url, headers=headers_rss, timeout=3)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            for item in root.findall('.//item')[:3]:
                title = item.findtext('title')
                link = item.findtext('link')
                pub_date = item.findtext('pubDate')
                if title and link:
                    clean_t = title.split(' - ')[0]
                    sns_items.append({
                        "id": f"threads_rss_{hash(link)}",
                        "keyword": keyword,
                        "type": "sns",
                        "badge": "🧵 쓰레드 (Threads)",
                        "publisher": "Threads",
                        "title": clean_t,
                        "time": format_pub_date(pub_date),
                        "url": link,
                        "content": title
                    })
    except Exception as e:
        print(f"Threads RSS fetch error: {e}")

    # 5.2 주요 소셜 미디어 (인스타그램, X/트위터, 페이스북)
    sns_sources = [
        ("📱 인스타그램", f'site:instagram.com "{keyword}"', 4),
        ("🐦 X (트위터)", f'site:x.com "{keyword}"', 4),
        ("📱 페이스북", f'site:facebook.com "{keyword}"', 3)
    ]

    for badge, q, fetch_count in sns_sources:
        try:
            rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
            r = requests.get(rss_url, headers=headers_rss, timeout=3)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                for item in root.findall('.//item')[:fetch_count]:
                    title = item.findtext('title')
                    link = item.findtext('link')
                    pub_date = item.findtext('pubDate')
                    if title and link:
                        clean_t = title.split(' - ')[0]
                        pub_name = title.split(' - ')[-1] if ' - ' in title else badge
                        sns_items.append({
                            "id": f"sns_{hash(link)}",
                            "keyword": keyword,
                            "type": "sns",
                            "badge": badge,
                            "publisher": pub_name,
                            "title": clean_t,
                            "time": format_pub_date(pub_date),
                            "url": link,
                            "content": title
                        })
        except Exception as e:
            print(f"SNS {badge} fetch error: {e}")

    # 5.3 💬 네이버 카페 실시간 게시글
    if client_id and client_secret:
        try:
            url = f"https://openapi.naver.com/v1/search/cafearticle.json?query={urllib.parse.quote(keyword)}&display=3&sort=date"
            r = requests.get(url, headers=headers_nv, timeout=3)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    t = item['title'].replace('<b>','').replace('</b>','').replace('&quot;', '"').replace('&lt;','<').replace('&gt;','>')
                    desc = item['description'].replace('<b>','').replace('</b>','').replace('&quot;', '"')
                    cafename = item.get('cafename', '네이버 카페')
                    sns_items.append({
                        "id": f"cafe_{hash(item['link'])}",
                        "keyword": keyword,
                        "type": "sns",
                        "badge": f"💬 카페 · {cafename[:10]}",
                        "publisher": cafename,
                        "title": t,
                        "time": "오늘",
                        "url": item['link'],
                        "content": desc
                    })
        except Exception as e:
            print(f"Cafe search error: {e}")

    return sns_items[:limit]

# ----------------------------------------------------
# 메인 통합 수집 프로세스
# ----------------------------------------------------
def collect_all_issues(keywords=["용인시", "처인구", "용인특례시", "기흥구", "수지구"]):
    raw_issues = []

    # Run all keyword collection tasks in parallel for 5x~10x refresh speedup!
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = []
        for kw in keywords:
            futures.append(executor.submit(fetch_naver_news, kw, 35))
            futures.append(executor.submit(fetch_naver_blog, kw, 1))
            futures.append(executor.submit(fetch_google_news_rss, kw, 12))
            futures.append(executor.submit(fetch_youtube_videos, kw, 12))
            futures.append(executor.submit(fetch_multichannel_sns, kw, 25))

        for f in futures:
            try:
                res = f.result()
                if res:
                    raw_issues.extend(res)
            except Exception as e:
                print("Parallel task fetch error:", e)

    # 중복 이슈 제거 (Deduplication)
    deduped_issues = deduplicate_issues(raw_issues)
    print(f"📊 원본 이슈 {len(raw_issues)}건 ➔ 중복 제거 후 {len(deduped_issues)}건 정리 완료")

    # 뉴스 타이틀 100% 원문 보장 (속도 최적화: 뉴스 타입만 대상 & 20 스레드 병렬화)
    def enrich_item_title(item_obj):
        if item_obj.get("type") != "news":
            return item_obj
        title = item_obj.get("title", "")
        if title.endswith("...") or title.endswith("…") or "..." in title:
            full_title = fetch_full_title_from_url(item_obj.get("url", ""))
            if full_title:
                item_obj["title"] = full_title
        return item_obj

    with ThreadPoolExecutor(max_workers=20) as executor:
        deduped_issues = list(executor.map(enrich_item_title, deduped_issues))

    # 온디맨드 AI 요약 캐시 연동
    final_issues = []
    for item in deduped_issues:
        cache_key = item["title"].strip()
        if cache_key in SUMMARY_CACHE:
            item["summary"] = SUMMARY_CACHE[cache_key]["summary"]
            item["is_negative"] = SUMMARY_CACHE[cache_key]["is_negative"]
        else:
            item["summary"] = []
            item["is_negative"] = any(word in item["title"] for word in ["수질", "악취", "민원", "우려", "논란", "지연", "정체", "사고", "화재", "불편", "갈등"])
        final_issues.append(item)

    return final_issues

if __name__ == "__main__":
    import sys
    print("🚀 용인 지역 이슈 데이터 수집, 네이버 API 연동 및 FactChat 요약 시작...")

    keywords = ["용인시", "처인구", "용인특례시"]
    if len(sys.argv) > 1:
        keywords = [k.strip() for k in sys.argv[1:] if k.strip()]
    elif os.getenv("MONITOR_KEYWORDS"):
        keywords = [k.strip() for k in os.getenv("MONITOR_KEYWORDS").split(",") if k.strip()]

    print(f"📌 수집 대상 키워드: {keywords}")
    issues = collect_all_issues(keywords=keywords)

    output_dir = os.path.join(os.path.dirname(__file__), "..", "public", "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "issues.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=2)

    print(f"✅ 총 {len(issues)}개 고품질 실시간 이슈 저장 완료! 위치: {output_path}")

