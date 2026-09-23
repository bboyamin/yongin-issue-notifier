import os
import re
import json
import requests
import urllib.parse
import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

def format_pub_date(pub_date_str):
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    fallback = kst_now.strftime("%Y-%m-%d %H:%M:%S")

    if not pub_date_str:
        return fallback

    # Handle RFC2822 pubDate (e.g. Naver News, RSS)
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        if dt:
            kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
            return kst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle ISO datetime strings
    try:
        if "T" in pub_date_str:
            clean_str = pub_date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt:
                kst_dt = dt.astimezone(timezone(timedelta(hours=9)))
                return kst_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle 8-digit date string
    try:
        if len(pub_date_str) == 8 and pub_date_str.isdigit():
            return f"{pub_date_str[:4]}-{pub_date_str[4:6]}-{pub_date_str[6:8]} 09:00:00"
    except Exception:
        pass

    # Extract YYYY-MM-DD HH:MM:SS if embedded
    try:
        m = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})\s+(\d{2}):(\d{2}):?(\d{2})?', pub_date_str)
        if m:
            sec = m.group(6) if m.group(6) else "00"
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{sec}"
    except Exception:
        pass

    return fallback

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

    prompt = f"""아래 지역 관련 뉴스/보도자료 글을 읽고 핵심 내용과 주요 팩트를 명확하게 요약해 주세요.

[이슈 제목]: {title}
[이슈 키워드]: {keyword}
[이슈 내용]:
{content[:1500]}

작성 지침:
1. 형식적인 문장 늘리기를 피하고, 기사의 핵심 내용, 주요 수치/일정/장소, 주요 영향/반응 등 가장 핵심적인 팩트 위주로 2~4개 포인트를 정리해 주세요.
2. 공무원 및 시청 직원들이 보기에 명확하고 직관적인 어조로 작성해 주세요.

응답 형식 (JSON):
{{
  "summary": ["핵심 포인트1", "핵심 포인트2", "핵심 포인트3"],
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
            summary = [line.strip("- 1.2.3.").strip() for line in ai_text.split("\n") if line.strip()][:4]
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
        f"'{keyword}' 관련 주요 언론 보도 내용",
        f"핵심 제목: {title[:50]}",
        "상세 세부내용 및 원문 팩트는 하단 [원문 보기] 버튼을 참고해 주세요."
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

DOMAIN_PRESS_MAP = {
    "siminilbo.co.kr": "시민일보",
    "cfnews.kr": "CF뉴스",
    "nspna.com": "NSP통신",
    "kbmaeil.com": "경북매일",
    "pointdaily.co.kr": "포인트데일리",
    "sportsseoul.com": "스포츠서울",
    "weekly.hankooki.com": "주간한국",
    "gukjenews.com": "국제뉴스",
    "tf.co.kr": "더팩트",
    "newsprime.co.kr": "프라임경제",
    "sisaon.co.kr": "시사오늘",
    "inews24.com": "아이뉴스24",
    "newspim.com": "뉴스핌",
    "etoday.co.kr": "이투데이",
    "ajunews.com": "아주뉴스",
    "yna.co.kr": "연합뉴스",
    "kbs.co.kr": "KBS",
    "imbc.com": "MBC",
    "sbs.co.kr": "SBS",
    "ytn.co.kr": "YTN",
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "chosun.com": "조선일보",
    "donga.com": "동아일보",
    "joongang.co.kr": "중앙일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "kyeonggi.com": "경기일보",
    "kyeongin.com": "경인일보",
    "joongboo.com": "중부일보",
    "incheonilbo.com": "인천일보",
    "kyeongho.com": "기호일보",
    "news1.kr": "뉴스1",
    "newsis.com": "뉴시스",
    "etnews.com": "전자신문",
    "mt.co.kr": "머니투데이",
    "edaily.co.kr": "이데일리",
    "dt.co.kr": "디지털타임스",
    "heraldcorp.com": "헤럴드경제",
    "fnnews.com": "파이낸셜뉴스",
    "segye.com": "세계일보",
    "seoul.co.kr": "서울신문",
    "kmib.co.kr": "국민일보",
    "munhwa.com": "문화일보",
    "nocutnews.co.kr": "노컷뉴스",
    "asiae.co.kr": "아시아경제",
    "sedaily.com": "서울경제",
    "biz.chosun.com": "조선비즈",
    "newstown.co.kr": "뉴스타운",
    "breaknews.com": "브레이크뉴스",
    "sportsworldi.com": "스포츠월드",
    "sports.chosun.com": "스포츠조선",
    "sports.khan.co.kr": "스포츠경향"
}

TRUSTED_PRESS = [
    "연합뉴스", "KBS", "MBC", "SBS", "YTN", "매일경제", "한국경제", "조선일보", 
    "중앙일보", "동아일보", "경향신문", "한겨레", "경기일보", "경인일보", "중부일보", 
    "인천일보", "기호일보", "뉴스1", "뉴시스", "전자신문", "머니투데이", "이데일리",
    "시민일보", "NSP통신", "스포츠서울", "경북매일", "포인트데일리", "아주뉴스"
]

def extract_press_name(url, title_text, desc_text):
    if url:
        netloc = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
        for domain, press in DOMAIN_PRESS_MAP.items():
            if domain in netloc:
                return press
        # Clean host fallback if not in dictionary
        host_part = netloc.split(".")[0]
        if host_part and len(host_part) >= 3 and host_part not in ["news", "article", "m", "blog"]:
            return host_part.upper()

    for tp in TRUSTED_PRESS:
        if tp in title_text or tp in desc_text:
            return tp
    if " - " in title_text:
        parts = title_text.rsplit(" - ", 1)
        if len(parts[1].strip()) <= 12:
            return parts[1].strip()
    return "뉴스"

def is_clean_relevant_article(title_text, desc_text, terms):
    if not terms:
        return True
    t_lower = (title_text or "").lower()
    d_lower = (desc_text or "").lower()

    # Reject promo ad spam if title or description contains promo keywords
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

        # Rule 2: Full description snippet match
        if t_term in d_lower or (base_term and len(base_term) >= 2 and base_term in d_lower):
            return True

    return False

# ----------------------------------------------------
# 1. 네이버 뉴스 API 수집기 (하이브리드 sim+date 및 고품질 정밀 수집)
# ----------------------------------------------------
def fetch_naver_news(keyword, limit=50):
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
    # Freshness Priority: 50 items sorted by date (newest first) + 10 items sorted by sim (relevance)
    for sort_mode in ["date", "sim"]:
        display_num = 50 if sort_mode == "date" else 10
        url = f"https://openapi.naver.com/v1/search/news.json?query={urllib.parse.quote(query_str)}&display={display_num}&sort={sort_mode}"
        try:
            res = requests.get(url, headers=headers, timeout=3.0)
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
        publisher = extract_press_name(link, clean_title, clean_desc)

        items.append({
            "id": f"naver_news_{keyword}_{idx}_{int(datetime.now().timestamp())}",
            "keyword": keyword,
            "type": "news",
            "badge": f"📰 {publisher}",
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

    if os.getenv("VERCEL") != "1":
        with ThreadPoolExecutor(max_workers=5) as executor:
            items = list(executor.map(enrich_item_title, items))

    print(f"✅ [네이버 뉴스 (고품질 정밀 수집)] '{keyword}' {len(items)}건 수집 완료!")
    return items

def fetch_korea_kr_rss(limit=100):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    DEPT_MAP = [
        ('기획재정부', ['기획재정부', '기재부', '재정경제부']),
        ('국토교통부', ['국토교통부', '국토부']),
        ('행정안전부', ['행정안전부', '행안부']),
        ('보건복지부', ['보건복지부', '복지부']),
        ('과학기술정보통신부', ['과학기술정보통신부', '과기정통부', '과기부']),
        ('산업통상자원부', ['산업통상자원부', '산업부', '산자부']),
        ('환경부', ['환경부']),
        ('고용노동부', ['고용노동부', '노동부']),
        ('여성가족부', ['여성가족부', '여가부']),
        ('해양수산부', ['해양수산부', '해수부']),
        ('중소벤처기업부', ['중소벤처기업부', '중기부']),
        ('농림축산식품부', ['농림축산식품부', '농식품부']),
        ('문화체육관광부', ['문화체육관광부', '문체부']),
        ('국방부', ['국방부']),
        ('외교부', ['외교부']),
        ('통일부', ['통일부']),
        ('법무부', ['법무부']),
        ('공정거래위원회', ['공정거래위원회', '공정위']),
        ('금융위원회', ['금융위원회', '금융위']),
        ('개인정보보호위원회', ['개인정보보호위원회', '개인정보위']),
        ('방송통신위원회', ['방송통신위원회', '방통위']),
        ('국민권익위원회', ['국민권익위원회', '권익위']),
        ('국무조정실', ['국무총리', '국무조정실', '총리실', '韓총리']),
        ('식품의약품안전처', ['식품의약품안전처', '식약처']),
        ('산림청', ['산림청', '국립산림과학원', '국립수목원', '국유림관리소', '산림항공관리소']),
        ('소방청', ['소방청', '소방서', '소방본부']),
        ('경찰청', ['경찰청', '경찰서', '지구대']),
        ('질병관리청', ['질병관리청', '질병청']),
        ('특허청', ['특허청']),
        ('관세청', ['관세청']),
        ('국세청', ['국세청']),
        ('조달청', ['조달청']),
        ('기상청', ['기상청']),
        ('국가유산청', ['국가유산청', '문화재청']),
        ('해양경찰청', ['해양경찰청', '해경']),
        ('용인시', ['용인시', '용인특례시']),
        ('서울특별시', ['서울특별시', '서울시']),
        ('경기도', ['경기도'])
    ]

    items = []
    seen_ids = set()

    def fetch_single_page(page):
        url = f"https://www.korea.kr/briefing/pressReleaseList.do?pageIndex={page}"
        try:
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                return (page, res.text)
        except Exception as e:
            print(f"Error fetching gov press releases page {page}:", e)
        return (page, None)

    pages_html = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetch_single_page, p) for p in range(1, 4)]
        for f in futures:
            try:
                pages_html.append(f.result(timeout=4.0))
            except Exception:
                pass

    pages_html.sort(key=lambda x: x[0])

    for page, html_text in pages_html:
        if not html_text:
            continue
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            links = soup.find_all("a", href=True)

            for a in links:
                href = a["href"]
                if "pressReleaseView.do" not in href:
                    continue

                match = re.search(r"newsId=(\d+)", href)
                news_id = match.group(1) if match else None
                if not news_id or news_id in seen_ids:
                    continue
                seen_ids.add(news_id)

                full_url = href if href.startswith("http") else "https://www.korea.kr" + href
                parent = a.find_parent("li") or a.find_parent("div") or a
                raw_text = parent.text.strip() if parent else a.text.strip()

                title_elem = a.select_one("strong") or a.select_one(".title") or a
                title = BeautifulSoup(title_elem.text, "html.parser").text.strip()
                title = re.sub(r"^\s*보도자료\s*", "", title).strip()
                if not title or len(title) < 5:
                    continue

                source_elem = parent.select_one(".source") or parent.select_one(".writer") or parent.select_one(".info")
                source_text = source_elem.text.strip() if source_elem else ""
                search_target = f"{source_text} {raw_text}"

                dept = None
                for official_name, aliases in DEPT_MAP:
                    if any(alias in search_target or alias in title for alias in aliases):
                        dept = official_name
                        break

                if not dept:
                    clean_s = re.sub(r"\d{4}[./-]\d{2}[./-]\d{2}", "", source_text).strip()
                    if clean_s and len(clean_s) <= 15:
                        dept = clean_s
                    else:
                        dept = "정부부처"

                date_str = datetime.now().strftime("%Y-%m-%d 09:00:00")
                date_match = re.search(r"(\d{4}[./-]\d{2}[./-]\d{2})", raw_text)
                if date_match:
                    date_str = date_match.group(1).replace(".", "-").replace("/", "-") + " 09:00:00"

                items.append({
                    "id": f"gov_press_{news_id}",
                    "keyword": "보도자료",
                    "type": "news",
                    "badge": f"🏛️ {dept}",
                    "publisher": dept,
                    "title": title,
                    "time": date_str,
                    "url": full_url,
                    "content": title
                })

                if len(items) >= limit:
                    break
        except Exception as e:
            print(f"Error parsing gov press releases page {page}:", e)

        if len(items) >= limit:
            break

    return items

# ----------------------------------------------------
# 메인 통합 수집 프로세스 (100% 네이버 뉴스 API 및 RSS 전용)
# ----------------------------------------------------
def collect_all_issues(keywords=None, tab="realtime"):
    if tab == "press":
        raw_issues = fetch_korea_kr_rss(limit=60)
        print(f"📊 원본 이슈 {len(raw_issues)}건 ➔ 탭[press] 공식 보도자료 정리 완료 ({len(raw_issues)}건)")
        return raw_issues

    if not keywords:
        if tab == "exclusive":
            keywords = ["[단독]", "단독 보도", "단독 뉴스"]
        else:
            keywords = ["용인시", "처인구", "용인특례시"]

    raw_issues = []
    is_vercel = os.getenv("VERCEL") == "1"
    max_w = 6 if is_vercel else 12

    with ThreadPoolExecutor(max_workers=max_w) as executor:
        futures = []
        for kw in keywords:
            futures.append(executor.submit(fetch_naver_news, kw, 50))

        for f in futures:
            try:
                res = f.result(timeout=6.0 if is_vercel else 10.0)
                if res:
                    raw_issues.extend(res)
            except Exception as e:
                print("Parallel task fetch error:", e)

    # Filter tab-specific requirements
    if tab == "exclusive":
        exclusive_items = [item for item in raw_issues if "[단독]" in item["title"] or "단독" in item["title"]]
        if len(exclusive_items) >= 5:
            raw_issues = exclusive_items

    # 중복 이슈 제거 (Deduplication)
    deduped_issues = deduplicate_issues(raw_issues)

    # Selection per keyword / tab
    selected = deduped_issues[:80]
    selected.sort(key=lambda x: str(x.get("time", "")), reverse=True)
    deduped_issues = selected

    print(f"📊 원본 이슈 {len(raw_issues)}건 ➔ 탭[{tab}] 정리 완료 ({len(deduped_issues)}건)")

    # 뉴스 타이틀 원문 긁어오기 (Vercel 서벌리스 환경에서는 타임아웃 방지를 위해 건너뜀)
    def enrich_item_title(item_obj):
        if os.getenv("VERCEL") == "1":
            return item_obj
        if item_obj.get("type") != "news":
            return item_obj
        title = item_obj.get("title", "")
        if title.endswith("...") or title.endswith("…") or "..." in title:
            full_title = fetch_full_title_from_url(item_obj.get("url", ""))
            if full_title:
                item_obj["title"] = full_title
        return item_obj

    if os.getenv("VERCEL") != "1":
        with ThreadPoolExecutor(max_workers=10) as executor:
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

