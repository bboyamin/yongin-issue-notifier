/**
 * Application Controller & UI View Coordinator
 */
let deferredPrompt = null;
let currentIssues = [];
let currentCategory = 'all';
let currentNavTab = 'feed'; // 'feed' or 'bookmark'
let currentKeyword = '용인시';
let currentEtnewsDate = getTodayKstStr();
let currentEtnewsSection = 'all';
let etnewsData = null;
let lastUpdatedTimeStr = StorageManager.getLastUpdatedTime();
let currentPaperProvider = StorageManager.getPaperProvider();
let pendingNewIssues = null;
let renderedTitlesSet = new Set();

function applyNewIssuesFromToast() {
  const toast = document.getElementById('newIssuesToast');
  if (toast) toast.style.display = 'none';

  if (pendingNewIssues && pendingNewIssues.length) {
    currentIssues = pendingNewIssues;
    pendingNewIssues = null;
  }

  renderIssues();

  const container = document.getElementById('feedContainer');
  if (container) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    container.scrollTo({ top: 0, behavior: 'smooth' });
  }
  showToast('✨ 새로운 핫이슈 피드로 갱신되었습니다!');
}

function getTodayKstStr() {
  const d = new Date();
  const kst = new Date(d.getTime() + (9 * 60 + d.getTimezoneOffset()) * 60000);
  const yyyy = kst.getFullYear();
  const mm = String(kst.getMonth() + 1).padStart(2, '0');
  const dd = String(kst.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function isDateWeekend(dateStr) {
  if (!dateStr) return false;
  const parts = dateStr.split('-');
  if (parts.length !== 3) return false;
  const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  const day = d.getDay();
  return day === 0 || day === 6;
}

function mergeIssues(existingList, newList) {
  if (!newList || !newList.length) return existingList || [];

  const isDummy = item => item && item.title && (
    item.title.includes('최신 현장 이슈 및 주민 반응') || 
    item.title.includes('지역 실시간 소통 및 이슈 쓰레드')
  );

  const cleanNew = newList.filter(i => !isDummy(i));
  const cleanExisting = (existingList || []).filter(i => !isDummy(i));

  if (!cleanExisting.length) return cleanNew;

  const existingMap = new Map();
  cleanExisting.forEach(item => {
    const key = (item.url && item.url !== '#') ? item.url : item.title;
    if (key) existingMap.set(key, item);
  });

  const merged = [];
  const addedKeys = new Set();

  cleanNew.forEach(newItem => {
    const key = (newItem.url && newItem.url !== '#') ? newItem.url : newItem.title;
    if (key) {
      addedKeys.add(key);
      const existing = existingMap.get(key);
      if (existing) {
        if (existing.summary && (!newItem.summary || newItem.summary.length === 0)) {
          newItem.summary = existing.summary;
        }
        if (existing.is_negative !== undefined && newItem.is_negative === undefined) {
          newItem.is_negative = existing.is_negative;
        }
      }
      merged.push(newItem);
    }
  });

  cleanExisting.forEach(existingItem => {
    const key = (existingItem.url && existingItem.url !== '#') ? existingItem.url : existingItem.title;
    if (key && !addedKeys.has(key)) {
      addedKeys.add(key);
      merged.push(existingItem);
    }
  });

  const sortedMerged = merged.sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
  const finalMerged = sortedMerged.slice(0, 600);
  StorageManager.saveFeedCache(finalMerged);
  return finalMerged;
}

// Initialize Keyword Chips UI
function renderKeywordChips() {
  const userKeywords = StorageManager.getKeywords();
  const mainChips = document.getElementById('keywordChips');
  const settingsChips = document.getElementById('settingsKeywordChips');

  if (!userKeywords.includes(currentKeyword)) {
    currentKeyword = userKeywords.length ? userKeywords[0] : '';
  }

  if (mainChips) {
    let html = '';
    userKeywords.forEach(kw => {
      const isActive = currentKeyword === kw;
      html += `
        <span class="chip ${isActive ? 'active' : ''}" onclick="selectKeyword('${kw}')">
          # ${kw}
          <span class="chip-delete" onclick="removeKeyword('${kw}', event)" title="${kw} 삭제">✕</span>
        </span>
      `;
    });
    html += `<span class="chip-add" onclick="addNewKeyword()">+ 추가</span>`;
    mainChips.innerHTML = html;
  }

  if (settingsChips) {
    let settingsHtml = '';
    userKeywords.forEach(kw => {
      settingsHtml += `
        <span class="chip active">
          # ${kw}
          <span class="chip-delete" onclick="removeKeyword('${kw}', event)" title="${kw} 삭제">✕</span>
        </span>
      `;
    });
    settingsHtml += `<span class="chip-add" onclick="addNewKeyword()">+ 새 키워드 등록</span>`;
    settingsChips.innerHTML = settingsHtml;
  }
}

let isFetchingActive = false;

async function fetchKeywordIssues(keywordsList) {
  const targetKw = keywordsList[0] || '최신';
  isFetchingActive = true;
  showToast(`🔄 '${targetKw}' 관련 최신 소식 수집 중...`);
  try {
    const freshIssues = await IssueApi.fetchKeywordIssues(keywordsList);
    if (Array.isArray(freshIssues) && freshIssues.length > 0) {
      currentIssues = mergeIssues(currentIssues, freshIssues);
      showToast(`✅ '${targetKw}' 최신 소식 수집 완료!`);
    } else {
      showToast(`ℹ️ '${targetKw}' 최신 소식 연동을 완료했습니다.`);
    }
  } catch (err) {
    console.warn('Keyword collect error:', err);
    showToast(`ℹ️ '${targetKw}' 소식을 불러오는 중입니다...`);
  } finally {
    isFetchingActive = false;
    renderKeywordChips();
    renderIssues();
  }
}

async function selectKeyword(kw) {
  currentKeyword = kw;
  isFetchingActive = true;
  renderKeywordChips();
  renderIssues();

  const userKeywords = StorageManager.getKeywords();
  const fetchList = [kw, ...userKeywords.filter(k => k !== kw)];
  await fetchKeywordIssues(fetchList);
}

async function addNewKeyword() {
  const input = prompt('추가할 모니터링 키워드를 입력하세요 (예: AI, 인공지능, 반도체 등):', '');
  if (!input) return;

  const kw = input.trim().replace(/^#\s*/, '');
  if (!kw) return;

  const currentKeywords = StorageManager.getKeywords();
  if (!currentKeywords.includes(kw)) {
    StorageManager.addKeyword(kw);
  }

  currentKeyword = kw;
  isFetchingActive = true;
  const updated = StorageManager.getKeywords();
  const fetchList = [kw, ...updated.filter(k => k !== kw)];

  renderKeywordChips();
  renderIssues();

  await fetchKeywordIssues(fetchList);
}

function removeKeyword(kw, event) {
  if (event) event.stopPropagation();
  if (!confirm(`'${kw}' 키워드를 모니터링 목록에서 삭제하시겠습니까?`)) return;

  const updated = StorageManager.removeKeyword(kw);

  if (currentKeyword === kw) {
    currentKeyword = updated.length ? updated[0] : '';
  }

  renderKeywordChips();
  renderIssues();
  showToast(`'# ${kw}' 키워드가 삭제되었습니다.`);
}

function updateScrapBadge() {
  const badge = document.getElementById('scrapBadge');
  const scraps = StorageManager.getScraps();
  if (badge) {
    if (scraps.length > 0) {
      badge.textContent = scraps.length;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }
}

async function refreshFeed() {
  const realtimeBar = document.querySelector('.realtime-bar');
  const feedContainer = document.getElementById('feedContainer');

  showToast('🔄 최신 소식 수집 및 업데이트 중...');

  if (realtimeBar) {
    realtimeBar.style.opacity = '0.7';
    const textElem = realtimeBar.querySelector('.realtime-indicator span');
    if (textElem) textElem.innerHTML = '실시간 이슈 피드 <span class="spin-icon">🔄</span> <strong>수집 중...</strong>';
  }
  if (feedContainer) {
    feedContainer.style.opacity = '0.5';
  }

  const userKeywords = StorageManager.getKeywords();
  try {
    if (userKeywords.length > 0) {
      const freshIssues = await IssueApi.fetchKeywordIssues(userKeywords);
      if (Array.isArray(freshIssues) && freshIssues.length > 0) {
        currentIssues = mergeIssues(currentIssues, freshIssues);
        StorageManager.saveFeedCache(currentIssues);
      }
    }
  } catch (err) {
    console.warn('Refresh error:', err);
  } finally {
    const now = new Date();
    lastUpdatedTimeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
    StorageManager.saveLastUpdatedTime(lastUpdatedTimeStr);
    renderKeywordChips();
    renderIssues();
    if (feedContainer) {
      feedContainer.style.opacity = '1';
    }
    showToast(`✅ 실시간 피드 업데이트 완료 (${lastUpdatedTimeStr})`);
  }
}

async function switchNavTab(tab, btn) {
  const isAlreadyFeed = (currentNavTab === 'feed' && tab === 'feed');
  const isAlreadyEtnews = (currentNavTab === 'etnews' && tab === 'etnews');
  currentNavTab = tab;

  const navBtns = document.querySelectorAll('.app-bottom-nav .nav-item');
  navBtns.forEach(b => {
    if (!b.innerText.includes('설정')) {
      b.classList.remove('active');
    }
  });
  if (btn) btn.classList.add('active');

  const categoryTabs = document.querySelector('.category-tabs');
  const keywordChips = document.querySelector('.keyword-chips');
  const etnewsHeader = document.getElementById('etnewsHeader');

  if (tab === 'bookmark') {
    if (categoryTabs) categoryTabs.style.display = 'none';
    if (keywordChips) keywordChips.style.display = 'none';
    if (etnewsHeader) etnewsHeader.style.display = 'none';
    renderIssues();
  } else if (tab === 'etnews') {
    if (categoryTabs) categoryTabs.style.display = 'none';
    if (keywordChips) keywordChips.style.display = 'none';
    if (etnewsHeader) etnewsHeader.style.display = 'flex';

    if (isAlreadyEtnews) {
      await refreshEtnews();
    } else {
      await loadEtnewsForCurrentDate();
    }
  } else {
    if (categoryTabs) categoryTabs.style.display = 'flex';
    if (keywordChips) keywordChips.style.display = 'flex';
    if (etnewsHeader) etnewsHeader.style.display = 'none';

    if (isAlreadyFeed) {
      await refreshFeed();
    } else {
      renderIssues();
    }
  }
}

function renderIssues() {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  updateScrapBadge();
  const scraps = StorageManager.getScraps();

  // --- ETNews View (전자신문 지면) ---
  if (currentNavTab === 'etnews') {
    renderEtnewsView();
    return;
  }

  // --- Bookmark View (보관함) ---
  if (currentNavTab === 'bookmark') {
    let html = `
      <div class="realtime-bar" style="background:#FFFBEB; border-color:#FDE68A; color:#D97706;">
        <div class="realtime-indicator">
          <span>⭐ 내가 보관한 주요 이슈 (${scraps.length}건)</span>
        </div>
        <span style="font-size: 11px; opacity: 0.8;">보관함</span>
      </div>
    `;

    if (scraps.length === 0) {
      html += `
        <div style="text-align:center; padding: 60px 20px; color: var(--text-sub);">
          <p style="font-size:36px; margin-bottom:12px;">⭐</p>
          <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">보관된 이슈가 없습니다.</p>
          <p style="font-size:12px; color:#64748B;">실시간 피드에서 관심 있는 이슈 카드의 <strong>[⭐ 스크랩]</strong> 버튼을 눌러 나만의 보관함에 담아보세요!</p>
        </div>
      `;
    } else {
      scraps.forEach(item => {
        const badgeClass = item.type === 'news' ? 'source-news' : (item.type === 'youtube' ? 'source-youtube' : 'source-sns');
        const hasPreSummary = item.summary && item.summary.length > 0;
        const summaryItems = hasPreSummary ? item.summary.map(s => `<li>${s}</li>`).join('') : '';
        const isNegBadge = item.is_negative ? `<span class="is-neg-tag" style="background:#FEF2F2; color:#EF4444; border:1px solid #FECACA; font-size:10px; font-weight:700; padding:2px 6px; border-radius:10px; margin-left:6px;">🚨 관심 이슈</span>` : '';

        let linkText = '원문 보기 ↗';
        if (item.type === 'youtube') linkText = '영상 재생 ↗';
        else if (item.type === 'sns') linkText = '포스트 보기 ↗';

        const titleAttr = (item.title || '').replace(/"/g, '&quot;');
        const contentAttr = (item.content || item.title || '').replace(/"/g, '&quot;');
        const urlAttr = (item.url || '#').replace(/"/g, '&quot;');
        const publisherAttr = (item.publisher || '소식').replace(/"/g, '&quot;');
        const badgeAttr = (item.badge || '📰 이슈').replace(/"/g, '&quot;');
        const timeAttr = (item.time || '보관됨').replace(/"/g, '&quot;');

        html += `
          <div class="issue-card" data-category="${item.type || 'news'}" data-title="${titleAttr}" data-url="${urlAttr}" data-content="${contentAttr}" data-keyword="${item.keyword || '용인시'}" data-publisher="${publisherAttr}" data-badge="${badgeAttr}" data-time="${timeAttr}">
            <div class="card-top">
              <span class="source-tag ${badgeClass}">${item.badge || '📰 이슈'} · ${item.publisher || '소식'} ${isNegBadge}</span>
              <span class="card-date card-time">${formatRelativeTime(item.time)}</span>
            </div>
            <h3 class="card-title">${item.title}</h3>
            
            <button class="ai-summary-toggle-btn" onclick="toggleOnDemandAiSummary(this)">
              ✨ AI 3줄 요약 보기 ▾
            </button>

            <div class="ai-summary-box" style="display: none;" data-generated="${hasPreSummary ? 'true' : 'false'}">
              <div class="ai-summary-head">✨ FactChat AI 핵심 3줄 요약</div>
              <ul class="ai-summary-list">
                ${summaryItems}
              </ul>
            </div>

            <div class="card-footer">
              <div class="card-btns">
                <button class="card-action-btn scrapped" onclick="toggleScrap(this)">★ 스크랩됨</button>
                <button class="card-action-btn" onclick="shareArticle(this)">🔗 공유</button>
              </div>
              <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="link-btn">${linkText}</a>
            </div>
          </div>
        `;
      });
    }

    container.innerHTML = html;
    updateClock();
    return;
  }

  // --- Realtime Feed View (실시간 피드) ---
  const userKeywords = StorageManager.getKeywords();
  if (userKeywords.length === 0) {
    let emptyHtml = `
      <div class="realtime-bar">
        <div class="realtime-indicator">
          <div class="live-dot"></div>
          <span>접속 시점 기준 실시간 이슈 피드</span>
        </div>
        <span style="font-size: 11px; opacity: 0.8;" id="updateTimestamp">방금 업데이트</span>
      </div>
      <div style="text-align:center; padding: 50px 20px; color: var(--text-sub);">
        <p style="font-size:32px; margin-bottom:10px;">📌</p>
        <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">등록된 모니터링 키워드가 없습니다.</p>
        <p style="font-size:12px; color:#64748B;">상단의 <strong>[+ 추가]</strong> 버튼을 눌러 모니터링할 지역 또는 관심 키워드를 추가해 주세요!</p>
      </div>
    `;
    container.innerHTML = emptyHtml;
    updateClock();
    return;
  }

  if (!currentIssues.length) return;

  const SPAM_PROMO_KEYWORDS = [
    '특별분양', '회사보유분', '모델하우스', '임대수익', '조합원 모집', '조합원',
    '지식산업센터', '선착순 계약', '선착순 분양', '분양가 상한제', '분양안내', '상가 분양',
    '수익형 부동산', '급등주', '상한가 종목', '무료 리딩방', '수익률 보장',
    '소정의 원고료', '협찬 받아', '할인 쿠폰'
  ];

  const keywordFiltered = currentIssues.filter(item => {
    const itemTitle = (item.title || '').toLowerCase();
    if (SPAM_PROMO_KEYWORDS.some(s => itemTitle.includes(s))) {
      return false;
    }

    if (currentKeyword === '전체') {
      return true;
    }

    const curKwClean = currentKeyword.trim().toLowerCase();
    const itemKwClean = (item.keyword || '').trim().toLowerCase();

    // Direct keyword tag match
    if (itemKwClean && (itemKwClean === curKwClean || curKwClean.includes(itemKwClean) || itemKwClean.includes(curKwClean))) {
      return true;
    }

    const subKws = curKwClean.replace(/ OR /gi, ',').split(',').map(k => k.trim()).filter(Boolean);
    const itemContent = (item.content || '').toLowerCase();

    return subKws.some(kw => {
      if (!kw) return false;
      const baseTerm = (kw.length >= 3 && (kw.endsWith('시') || kw.endsWith('구') || kw.endsWith('동') || kw.endsWith('군') || kw.endsWith('학교'))) ? kw.slice(0, -1) : kw;
      const shortTerm = (kw.endsWith('학교') && kw.length >= 3) ? kw.slice(0, -2) : kw;

      if (itemTitle.includes(kw) || (baseTerm && baseTerm.length >= 2 && itemTitle.includes(baseTerm)) || (shortTerm && shortTerm.length >= 2 && itemTitle.includes(shortTerm))) {
        return true;
      }

      if (itemContent.includes(kw) || (baseTerm && baseTerm.length >= 2 && itemContent.includes(baseTerm)) || (shortTerm && shortTerm.length >= 2 && itemContent.includes(shortTerm))) {
        return true;
      }

      return false;
    });
  });

function getRecencyWeight(timeStr) {
  if (!timeStr) return 0;
  let s = String(timeStr).trim();

  // 1. Formatted datetime: "YYYY-MM-DD HH:mm:ss" or "YYYY.MM.DD HH:mm"
  let match = s.match(/^(\d{4})[\.\/-](\d{1,2})[\.\/-](\d{1,2})\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/);
  if (match) {
    const year = parseInt(match[1], 10);
    const month = parseInt(match[2], 10) - 1;
    const day = parseInt(match[3], 10);
    const hour = parseInt(match[4], 10);
    const min = parseInt(match[5], 10);
    const sec = match[6] ? parseInt(match[6], 10) : 0;
    return new Date(year, month, day, hour, min, sec).getTime();
  }

  // 2. Formatted date: "MM/DD HH:mm"
  match = s.match(/^(\d{1,2})[\.\/-](\d{1,2})\s+(\d{1,2}):(\d{1,2})/);
  if (match) {
    const month = parseInt(match[1], 10) - 1;
    const day = parseInt(match[2], 10);
    const hour = parseInt(match[3], 10);
    const min = parseInt(match[4], 10);
    const currentYear = new Date().getFullYear();
    return new Date(currentYear, month, day, hour, min).getTime();
  }

  // 3. 8-digit date string: "20260921"
  if (/^\d{8}$/.test(s)) {
    const year = parseInt(s.slice(0, 4), 10);
    const month = parseInt(s.slice(4, 6), 10) - 1;
    const day = parseInt(s.slice(6, 8), 10);
    return new Date(year, month, day).getTime();
  }

  // 4. Handle RFC date string lacking minutes (e.g. "Mon, 21 Sep 2026 13")
  if (/^[A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}$/.test(s)) {
    s += ":00:00";
  }

  // 5. General JS Date parsing fallback (e.g. RSS / RFC pubDate)
  const parsed = Date.parse(s);
  if (!isNaN(parsed)) {
    return parsed;
  }

  return 0;
}

function formatRelativeTime(timeStr) {
  if (!timeStr) return '방금 전';
  const weight = getRecencyWeight(timeStr);
  if (!weight) return timeStr;

  const diffSec = Math.floor((Date.now() - weight) / 1000);
  if (diffSec < 0 || diffSec < 60) return '방금 전';
  if (diffSec < 3600) return `${Math.max(1, Math.floor(diffSec / 60))}분 전`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}시간 전`;

  const d = new Date(weight);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${mm}/${dd} ${hh}:${min}`;
}

// Calculate category tab counts based strictly on the selected keyword's contents
  const counts = {
    all: keywordFiltered.length,
    news: keywordFiltered.filter(i => i.type === 'news').length,
    youtube: keywordFiltered.filter(i => i.type === 'youtube').length,
    sns: keywordFiltered.filter(i => i.type === 'sns').length
  };

  const tabs = document.querySelectorAll('.tab-btn');
  if (tabs.length >= 4) {
    tabs[0].textContent = `전체 (${counts.all})`;
    tabs[1].textContent = `📰 뉴스 (${counts.news})`;
    tabs[2].textContent = `🎥 유튜브 (${counts.youtube})`;
    tabs[3].textContent = `📱 SNS (${counts.sns})`;
  }

  // Filter & Group list: News -> Youtube -> SNS (Newest first)
  let filtered = [];
  if (currentCategory === 'all') {
    const newsItems = keywordFiltered.filter(i => i.type === 'news').sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
    const youtubeItems = keywordFiltered.filter(i => i.type === 'youtube').sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
    const snsItems = keywordFiltered.filter(i => i.type === 'sns').sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
    const otherItems = keywordFiltered.filter(i => i.type !== 'news' && i.type !== 'youtube' && i.type !== 'sns').sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));

    filtered = [...newsItems, ...youtubeItems, ...snsItems, ...otherItems];
  } else if (currentCategory === 'sns') {
    // Priority ordering inside SNS tab: Threads -> Instagram -> Facebook -> X -> Cafe -> Blog
    const getSnsPriority = (item) => {
      const b = (item.badge || '').toLowerCase();
      if (b.includes('쓰레드') || b.includes('threads')) return 1;
      if (b.includes('인스타그램') || b.includes('instagram')) return 2;
      if (b.includes('트위터') || b.includes('x (') || b.startsWith('x ')) return 3;
      if (b.includes('페이스북') || b.includes('facebook')) return 4;
      if (b.includes('카페')) return 5;
      return 6;
    };

    filtered = keywordFiltered
      .filter(item => item.type === 'sns')
      .sort((a, b) => {
        const pA = getSnsPriority(a);
        const pB = getSnsPriority(b);
        if (pA !== pB) return pA - pB;
        return getRecencyWeight(b.time) - getRecencyWeight(a.time);
      });
  } else {
    filtered = keywordFiltered
      .filter(item => item.type === currentCategory)
      .sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
  }

  const displayTimeStr = lastUpdatedTimeStr ? `${lastUpdatedTimeStr} 갱신 완료` : '최신 데이터 표시 중';

  let html = `
    <div class="realtime-bar" onclick="refreshFeed()" style="cursor: pointer;" title="클릭 시 최신 소식 실시간 새로고침">
      <div class="realtime-indicator">
        <div class="live-dot"></div>
        <span>실시간 이슈 피드 🔄 <strong>새로고침</strong></span>
      </div>
      <span style="font-size: 11px; opacity: 0.9;" id="updateTimestamp">${displayTimeStr}</span>
    </div>
  `;

  renderedTitlesSet.clear();
  if (filtered.length === 0) {
    if (isFetchingActive) {
      html += `
        <div style="text-align:center; padding: 50px 20px; color: var(--text-sub);">
          <p style="font-size:32px; margin-bottom:10px;" class="spin-icon">🔄</p>
          <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">'# ${currentKeyword}' 관련 실시간 최신 소식을 수집 중입니다...</p>
          <p style="font-size:12px; color:#64748B;">네이버 뉴스, 블로그, 포스트에서 소식을 연동 중입니다. 잠시만 기다려 주세요!</p>
        </div>
      `;
    } else {
      html += `
        <div style="text-align:center; padding: 50px 20px; color: var(--text-sub);">
          <p style="font-size:32px; margin-bottom:10px;">🔍</p>
          <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">'# ${currentKeyword}' 관련 실시간 이슈를 준비 중입니다.</p>
          <p style="font-size:12px; color:#64748B; margin-bottom:16px;">아래 버튼을 누르면 실시간으로 최신 뉴스 및 소식을 수집해 연결합니다.</p>
          <button onclick="refreshFeed()" style="background:var(--primary); color:white; border:none; padding:10px 18px; border-radius:20px; font-size:13px; font-weight:700; cursor:pointer; box-shadow: 0 4px 12px rgba(37,99,235,0.2);">🔄 '# ${currentKeyword}' 실시간 소식 수집하기</button>
        </div>
      `;
    }
  } else {
    filtered.forEach(item => {
      if (item && item.title) renderedTitlesSet.add(item.title);

      const badgeClass = item.type === 'news' ? 'source-news' : (item.type === 'youtube' ? 'source-youtube' : 'source-sns');
      const hasPreSummary = item.summary && item.summary.length > 0;
      const summaryItems = hasPreSummary ? item.summary.map(s => `<li>${s}</li>`).join('') : '';
      const isNegBadge = item.is_negative ? `<span class="is-neg-tag" style="background:#FEF2F2; color:#EF4444; border:1px solid #FECACA; font-size:10px; font-weight:700; padding:2px 6px; border-radius:10px; margin-left:6px;">🚨 관심 이슈</span>` : '';

      let linkText = '원문 보기 ↗';
      if (item.type === 'youtube') linkText = '영상 재생 ↗';
      else if (item.type === 'sns') linkText = '포스트 보기 ↗';

      const titleAttr = (item.title || '').replace(/"/g, '&quot;');
      const contentAttr = (item.content || item.title || '').replace(/"/g, '&quot;');
      const urlAttr = (item.url || '#').replace(/"/g, '&quot;');
      const publisherAttr = (item.publisher || '소식').replace(/"/g, '&quot;');
      const badgeAttr = (item.badge || '📰 이슈').replace(/"/g, '&quot;');
      const timeAttr = (item.time || '방금 전').replace(/"/g, '&quot;');
      const isScrapped = StorageManager.isScrapped(item.title);
      const scrapBtnHtml = isScrapped
        ? `<button class="card-action-btn scrapped" onclick="toggleScrap(this)">★ 스크랩됨</button>`
        : `<button class="card-action-btn" onclick="toggleScrap(this)">⭐ 스크랩</button>`;

      const badgeLabel = (item.badge && item.publisher && item.badge.includes(item.publisher)) 
        ? item.badge 
        : `${item.badge || '📰 이슈'} · ${item.publisher || '소식'}`;

      html += `
        <div class="issue-card" data-category="${item.type || 'news'}" data-title="${titleAttr}" data-url="${urlAttr}" data-content="${contentAttr}" data-keyword="${item.keyword || '용인시'}" data-publisher="${publisherAttr}" data-badge="${badgeAttr}" data-time="${timeAttr}">
          <div class="card-top">
            <span class="source-tag ${badgeClass}">${badgeLabel} ${isNegBadge}</span>
            <span class="card-time">${formatRelativeTime(item.time)}</span>
          </div>
          <h3 class="card-title">${item.title}</h3>
          
          <button class="ai-summary-toggle-btn" onclick="toggleOnDemandAiSummary(this)">
            ✨ AI 3줄 요약 보기 ▾
          </button>

          <div class="ai-summary-box" style="display: none;" data-generated="${hasPreSummary ? 'true' : 'false'}">
            <div class="ai-summary-head">✨ FactChat AI 핵심 3줄 요약</div>
            <ul class="ai-summary-list">
              ${summaryItems}
            </ul>
          </div>

          <div class="card-footer">
            <div class="card-btns">
              ${scrapBtnHtml}
              <button class="card-action-btn" onclick="shareArticle(this)">🔗 공유</button>
            </div>
            <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="link-btn">${linkText}</a>
          </div>
        </div>
      `;
    });
  }

  container.innerHTML = html;
  updateClock();
}

function switchCategory(cat, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentCategory = cat;
  renderIssues();
}

async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    showToast('⚠️ 이 브라우저는 푸시 알림을 지원하지 않습니다.');
    return false;
  }

  if (Notification.permission === 'granted') {
    return true;
  }

  if (Notification.permission !== 'denied') {
    try {
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        showToast('✅ 알림 권한이 허용되었습니다!');
        return true;
      }
    } catch (e) {
      console.error('Notification permission request error:', e);
    }
  }

  showToast('⚠️ 아이폰/브라우저 [설정 > 알림]에서 알림을 허용해주세요.');
  return false;
}

async function triggerRealPushNotification(title, body, targetUrl) {
  const push = document.getElementById('pushBanner');
  if (push) {
    const titleElem = push.querySelector('.push-title span:first-child');
    const descElem = push.querySelector('.push-desc');
    if (titleElem) titleElem.textContent = title;
    if (descElem) descElem.textContent = body;

    if (targetUrl && targetUrl.startsWith('http')) {
      push.style.cursor = 'pointer';
      push.onclick = () => window.open(targetUrl, '_blank', 'noopener,noreferrer');
    } else {
      push.style.cursor = 'default';
      push.onclick = null;
    }

    push.classList.add('show');
    setTimeout(() => push.classList.remove('show'), 6000);
  }

  showToast(`🔔 ${title}`);

  if ('Notification' in window) {
    let perm = Notification.permission;
    if (perm === 'default') {
      try {
        perm = await Notification.requestPermission();
      } catch (e) { }
    }

    if (perm === 'granted') {
      const finalUrl = (targetUrl && targetUrl.startsWith('http')) ? targetUrl : window.location.href;
      if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.ready.then(registration => {
          registration.showNotification(title, {
            body: body,
            icon: './apple-touch-icon.png',
            badge: './apple-touch-icon.png',
            vibrate: [200, 100, 200],
            data: { url: finalUrl }
          });
        });
      } else {
        try {
          const n = new Notification(title, {
            body: body,
            icon: './apple-touch-icon.png',
            data: { url: finalUrl }
          });
          n.onclick = (e) => {
            e.preventDefault();
            window.open(finalUrl, '_blank', 'noopener,noreferrer');
            window.focus();
          };
        } catch (e) {
          console.log('Fallback Notification error:', e);
        }
      }
    }
  }
}

async function triggerNotificationTest() {
  await requestNotificationPermission();
  const topItem = currentIssues.length ? currentIssues[0] : null;
  const testTitle = topItem ? topItem.title : `[${currentKeyword || '용인시'}] 실시간 주요 속보`;
  const testUrl = topItem ? topItem.url : 'https://news.naver.com';

  triggerRealPushNotification(
    `🔔 [속보 알림] #${topItem ? topItem.keyword : (currentKeyword || '용인시')}`,
    testTitle,
    testUrl
  );
}

function toggleSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (modal) modal.classList.toggle('show');
}

function toggleScrap(btn, legacyTitle) {
  const card = (btn && btn.closest) ? btn.closest('.issue-card') : null;
  let title = card ? (card.dataset.title || '') : (legacyTitle || '');
  if (!title) return;

  let targetItem = currentIssues.find(item => item.title === title);
  if (!targetItem && card) {
    targetItem = {
      title: card.dataset.title || title,
      url: card.dataset.url || (card.querySelector('.link-btn') ? card.querySelector('.link-btn').href : '#'),
      publisher: card.dataset.publisher || '용인 소식',
      time: card.dataset.time || '보관됨',
      type: card.dataset.category || 'news',
      badge: card.dataset.badge || '📰 보관',
      keyword: card.dataset.keyword || '용인시'
    };
  } else if (!targetItem) {
    targetItem = { title: title };
  }

  const { isScrapped } = StorageManager.toggleScrap(targetItem);

  if (btn && btn.classList) {
    if (isScrapped) {
      btn.classList.add('scrapped');
      btn.innerHTML = '★ 스크랩됨';
      showToast('⭐ 보관함에 스크랩되었습니다.');
    } else {
      btn.classList.remove('scrapped');
      btn.innerHTML = '⭐ 스크랩';
      showToast('보관함에서 취소되었습니다.');
    }
  }

  updateScrapBadge();

  if (currentNavTab === 'bookmark') {
    renderIssues();
  }
}

function showToast(msg) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.className = 'app-toast';
    const appScreen = document.querySelector('.app-screen');
    if (appScreen) appScreen.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 2500);
}

async function shareArticle(btnOrTitle, legacyUrl) {
  let title = '';
  let articleUrl = '';

  if (btnOrTitle && typeof btnOrTitle === 'object' && btnOrTitle.nodeType) {
    const card = btnOrTitle.closest('.issue-card');
    if (card) {
      title = card.dataset.title || '';
      articleUrl = card.dataset.url || card.querySelector('.link-btn')?.href || window.location.href;
    }
  } else if (typeof btnOrTitle === 'string') {
    title = btnOrTitle;
    articleUrl = legacyUrl || window.location.href;
  }

  if (!articleUrl || articleUrl === '#') {
    articleUrl = window.location.href;
  }

  const cleanTitle = title ? title.replace(/&quot;/g, '"') : '용인 핫이슈';
  const shareData = {
    title: cleanTitle,
    text: `[용인 핫이슈 모니터] ${cleanTitle}`,
    url: articleUrl
  };

  if (navigator.share) {
    try {
      await navigator.share(shareData);
      showToast('🔗 원문 링크 공유가 완료되었습니다.');
      return;
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.warn('Web Share API error:', err);
      } else {
        return;
      }
    }
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(articleUrl);
      showToast('🔗 콘텐츠 원문 링크가 클립보드에 복사되었습니다!');
      return;
    } catch (err) {
      console.warn('Clipboard write error:', err);
    }
  }

  prompt('아래 콘텐츠 원문 링크를 복사하여 공유하세요:', articleUrl);
}

function updateNotifySetting(key, inputElem) {
  const settings = StorageManager.getNotifySettings();
  settings[key] = inputElem.checked;
  StorageManager.saveNotifySettings(settings);
  const labelStr = key === 'realtime' ? '실시간 속보' : (key === 'negative' ? '관심/위험 이슈' : '정기 브리핑');
  showToast(`${labelStr} 알림이 ${inputElem.checked ? 'ON 설정' : 'OFF 해제'}되었습니다.`);
}

function updateNotifyInterval(selectElem) {
  const val = parseInt(selectElem.value, 10) || 15;
  const settings = StorageManager.getNotifySettings();
  settings.intervalMinutes = val;
  StorageManager.saveNotifySettings(settings);

  startAutoPolling();
  showToast(`⏱️ 푸시 알림 주기가 ${val}분 마다로 설정되었습니다.`);
}

let autoPollingTimer = null;

function startAutoPolling() {
  if (autoPollingTimer) clearInterval(autoPollingTimer);

  const settings = StorageManager.getNotifySettings();
  const intervalMin = settings.intervalMinutes || 15;
  const intervalMs = intervalMin * 60 * 1000;

  autoPollingTimer = setInterval(async () => {
    const notifySettings = StorageManager.getNotifySettings();
    if (!notifySettings || !notifySettings.realtime) return;

    const userKeywords = StorageManager.getKeywords();
    if (!userKeywords || userKeywords.length === 0) return;

    try {
      const latestIssues = await IssueApi.fetchKeywordIssues(userKeywords);
      if (latestIssues && latestIssues.length > 0) {
        const previousTitles = new Set(currentIssues.map(i => i.title));
        const newItems = latestIssues.filter(i => !previousTitles.has(i.title));

        currentIssues = mergeIssues(currentIssues, latestIssues);
        const now = new Date();
        lastUpdatedTimeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
        StorageManager.saveLastUpdatedTime(lastUpdatedTimeStr);

        renderKeywordChips();
        renderIssues();

        if (newItems.length > 0) {
          newItems.sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));
          const topItem = newItems[0];
          triggerRealPushNotification(
            `🔔 [신규 속보] #${topItem.keyword || '용인시'} 새 이슈`,
            topItem.title,
            topItem.url
          );
        }
      }
    } catch (err) {
      console.warn('Auto polling check error:', err);
    }
  }, intervalMs);
}

function togglePasswordVisibility() {
  const input = document.getElementById('factchatApiKeyInput');
  if (input) input.type = input.type === 'password' ? 'text' : 'password';
}

function initFactChatKeyUI() {
  const input = document.getElementById('factchatApiKeyInput');
  const badge = document.getElementById('factchatKeyBadge');
  const savedKey = StorageManager.getFactChatKey();

  if (input && savedKey) {
    input.value = savedKey;
  }
  if (badge) {
    if (savedKey) {
      badge.className = 'api-key-badge active';
      badge.textContent = '✅ 연동됨';
    } else {
      badge.className = 'api-key-badge warning';
      badge.textContent = '⚠️ 키 입력 필요';
    }
  }
}

function saveFactchatKey() {
  const input = document.getElementById('factchatApiKeyInput');
  const badge = document.getElementById('factchatKeyBadge');
  const keyVal = input ? input.value.trim() : '';

  StorageManager.saveFactChatKey(keyVal);
  if (keyVal) {
    if (badge) {
      badge.className = 'api-key-badge active';
      badge.textContent = '✅ 연동됨';
    }
    showToast('🔑 FactChat API 키가 안전하게 저장되었습니다!');
  } else {
    if (badge) {
      badge.className = 'api-key-badge warning';
      badge.textContent = '⚠️ 키 입력 필요';
    }
    showToast('⚠️ API 키를 입력하지 않으면 AI 3줄 요약 기능이 제한됩니다.');
  }
}

function showKeyIssuanceGuide() {
  alert(`[사내 FactChat API 개인 키 발급 안내]\n\n1. 사내 FactChat 개발자 포털(https://factchat-cloud.mindlogic.ai/v1/gateway) 접속\n2. 사내 계정 로그인 후 [마이페이지 -> API 키 관리] 메뉴 이동\n3. [신규 개인 발급키 생성] 클릭 후 생성된 키 복사 (fc_key_...)\n4. 본 앱의 설정창 [사내 FactChat API 개인 키 설정] 입력란에 붙여넣고 [저장]을 누르시면 AI 3줄 요약 기능이 즉시 연동됩니다.`);
}

async function toggleOnDemandAiSummary(btn) {
  const card = btn.closest('.issue-card');
  const summaryBox = card.querySelector('.ai-summary-box');
  if (!summaryBox) return;

  const isVisible = summaryBox.style.display !== 'none';
  if (isVisible) {
    summaryBox.style.display = 'none';
    btn.innerHTML = '✨ AI 3줄 요약 보기 ▾';
    return;
  }

  const isGenerated = summaryBox.dataset.generated === 'true';
  if (isGenerated) {
    summaryBox.style.display = 'block';
    btn.innerHTML = '✨ AI 3줄 요약 접기 ▴';
    return;
  }

  const title = card.dataset.title || '';
  const content = card.dataset.content || title;
  const keyword = card.dataset.keyword || '용인시';
  const apiKey = StorageManager.getFactChatKey();

  btn.innerHTML = '✨ FactChat AI 3줄 요약 생성 중...';
  btn.disabled = true;

  try {
    const { summary, is_negative } = await IssueApi.generateSummary({ title, keyword, content, apiKey });
    const listHtml = summary.map(s => `<li>${s}</li>`).join('');
    summaryBox.querySelector('.ai-summary-list').innerHTML = listHtml;
    summaryBox.style.display = 'block';
    summaryBox.dataset.generated = 'true';
    btn.innerHTML = '✨ AI 3줄 요약 접기 ▴';
    btn.disabled = false;

    if (is_negative) {
      const sourceTag = card.querySelector('.source-tag');
      if (sourceTag && !sourceTag.querySelector('.is-neg-tag')) {
        sourceTag.innerHTML += `<span class="is-neg-tag" style="background:#FEF2F2; color:#EF4444; border:1px solid #FECACA; font-size:10px; font-weight:700; padding:2px 6px; border-radius:10px; margin-left:6px;">🚨 관심 이슈</span>`;
      }
    }
  } catch (err) {
    console.error('On-Demand AI Summary Error:', err);
    btn.innerHTML = '✨ AI 3줄 요약 보기 ▾';
    btn.disabled = false;
    alert('FactChat API 요약 생성 중 오류가 발생했습니다. 설정에서 API 키를 확인해 주세요.');
  }
}

function updatePaperProviderUI() {
  const selectElem = document.getElementById('paperProviderSelect');
  if (selectElem) selectElem.value = currentPaperProvider;

  const labelElem = document.getElementById('navPaperLabel');
  if (labelElem) labelElem.textContent = currentPaperProvider === 'mknews' ? '매일경제' : '전자신문';
}

function updatePaperProviderSetting(provider) {
  if (!['etnews', 'mknews'].includes(provider)) return;
  currentPaperProvider = provider;
  StorageManager.savePaperProvider(provider);
  currentEtnewsSection = 'all';

  updatePaperProviderUI();
  const providerName = provider === 'mknews' ? '매일경제' : '전자신문';
  showToast(`📰 지면 신문사가 '${providerName}'(으)로 설정되었습니다.`);

  if (currentNavTab === 'etnews') {
    loadEtnewsForCurrentDate();
  }
}

async function loadEtnewsForCurrentDate() {
  const datePicker = document.getElementById('etnewsDatePicker');
  if (datePicker && !datePicker.value) {
    datePicker.value = currentEtnewsDate;
  }
  const ymd = (datePicker && datePicker.value ? datePicker.value : currentEtnewsDate).replace(/-/g, '');
  const providerName = currentPaperProvider === 'mknews' ? '매일경제' : '전자신문';
  const apiEndpoint = currentPaperProvider === 'mknews' ? '/api/mknews' : '/api/etnews';

  showToast(`🔄 ${providerName} 지면(${ymd}) 수집 중...`);
  etnewsData = { sections: [], categorized: {}, articles: [] };
  
  try {
    const res = await fetch(`${apiEndpoint}?provider=${currentPaperProvider}&date=${ymd}&v=` + Date.now());
    if (res.ok) {
      etnewsData = await res.json();
    } else {
      etnewsData = { sections: [], categorized: {}, articles: [] };
    }
  } catch (e) {
    console.warn('Paper fetch error:', e);
    etnewsData = { sections: [], categorized: {}, articles: [] };
  }
  
  updatePaperProviderUI();
  renderEtnewsSectionChips();
  renderEtnewsView();
}

function renderEtnewsSectionChips() {
  const container = document.getElementById('etnewsSectionChips');
  if (!container || !etnewsData) return;

  const sections = etnewsData.sections || [];
  const totalCount = etnewsData.articles ? etnewsData.articles.length : 0;
  let html = `<span class="etnews-section-chip ${currentEtnewsSection === 'all' ? 'active' : ''}" onclick="selectEtnewsSection('all')">전체 지면 (${totalCount})</span>`;

  sections.forEach(sec => {
    const count = etnewsData.categorized[sec] ? etnewsData.categorized[sec].length : 0;
    const isActive = currentEtnewsSection === sec;
    const safeSec = sec.replace(/'/g, "\\'");
    html += `<span class="etnews-section-chip ${isActive ? 'active' : ''}" onclick="selectEtnewsSection('${safeSec}')">${sec} (${count})</span>`;
  });

  container.innerHTML = html;
}

function selectEtnewsSection(sec) {
  currentEtnewsSection = sec;
  renderEtnewsSectionChips();
  renderEtnewsView();
}

function onEtnewsDateChange(val) {
  if (!val) return;
  currentEtnewsDate = val;
  currentEtnewsSection = 'all';
  loadEtnewsForCurrentDate();
}

function setEtnewsToday() {
  currentEtnewsDate = getTodayKstStr();
  const datePicker = document.getElementById('etnewsDatePicker');
  if (datePicker) datePicker.value = currentEtnewsDate;
  currentEtnewsSection = 'all';
  loadEtnewsForCurrentDate();
}

async function refreshEtnews() {
  await loadEtnewsForCurrentDate();
}

function renderEtnewsView() {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  updateScrapBadge();
  const providerName = currentPaperProvider === 'mknews' ? '매일경제' : '전자신문';
  const providerIcon = currentPaperProvider === 'mknews' ? '📈' : '📰';

  if (!etnewsData || !etnewsData.articles || etnewsData.articles.length === 0) {
    const isWeekend = isDateWeekend(currentEtnewsDate);
    let msg = isWeekend
      ? `📅 ${currentEtnewsDate} 은 주말(휴간일)로 지면 신문이 발행되지 않는 날입니다. 평일을 선택해 주세요.`
      : `📅 ${currentEtnewsDate} 지면 정보를 불러오는 중입니다. 신문사 발행 직후(아침 06~07시)이거나 수집 지연이 발생할 수 있습니다.`;
    container.innerHTML = `
      <div style="text-align:center; padding: 60px 20px; color: var(--text-sub);">
        <p style="font-size:36px; margin-bottom:12px;">${providerIcon}</p>
        <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">${providerName} 지면 기사 없음</p>
        <p style="font-size:12px; color:#64748B; line-height:1.5;">${msg}</p>
        <button onclick="refreshEtnews()" style="margin-top:16px; background:#EEF2FF; color:#4F46E5; border:1px solid #C7D2FE; padding:8px 16px; border-radius:12px; font-weight:700; cursor:pointer;">🔄 지면 다시 불러오기</button>
      </div>
    `;
    updateClock();
    return;
  }

  let displayArticles = etnewsData.articles;
  if (currentEtnewsSection !== 'all') {
    displayArticles = etnewsData.categorized[currentEtnewsSection] || [];
  }

  const formattedYmd = currentEtnewsDate.replace(/-/g, '.');
  let html = `
    <div class="realtime-bar" onclick="refreshEtnews()" style="cursor: pointer; background: #F8FAFC; border-color: #E2E8F0;" title="클릭 시 지면 다시 불러오기">
      <div class="realtime-indicator">
        <div class="live-dot" style="background:#0F172A;"></div>
        <span>${providerIcon} ${providerName} 지면 브리핑 <strong>(${formattedYmd})</strong></span>
      </div>
      <span style="font-size: 11px; opacity: 0.8;">총 ${displayArticles.length}건</span>
    </div>
  `;

  displayArticles.forEach(item => {
    const hasPreSummary = item.summary && item.summary.length > 0;
    const summaryItems = hasPreSummary ? item.summary.map(s => `<li>${s}</li>`).join('') : '';

    const titleAttr = (item.title || '').replace(/"/g, '&quot;');
    const contentAttr = (item.content || item.title || '').replace(/"/g, '&quot;');
    const urlAttr = (item.url || '#').replace(/"/g, '&quot;');
    const publisherAttr = (item.publisher || providerName).replace(/"/g, '&quot;');
    const badgeAttr = (item.badge || `${providerIcon} ${providerName}`).replace(/"/g, '&quot;');
    const timeAttr = (item.time || currentEtnewsDate).replace(/"/g, '&quot;');
    const isScrapped = StorageManager.isScrapped(item.title);
    const scrapBtnHtml = isScrapped
      ? `<button class="card-action-btn scrapped" onclick="toggleScrap(this)">★ 스크랩됨</button>`
      : `<button class="card-action-btn" onclick="toggleScrap(this)">⭐ 스크랩</button>`;

    html += `
      <div class="issue-card" data-category="news" data-title="${titleAttr}" data-url="${urlAttr}" data-content="${contentAttr}" data-keyword="${providerName}" data-publisher="${publisherAttr}" data-badge="${badgeAttr}" data-time="${timeAttr}">
        <div class="card-top">
          <span class="source-tag source-news">${item.badge || badgeAttr}</span>
          <span class="card-time">${item.time}</span>
        </div>
        <h3 class="card-title">${item.title}</h3>
        
        <button class="ai-summary-toggle-btn" onclick="toggleEtnewsAiSummary(this)">
          ✨ AI 스마트 브리핑 보기 ▾
        </button>

        <div class="ai-summary-box" style="display: none;" data-generated="${hasPreSummary ? 'true' : 'false'}">
          <div class="ai-summary-head">✨ FactChat AI ${providerName} 스마트 브리핑</div>
          <ul class="ai-summary-list">
            ${summaryItems}
          </ul>
        </div>

        <div class="card-footer">
          <div class="card-btns">
            ${scrapBtnHtml}
            <button class="card-action-btn" onclick="shareArticle(this)">🔗 공유</button>
          </div>
          <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="link-btn">지면 원문 보기 ↗</a>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
  updateClock();
}

async function toggleEtnewsAiSummary(btn) {
  const card = btn.closest('.issue-card');
  if (!card) return;
  const summaryBox = card.querySelector('.ai-summary-box');
  if (!summaryBox) return;

  if (summaryBox.style.display === 'block') {
    summaryBox.style.display = 'none';
    btn.innerHTML = '✨ AI 스마트 브리핑 보기 ▾';
    return;
  }

  if (summaryBox.dataset.generated === 'true') {
    summaryBox.style.display = 'block';
    btn.innerHTML = '✨ AI 스마트 브리핑 접기 ▴';
    return;
  }

  const apiKey = StorageManager.getFactChatKey();
  if (!apiKey) {
    alert('FactChat API 키가 설정되지 않았습니다.\n상단 ⚙️ 설정 메뉴에서 API 키를 입력해 주세요.');
    toggleSettingsModal();
    return;
  }

  const title = card.dataset.title;
  const url = card.dataset.url;
  btn.disabled = true;
  btn.innerHTML = '✨ AI 요약 작성 중... ⏳';

  try {
    let articleContent = card.dataset.content || '';
    if (!articleContent || articleContent === title) {
      const bodyRes = await fetch(`/api/etnews?mode=etnews&url=${encodeURIComponent(url)}&v=` + Date.now());
      if (bodyRes.ok) {
        const bodyData = await bodyRes.json();
        if (bodyData.content) {
          articleContent = bodyData.content;
          card.dataset.content = articleContent;
        }
      }
    }

    const { summary } = await IssueApi.generateSummary({
      title,
      keyword: '전자신문',
      content: articleContent,
      apiKey
    });

    const listHtml = summary.map(s => `<li>${s}</li>`).join('');
    summaryBox.querySelector('.ai-summary-list').innerHTML = listHtml;
    summaryBox.style.display = 'block';
    summaryBox.dataset.generated = 'true';
    btn.innerHTML = '✨ AI 스마트 브리핑 접기 ▴';
    btn.disabled = false;
  } catch (err) {
    console.error('ETNews AI Summary Error:', err);
    btn.innerHTML = '✨ AI 스마트 브리핑 보기 ▾';
    btn.disabled = false;
    alert('FactChat API 요약 작성 중 오류가 발생했습니다.');
  }
}

function openContentUrl(url, event) {
  if (!url || url === '#') {
    if (event) event.preventDefault();
    return false;
  }
  return true;
}

function updateClock() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const timeElem = document.getElementById('liveTime');
  if (timeElem) timeElem.textContent = `${hours}:${minutes}`;
}

function installPWA() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then((choiceResult) => {
      if (choiceResult.outcome === 'accepted') {
        alert('용인 핫이슈 모니터 앱 설치가 시작되었습니다!');
      }
      deferredPrompt = null;
    });
  } else {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (isIOS) {
      alert('📱 [아이폰 PWA 앱 설치 안내]\n\n하단 사파리 브라우저의 [공유] 버튼(↑)을 누르신 후 목록에서 [홈 화면에 추가 (+)]를 클릭하시면 스마트폰 바탕화면에 앱으로 등록됩니다.');
    } else {
      alert('📱 [앱 설치 안내]\n\n모바일 크롬/웨일 브라우저 상단 우측 메뉴(⋮) ➔ [앱 설치] 또는 [홈 화면에 추가]를 누르시면 스마트폰 바탕화면에 앱이 설치됩니다.');
    }
  }
}

// Lifecycle Init
document.addEventListener('DOMContentLoaded', () => {
  renderKeywordChips();
  updateScrapBadge();
  initFactChatKeyUI();

  // Register Service Worker & Force Version Check
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js')
        .then((reg) => {
          console.log('PWA Service Worker registered:', reg.scope);
          reg.update();
        })
        .catch((err) => console.log('SW Registration failed:', err));
    });
  }

  // PWA Prompt Listener
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
  });

  // Initialize notification interval UI & paper provider UI
  const notifySettings = StorageManager.getNotifySettings();
  const selectElem = document.getElementById('notifyIntervalSelect');
  if (selectElem && notifySettings.intervalMinutes) {
    selectElem.value = String(notifySettings.intervalMinutes);
  }

  updatePaperProviderUI();

  // Clock Timer
  setInterval(updateClock, 1000);
  updateClock();

  // Start auto-polling with user preferred interval (default 15 min)
  startAutoPolling();

  // Mobile App Resume / Foreground listener: check if interval has passed when user reopens screen
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      const settings = StorageManager.getNotifySettings();
      const intervalMin = settings.intervalMinutes || 15;
      const lastTimeStr = StorageManager.getLastUpdatedTime();

      if (lastTimeStr && lastTimeStr.includes(':')) {
        const parts = lastTimeStr.split(':');
        const lastDate = new Date();
        lastDate.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10), parseInt(parts[2] || 0, 10));
        const diffMins = (new Date() - lastDate) / (1000 * 60);
        if (diffMins >= intervalMin) {
          refreshFeed();
        }
      }
    }
  });

  // 100% Fail-Safe Initial Load: Render cached feed immediately if present, then sync fresh dataset
  const cachedFeed = StorageManager.getFeedCache();
  if (Array.isArray(cachedFeed) && cachedFeed.length > 0) {
    currentIssues = cachedFeed;
    renderKeywordChips();
    renderIssues();
  }

  IssueApi.loadDefaultIssues().then(defaultIssues => {
    if (Array.isArray(defaultIssues) && defaultIssues.length > 0) {
      currentIssues = mergeIssues(currentIssues, defaultIssues);
      StorageManager.saveFeedCache(currentIssues);
    }
    renderKeywordChips();
    renderIssues();
    refreshFeed();
  }).catch(err => {
    console.warn('loadDefaultIssues error:', err);
    renderKeywordChips();
    renderIssues();
    refreshFeed();
  });
});
