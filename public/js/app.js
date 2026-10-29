/**
 * Application Controller & UI View Coordinator
 */

// Disable automatic browser scroll restoration so views always start at top (0)
if ('scrollRestoration' in history) {
  try {
    history.scrollRestoration = 'manual';
  } catch (e) {}
}

// Proactively purge all legacy paper_scroll keys from storage
try {
  localStorage.removeItem('paper_scroll_y');
  sessionStorage.removeItem('paper_scroll_y');
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const k = localStorage.key(i);
    if (k && k.includes('paper_scroll')) localStorage.removeItem(k);
  }
  for (let i = sessionStorage.length - 1; i >= 0; i--) {
    const k = sessionStorage.key(i);
    if (k && k.includes('paper_scroll')) sessionStorage.removeItem(k);
  }
} catch (e) {}

let deferredPrompt = null;
let currentIssues = [];
const keywordFeeds = {}; // Cache feeds per keyword
const tabFeeds = {}; // Cache feeds per tab ('exclusive', 'press')
const paperFeedsCache = {}; // Memory & Session cache for Paper View
let currentNavTab = 'feed'; // 'feed', 'paper', 'exclusive', 'press', 'bookmark'
let currentKeyword = '용인시';
let currentPaperDate = getTodayKstStr();
let currentPaperSection = 'all';
const PAPER_PROVIDERS = [
  { id: 'mknews', name: '매일경제' },
  { id: 'etnews', name: '전자신문' },
  { id: 'khan', name: '경향신문' }
];

let currentPaperProvider = StorageManager.getPaperProvider() || 'mknews';
if (!PAPER_PROVIDERS.some(p => p.id === currentPaperProvider)) {
  currentPaperProvider = 'mknews';
  StorageManager.savePaperProvider('mknews');
}
let currentPressDept = '용인시';
let paperData = null;
let lastUpdatedTimeStr = StorageManager.getLastUpdatedTime();

function getTodayKstStr() {
  const d = new Date();
  const kst = new Date(d.getTime() + (9 * 60 + d.getTimezoneOffset()) * 60000);
  const yyyy = kst.getFullYear();
  const mm = String(kst.getMonth() + 1).padStart(2, '0');
  const dd = String(kst.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function scrollToTop() {
  try {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const feedContainer = document.getElementById('feedContainer');
    if (feedContainer) feedContainer.scrollTop = 0;
  } catch (e) {}
}

function formatRelativeTime(timeStr) {
  if (!timeStr) return '방금 전';
  if (timeStr.includes('방금') || timeStr.includes('전') || timeStr.includes('어제')) return timeStr;

  try {
    let cleanStr = String(timeStr).trim().replace(/\//g, '-');
    if (cleanStr.length === 10) cleanStr += ' 00:00:00';
    let isoStr = cleanStr.replace(' ', 'T');
    if (!isoStr.includes('+') && !isoStr.includes('Z')) {
      isoStr += '+09:00';
    }
    const pubDate = new Date(isoStr);
    if (isNaN(pubDate.getTime())) return timeStr;
    const diffMin = Math.floor((Date.now() - pubDate.getTime()) / 60000);

    if (diffMin < 0 || diffMin < 1) return '방금 전';
    if (diffMin < 60) return `${diffMin}분 전`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}시간 전`;
    return `${Math.floor(diffHours / 24)}일 전`;
  } catch (e) {
    return timeStr;
  }
}

function updateHeaderScrapBadge() {
  const badge = document.getElementById('headerScrapBadge');
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

function renderPaperProviderChips() {
  const chipsContainer = document.getElementById('paperProviderChips');
  if (!chipsContainer) return;

  let html = '';
  PAPER_PROVIDERS.forEach(p => {
    const isActive = currentPaperProvider === p.id;
    html += `
      <span class="chip ${isActive ? 'active' : ''}" onclick="selectPaperProvider('${p.id}')" style="cursor:pointer; font-weight:700;">
        ${p.name}
      </span>
    `;
  });
  chipsContainer.innerHTML = html;
}

function selectPaperProvider(providerId) {
  currentPaperProvider = providerId;
  StorageManager.savePaperProvider(providerId);

  const selectElem = document.getElementById('paperProviderSelect');
  if (selectElem) selectElem.value = providerId;

  const container = document.getElementById('feedContainer');
  if (container) {
    container.removeAttribute('data-rendered-key');
    container.scrollTop = 0;
  }
  scrollToTop();

  renderPaperProviderChips();
  loadPaperForCurrentDate();
}

function updatePaperProviderSetting(providerId) {
  selectPaperProvider(providerId);
}

// 100% Original Keyword Chips UI for Realtime Feed
function renderKeywordChips() {
  const userKeywords = StorageManager.getKeywords();
  const mainChips = document.getElementById('keywordChips');
  const settingsChips = document.getElementById('settingsKeywordChips');

  if (!userKeywords.includes(currentKeyword)) {
    currentKeyword = userKeywords.length ? userKeywords[0] : '용인시';
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

async function selectKeyword(kw) {
  scrollToTop();
  currentKeyword = kw;
  renderKeywordChips();
  await fetchKeywordIssues([kw]);
}

async function addNewKeyword() {
  const input = prompt('추가할 모니터링 키워드를 입력하세요 (예: 용인시, 처인구, 수지구, 기흥구 등):', '');
  if (!input) return;

  const kw = input.trim().replace(/^#\s*/, '');
  if (!kw) return;

  const currentKeywords = StorageManager.getKeywords();
  if (!currentKeywords.includes(kw)) {
    StorageManager.addKeyword(kw);
  }

  currentKeyword = kw;
  renderKeywordChips();
  await fetchKeywordIssues([kw]);
}

function removeKeyword(kw, event) {
  if (event) event.stopPropagation();
  if (!confirm(`'${kw}' 키워드를 모니터링 목록에서 삭제하시겠습니까?`)) return;

  delete keywordFeeds[kw];
  const updated = StorageManager.removeKeyword(kw);

  if (currentKeyword === kw) {
    currentKeyword = updated.length ? updated[0] : '용인시';
    selectKeyword(currentKeyword);
  } else {
    renderKeywordChips();
    renderIssues();
  }
  showToast(`'# ${kw}' 키워드가 삭제되었습니다.`);
}

// Helper: Toggle Top Refresh Progress Bar
function setRefreshProgress(active) {
  const bar = document.getElementById('refreshProgressBar');
  if (bar) {
    if (active) {
      bar.classList.add('active');
    } else {
      bar.classList.remove('active');
    }
  }
}

// Realtime Feed Refresh Function
async function refreshFeed() {
  scrollToTop();
  const feedContainer = document.getElementById('feedContainer');
  try {
    const userKws = StorageManager.getKeywords();
    if (!userKws.includes(currentKeyword)) {
      currentKeyword = userKws.length ? userKws[0] : '용인시';
    }
    renderKeywordChips();
    await fetchKeywordIssues([currentKeyword]);
  } catch (err) {
    console.warn('Refresh error:', err);
  } finally {
    showToast('실시간 피드가 최신화되었습니다.');
  }
}

function renderSkeletonFeed(keywordName = '용인시') {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  container.innerHTML = `
    <div class="skeleton-wrapper" style="padding: 4px 0;">
      <div class="realtime-bar" style="background: #EFF6FF; border-color: #BFDBFE; color: #1D4ED8;">
        <div class="realtime-indicator">
          <div class="live-dot" style="background: #2563EB;"></div>
          <span># ${keywordName} 실시간 소식 동기화 중...</span>
        </div>
        <span style="font-size: 11px; opacity: 0.85;">최신 뉴스 수집</span>
      </div>

      <div style="display: flex; flex-direction: column; gap: 10px; margin-top: 10px;">
        <div style="background: #FFFFFF; border-radius: 14px; padding: 16px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
          <div class="skeleton-shimmer" style="height: 14px; width: 35%; border-radius: 4px; margin-bottom: 12px;"></div>
          <div class="skeleton-shimmer" style="height: 18px; width: 85%; border-radius: 4px; margin-bottom: 8px;"></div>
          <div class="skeleton-shimmer" style="height: 14px; width: 60%; border-radius: 4px;"></div>
        </div>
        <div style="background: #FFFFFF; border-radius: 14px; padding: 16px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
          <div class="skeleton-shimmer" style="height: 14px; width: 28%; border-radius: 4px; margin-bottom: 12px;"></div>
          <div class="skeleton-shimmer" style="height: 18px; width: 78%; border-radius: 4px; margin-bottom: 8px;"></div>
          <div class="skeleton-shimmer" style="height: 14px; width: 50%; border-radius: 4px;"></div>
        </div>
        <div style="background: #FFFFFF; border-radius: 14px; padding: 16px; border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
          <div class="skeleton-shimmer" style="height: 14px; width: 40%; border-radius: 4px; margin-bottom: 12px;"></div>
          <div class="skeleton-shimmer" style="height: 18px; width: 90%; border-radius: 4px; margin-bottom: 8px;"></div>
          <div class="skeleton-shimmer" style="height: 14px; width: 65%; border-radius: 4px;"></div>
        </div>
      </div>
    </div>
  `;
}

// 100% Original Realtime Feed Fetcher
async function fetchKeywordIssues(keywordsList, options = { silent: false }) {
  const kwKey = keywordsList.join(',');
  const hasCache = currentIssues && currentIssues.length > 0;

  if (!options.silent && !hasCache) {
    showToast(`'${keywordsList.join(', ')}' 최신 소식 수집 중...`);
  }

  // Render Skeleton UI ONLY if no current issues or cache exists
  if (!hasCache && currentNavTab === 'feed') {
    renderSkeletonFeed(keywordsList.join(', '));
  }

  try {
    const issues = await IssueApi.fetchKeywordIssues(keywordsList);
    if (issues && issues.length > 0) {
      tabFeeds['feed'] = issues;
      keywordFeeds[kwKey] = issues;
      try {
        const jsonStr = JSON.stringify(issues.slice(0, 300));
        localStorage.setItem(`cached_tab_issues_${kwKey}`, jsonStr);
        localStorage.setItem('cached_tab_issues_realtime', jsonStr);
        localStorage.setItem('cached_tab_issues_feed', jsonStr);
        StorageManager.saveFeedCache(issues);
      } catch (e) {
        StorageManager.cleanupOldCaches();
        try {
          const jsonStr = JSON.stringify(issues.slice(0, 300));
          localStorage.setItem('cached_tab_issues_realtime', jsonStr);
          localStorage.setItem('cached_tab_issues_feed', jsonStr);
          StorageManager.saveFeedCache(issues);
        } catch (err) {}
      }
      currentIssues = issues;
    }
  } catch (e) {
    console.warn('Realtime feed fetch error:', e);
  } finally {
    if (currentNavTab === 'feed') {
      renderIssues();
    }
  }
}

async function fetchTabIssues(tabName) {
  try {
    const cachedIssues = await IssueApi.loadDefaultIssues(tabName);
    if (cachedIssues && cachedIssues.length > 0) {
      tabFeeds[tabName] = cachedIssues;
      currentIssues = cachedIssues;
      renderIssues();
    }
  } catch (e) {
    console.warn(`Tab [${tabName}] cache load error:`, e);
  }

  // Background live update without blocking UI
  IssueApi.fetchLiveTabIssues(tabName).then(liveIssues => {
    if (liveIssues && liveIssues.length > 0) {
      const prevKeys = (currentIssues || []).map(i => i.id || i.title).join('|');
      const newKeys = liveIssues.map(i => i.id || i.title).join('|');

      tabFeeds[tabName] = liveIssues;
      if (currentNavTab === tabName) {
        currentIssues = liveIssues;
        if (prevKeys !== newKeys) {
          renderIssues();
        }
      }
    }
  }).catch(err => {
    console.warn(`Background live update error for tab [${tabName}]:`, err);
  });
}

async function switchNavTab(tab, btn) {
  scrollToTop();
  currentNavTab = tab;
  StorageManager.saveActiveNavTab(tab);

  const navBtns = document.querySelectorAll('.app-bottom-nav .nav-item');
  navBtns.forEach(b => b.classList.remove('active'));
  if (btn) {
    btn.classList.add('active');
  } else {
    const targetBtn = document.querySelector(`.app-bottom-nav .nav-item[data-tab="${tab}"]`);
    if (targetBtn) targetBtn.classList.add('active');
  }

  const keywordChips = document.getElementById('keywordChips');
  const etnewsHeader = document.getElementById('etnewsHeader');
  const pressHeader = document.getElementById('pressHeader');

  if (pressHeader) pressHeader.style.display = (tab === 'press') ? 'block' : 'none';

  if (tab === 'paper') {
    if (keywordChips) keywordChips.style.display = 'none';
    if (etnewsHeader) etnewsHeader.style.display = 'flex';
    const container = document.getElementById('feedContainer');
    if (container) {
      container.scrollTop = 0;
      container.removeAttribute('data-rendered-key');
    }
    scrollToTop();
    renderPaperProviderChips();
    await loadPaperForCurrentDate();
  } else {
    if (etnewsHeader) etnewsHeader.style.display = 'none';

    if (tab === 'feed') {
      if (keywordChips) keywordChips.style.display = 'flex';
      const userKeywords = StorageManager.getKeywords();
      if (!userKeywords.includes(currentKeyword)) {
        currentKeyword = userKeywords.length ? userKeywords[0] : '용인시';
      }
      renderKeywordChips();

      // Immediately render cached feed state from memory or localStorage if available
      const kwKey = [currentKeyword].join(',');
      const existingFeed = tabFeeds['feed'] || keywordFeeds[kwKey];
      if (existingFeed && existingFeed.length > 0) {
        currentIssues = existingFeed;
        renderIssues();
      } else {
        try {
          const localCached = localStorage.getItem(`cached_tab_issues_${kwKey}`) || 
                              localStorage.getItem('cached_tab_issues_realtime') || 
                              localStorage.getItem('cached_tab_issues_feed');
          if (localCached) {
            const parsed = JSON.parse(localCached);
            if (Array.isArray(parsed) && parsed.length > 0) {
              tabFeeds['feed'] = parsed;
              keywordFeeds[kwKey] = parsed;
              currentIssues = parsed;
              renderIssues();
            } else {
              currentIssues = [];
              renderSkeletonFeed(currentKeyword);
            }
          } else {
            currentIssues = [];
            renderSkeletonFeed(currentKeyword);
          }
        } catch (e) {
          currentIssues = [];
          renderSkeletonFeed(currentKeyword);
        }
      }

      await fetchKeywordIssues([currentKeyword], { silent: true });
    } else {
      if (keywordChips) keywordChips.style.display = 'none';
      if (tab === 'bookmark') {
        renderIssues();
      } else {
        if (tab === 'press' && !currentPressDept) {
          currentPressDept = '용인시';
        }
        await fetchTabIssues(tab);
      }
    }
  }
}

function resetAppCache() {
  if (confirm('로컬 저장소 캐시를 초기화하시겠습니까?')) {
    localStorage.clear();
    showToast('저장소 캐시가 초기화되었습니다.');
    setTimeout(() => {
      window.location.reload();
    }, 600);
  }
}

function getRecencyWeight(timeStr) {
  if (!timeStr) return 0;
  let s = String(timeStr).trim();

  // 1. Full datetime: YYYY-MM-DD HH:mm(:ss) or YYYY/MM/DD HH:mm(:ss)
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

  // 2. ISO 8601 string: e.g. 2026-10-23T09:01:00+09:00
  if (s.includes('T')) {
    const parsed = Date.parse(s);
    if (!isNaN(parsed)) return parsed;
  }

  // 3. Date only: YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
  match = s.match(/^(\d{4})[\.\/-](\d{1,2})[\.\/-](\d{1,2})/);
  if (match) {
    const year = parseInt(match[1], 10);
    const month = parseInt(match[2], 10) - 1;
    const day = parseInt(match[3], 10);
    return new Date(year, month, day, 0, 0, 0).getTime();
  }

  // 4. Short date with time: MM-DD HH:mm
  match = s.match(/^(\d{1,2})[\.\/-](\d{1,2})\s+(\d{1,2}):(\d{1,2})/);
  if (match) {
    const now = new Date();
    const month = parseInt(match[1], 10) - 1;
    const day = parseInt(match[2], 10);
    const hour = parseInt(match[3], 10);
    const min = parseInt(match[4], 10);
    return new Date(now.getFullYear(), month, day, hour, min).getTime();
  }

  // 5. Relative text
  if (s.includes('분 전')) {
    const m = parseInt(s, 10);
    return Date.now() - (m * 60 * 1000);
  }
  if (s.includes('시간 전')) {
    const h = parseInt(s, 10);
    return Date.now() - (h * 60 * 60 * 1000);
  }
  if (s.includes('일 전')) {
    const d = parseInt(s, 10);
    return Date.now() - (d * 24 * 60 * 60 * 1000);
  }
  if (s.includes('방금')) return Date.now();
  if (s.includes('어제')) return Date.now() - (24 * 60 * 60 * 1000);

  const fallback = Date.parse(s);
  if (!isNaN(fallback)) return fallback;

  return 0;
}

function normalizeTitleForDedupe(rawTitle) {
  if (!rawTitle) return '';
  let title = String(rawTitle).trim();

  // 1) Remove HTML entities & bracketed press metadata e.g. [속보], [단독], [포토], (종합), [특징주]
  title = title.replace(/&quot;|&amp;|&lt;|&gt;/g, '');
  title = title.replace(/\[[^\]]+\]|\([^\)]+\)/g, '');

  // 2) Remove suffix publisher attribution e.g. " - 연합뉴스", " - 경향신문"
  title = title.replace(/\s*-\s*[가-힣A-Za-z0-9]+$/g, '');

  // 3) Split by common separator delimiters (..., …, :, -, |, ·, 등)
  let parts = title.split(/[\.\.\.…:\-–—|·]/);
  let prefix = parts[0].trim();
  if (prefix.length < 6 && parts.length > 1) {
    prefix = (parts[0] + ' ' + parts[1]).trim();
  }
  if (prefix.length < 5) prefix = title;

  // 4) Clean non-alphanumeric/Korean chars & spaces
  return prefix.replace(/[^가-힣a-zA-Z0-9]/g, '').toLowerCase();
}

function isTitleDuplicate(normA, normB) {
  if (!normA || !normB) return false;
  if (normA === normB) return true;

  const minLen = Math.min(normA.length, normB.length);
  if (minLen >= 5) {
    const pA = normA.substring(0, Math.min(minLen, 12));
    const pB = normB.substring(0, Math.min(minLen, 12));
    if (pA === pB) return true;
  }

  if (minLen >= 6) {
    if (normA.includes(normB.substring(0, 8)) || normB.includes(normA.substring(0, 8))) return true;
  }

  if (normA.length >= 5 && normB.length >= 5) {
    let matches = 0;
    const totalBigrams = normA.length - 1;
    for (let i = 0; i < totalBigrams; i++) {
      const bigram = normA.substring(i, i + 2);
      if (normB.includes(bigram)) matches++;
    }
    const similarity = matches / totalBigrams;
    if (similarity >= 0.55) return true;
  }

  return false;
}

function prepareIssueMetadata(item) {
  if (!item) return null;
  if (item._meta) return item._meta;

  const title = item.title || '';
  const norm = normalizeTitleForDedupe(title);
  const clean = String(title).replace(/[^가-힣a-zA-Z0-9\s]/g, ' ');
  const words = Array.from(new Set(clean.split(/\s+/).filter(w => w.length >= 2)));
  const nums = (clean.match(/\d+(?:주|개|월|년|억|조|%|건|차|위|번|동|구)?/g) || []).map(n => n.replace(/\D/g, '')).filter(Boolean);
  const ts = getRecencyWeight(item.time);
  const pubScore = getPublisherScore(item.publisher);
  const score = ts + (pubScore * 60000) + (item.summary && item.summary.length ? 300000 : 0);

  const meta = { norm, clean, words, nums, ts, score };
  item._meta = meta;
  return meta;
}

function isSameTopicStory(titleA, titleB) {
  if (!titleA || !titleB) return false;

  const metaA = (typeof titleA === 'object' && titleA._meta) ? titleA._meta : (typeof titleA === 'object' ? prepareIssueMetadata(titleA) : prepareIssueMetadata({ title: titleA }));
  const metaB = (typeof titleB === 'object' && titleB._meta) ? titleB._meta : (typeof titleB === 'object' ? prepareIssueMetadata(titleB) : prepareIssueMetadata({ title: titleB }));

  if (!metaA || !metaB) return false;

  // 1) Direct title similarity
  if (isTitleDuplicate(metaA.norm, metaB.norm)) return true;

  // 2) Keyword & metric match (e.g. "85주", "1.09%", "25사단" + "서울", "아파트", "매매가")
  const numsA = metaA.nums;
  const numsB = metaB.nums;

  const commonNums = numsA.filter(na => numsB.includes(na));

  if (commonNums.length > 0) {
    let sharedNounCount = 0;
    for (const wA of metaA.words) {
      if (metaB.words.some(wB => wB.includes(wA) || wA.includes(wB))) {
        sharedNounCount++;
      }
    }
    if (sharedNounCount >= 2) return true;
  }

  // 3) Keyword Jaccard Overlap check (3+ shared nouns without numbers)
  const wordsA = metaA.words;
  const wordsB = metaB.words;
  let overlapCount = 0;
  for (const wA of wordsA) {
    if (wordsB.some(wB => wB === wA || (wA.length >= 3 && wB.includes(wA)))) {
      overlapCount++;
    }
  }
  const minWords = Math.min(wordsA.length, wordsB.length);
  if (minWords >= 3 && (overlapCount / minWords) >= 0.60) {
    return true;
  }

  return false;
}

function getPublisherScore(publisherName) {
  const pub = (publisherName || '').toLowerCase();
  const MAJORS = [
    '연합뉴스', '연합뉴스tv', '조선일보', '중앙일보', '동아일보', '한겨레', '경향신문',
    '매일경제', '한국경제', 'kbs', 'sbs', 'mbc', 'ytn', '오마이뉴스', '국민일보',
    '세계일보', '서울신문', '전자신문', '이데일리', '머니투데이', '파이낸셜뉴스'
  ];
  if (MAJORS.some(m => pub.includes(m))) return 15;
  return 0;
}

function deduplicateIssues(items) {
  if (!Array.isArray(items) || items.length === 0) return [];

  for (let i = 0; i < items.length; i++) {
    prepareIssueMetadata(items[i]);
  }

  const uniqueItems = [];

  for (const item of items) {
    const rawTitle = item.title || '';
    if (!rawTitle) continue;

    let duplicateIndex = -1;
    for (let i = 0; i < uniqueItems.length; i++) {
      if (isSameTopicStory(item, uniqueItems[i])) {
        duplicateIndex = i;
        break;
      }
    }

    if (duplicateIndex === -1) {
      uniqueItems.push(item);
    } else {
      const existing = uniqueItems[duplicateIndex];
      const existingScore = existing._meta ? existing._meta.score : 0;
      const currentScore = item._meta ? item._meta.score : 0;

      if (currentScore > existingScore) {
        uniqueItems[duplicateIndex] = item;
      }
    }
  }

  return uniqueItems;
}

function renderIssues() {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  updateHeaderScrapBadge();
  const scraps = StorageManager.getScraps();

  // --- Paper View (지면보기) ---
  if (currentNavTab === 'paper') {
    renderPaperView();
    return;
  }

  container.removeAttribute('data-rendered-key');

  // --- Bookmark View (보관함) ---
  if (currentNavTab === 'bookmark') {
    let html = `
      <div class="realtime-bar" style="background:#F8FAFC; border-color:#E2E8F0; color:#334155;">
        <div class="realtime-indicator">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
          </svg>
          <span>보관한 중요 이슈 (${scraps.length}건)</span>
        </div>
        <span style="font-size: 11.5px; color:#64748B;">보관함</span>
      </div>
    `;

    if (scraps.length === 0) {
      html += `
        <div class="empty-state-wrap">
          <div class="empty-icon-circle">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
            </svg>
          </div>
          <div class="empty-title">보관된 이슈가 없습니다</div>
          <div class="empty-desc">주요 기사 카드의 [보관] 버튼을 누르면 이 곳에 안전하게 모아볼 수 있습니다.</div>
        </div>
      `;
    } else {
      scraps.forEach(item => {
        html += renderIssueCardHtml(item, true);
      });
    }

    container.innerHTML = html;
    return;
  }

  // --- Realtime Feed View (100% Original Screen & Code) ---
  if (currentNavTab === 'feed') {
    const SPAM_PROMO_KEYWORDS = [
      '특별분양', '회사보유분', '모델하우스', '임대수익', '조합원 모집', '조합원',
      '지식산업센터', '선착순 계약', '선착순 분양', '분양가 상한제', '분양안내', '상가 분양',
      '수익형 부동산', '급등주', '상한가 종목', '무료 리딩방', '수익률 보장',
      '소정의 원고료', '협찬 받아', '할인 쿠폰'
    ];

    let displayItems = currentIssues.filter(item => {
      const itemTitle = (item.title || '').toLowerCase();
      return !SPAM_PROMO_KEYWORDS.some(s => itemTitle.includes(s));
    });

    displayItems.forEach(it => prepareIssueMetadata(it));
    displayItems.sort((a, b) => (b._meta ? b._meta.ts : 0) - (a._meta ? a._meta.ts : 0));
    displayItems = deduplicateIssues(displayItems);

    let html = `
      <div class="realtime-bar" onclick="executeTabRefresh()" style="cursor:pointer;" title="클릭 시 실시간 소식 최신화">
        <div class="realtime-indicator">
          <div class="live-dot"></div>
          <span>실시간 이슈 피드 (${displayItems.length}건)</span>
        </div>
        <div style="display:flex; align-items:center; gap:4px; font-size:11.5px; opacity:0.85;">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
            <path d="M21 3v5h-5"/>
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
            <path d="M8 16H3v5"/>
          </svg>
          <span id="updateTimestamp">새로고침</span>
        </div>
      </div>
    `;

    if (displayItems.length === 0) {
      html += `
        <div class="empty-state-wrap">
          <div class="empty-icon-circle">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/>
              <path d="M18 14h-8"/>
              <path d="M15 18h-5"/>
              <path d="M10 6h8v4h-8V6Z"/>
            </svg>
          </div>
          <div class="empty-title">'# ${currentKeyword}' 관련 기사 수집 중</div>
          <div class="empty-desc">실시간 포털에서 최신 뉴스를 불러오고 있습니다. 잠시만 기다려 주세요.</div>
        </div>
      `;
    } else {
      displayItems.forEach(item => {
        const isScrapped = StorageManager.isScrapped(item.title);
        html += renderIssueCardHtml(item, isScrapped);
      });
    }

    container.innerHTML = html;
    return;
  }

  // --- Other Feed Views ('exclusive', 'press') ---
  const tabTitles = {
    feed: '언론보도',
    press: '공식 보도자료',
    paper: '지면신문',
    exclusive: '주요기사'
  };

  let displayItems = currentIssues;
  if (currentNavTab === 'press') {
    renderPressDeptChips();
    if (currentPressDept === '용인시') {
      displayItems = currentIssues.filter(item => (item.publisher || '').includes('용인시') || (item.badge || '').includes('용인시'));
    } else if (currentPressDept === 'central') {
      displayItems = currentIssues.filter(item => !(item.publisher || '').includes('용인시') && !(item.badge || '').includes('용인시'));
    } else if (currentPressDept && currentPressDept !== 'all') {
      displayItems = currentIssues.filter(item => (item.publisher || '').includes(currentPressDept) || (item.badge || '').includes(currentPressDept));
    }
  }

  let html = `
    <div class="realtime-bar" onclick="executeTabRefresh()" style="cursor:pointer;" title="클릭 시 최신 소식 새로고침">
      <div class="realtime-indicator">
        <div class="live-dot"></div>
        <span>${tabTitles[currentNavTab] || '언론보도'} (${displayItems.length}건)</span>
      </div>
      <div style="display:flex; align-items:center; gap:4px; font-size:11.5px; opacity:0.85;">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
          <path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
          <path d="M8 16H3v5"/>
        </svg>
        <span>새로고침</span>
      </div>
    </div>
  `;

  if (displayItems.length === 0) {
    html += `
      <div class="empty-state-wrap">
        <div class="empty-icon-circle">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m3 11 18-5v12L3 13v-2z"/>
            <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>
          </svg>
        </div>
        <div class="empty-title">수집된 소식이 없습니다</div>
        <div class="empty-desc">선택하신 카테고리의 최신 공식 발표 자료를 확인 중입니다.</div>
      </div>
    `;
  } else {
    displayItems.forEach(item => {
      const isScrapped = StorageManager.isScrapped(item.title);
      html += renderIssueCardHtml(item, isScrapped);
    });
  }

  container.innerHTML = html;
}

function renderPressDeptChips() {
  const chipContainer = document.getElementById('pressDeptChips');
  if (!chipContainer || currentNavTab !== 'press') return;

  const deptCounts = {};
  currentIssues.forEach(item => {
    const dept = item.publisher || '정부 부처';
    deptCounts[dept] = (deptCounts[dept] || 0) + 1;
  });

  const yonginCount = deptCounts['용인시'] || 0;
  const centralCount = currentIssues.length - yonginCount;

  let html = `
    <span class="chip ${currentPressDept === '용인시' ? 'active' : ''}" onclick="selectPressDept('용인시')">
      용인시 (${yonginCount})
    </span>
    <span class="chip ${currentPressDept === 'central' ? 'active' : ''}" onclick="selectPressDept('central')">
      중앙부처 전체 (${centralCount})
    </span>
  `;

  Object.keys(deptCounts).forEach(dept => {
    if (dept === '용인시') return;
    const count = deptCounts[dept];
    const isActive = (currentPressDept === dept);
    html += `
      <span class="chip ${isActive ? 'active' : ''}" onclick="selectPressDept('${dept}')">
        ${dept} (${count})
      </span>
    `;
  });

  chipContainer.innerHTML = html;
}

function selectPressDept(dept) {
  scrollToTop();
  currentPressDept = dept;
  renderIssues();
}

function cleanBadgeText(badge, publisher) {
  let text = String(badge || publisher || '').trim();
  text = text.replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0F\u200D\u200B]/gu, '').trim();
  text = text.replace(/^[·\-\s|]+|[·\-\s|]+$/g, '').trim();
  if (!text || text === '뉴스' || text === '이슈') {
    let p = String(publisher || '').replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0F\u200D\u200B]/gu, '').trim();
    text = p || '언론보도';
  }
  return text || '언론보도';
}

function renderIssueCardHtml(item, isScrapped) {
  const hasPreSummary = item.summary && item.summary.length > 0;
  const summaryItems = hasPreSummary ? item.summary.map(s => `<li>${s}</li>`).join('') : '';
  const isNegBadge = item.is_negative ? `<span class="is-neg-tag"><span class="neg-dot"></span>주요 이슈</span>` : '';

  const cleanBadge = cleanBadgeText(item.badge, item.publisher);
  const titleAttr = (item.title || '').replace(/"/g, '&quot;');
  const contentAttr = (item.content || item.title || '').replace(/"/g, '&quot;');
  const urlAttr = (item.url || '#').replace(/"/g, '&quot;');
  const publisherAttr = (item.publisher || cleanBadge).replace(/"/g, '&quot;');
  const badgeAttr = cleanBadge.replace(/"/g, '&quot;');
  const timeAttr = (item.time || '').replace(/"/g, '&quot;');

  return `
    <article class="issue-card" data-title="${titleAttr}" data-url="${urlAttr}" data-content="${contentAttr}" data-keyword="${item.keyword || '뉴스'}" data-publisher="${publisherAttr}" data-badge="${badgeAttr}" data-time="${timeAttr}">
      <div class="card-top">
        <span class="source-tag source-news">${cleanBadge} ${isNegBadge}</span>
        <span class="card-date card-time">${formatRelativeTime(item.time)}</span>
      </div>
      <h3 class="card-title">${item.title}</h3>
      
      <button class="ai-summary-toggle-btn" onclick="toggleOnDemandAiSummary(this)" type="button">
        <svg class="ai-spark-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3z"/>
        </svg>
        <span>AI 핵심 요약</span>
        <svg class="chevron-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      <div class="ai-summary-box" style="display: none;" data-generated="${hasPreSummary ? 'true' : 'false'}">
        <div class="ai-summary-head">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3z"/>
          </svg>
          FactChat AI 분석 요약
        </div>
        <ul class="ai-summary-list">
          ${summaryItems}
        </ul>
      </div>

      <div class="card-footer">
        <div class="card-btns">
          <button class="card-action-btn ${isScrapped ? 'scrapped' : ''}" onclick="toggleScrap(this)" type="button">
            <svg class="card-btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="${isScrapped ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
            </svg>
            <span>${isScrapped ? '보관됨' : '보관'}</span>
          </button>
          <button class="card-action-btn" onclick="shareArticle(this)" type="button">
            <svg class="card-btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="18" cy="5" r="3"/>
              <circle cx="6" cy="12" r="3"/>
              <circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
            <span>공유</span>
          </button>
        </div>
        <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="link-btn">
          <span>원문 보기</span>
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </div>
    </article>
  `;
}

async function toggleOnDemandAiSummary(btn) {
  const card = btn.closest('.issue-card');
  if (!card) return;

  const box = card.querySelector('.ai-summary-box');
  if (!box) return;

  const isHidden = (box.style.display === 'none' || !box.style.display);

  if (isHidden) {
    box.style.display = 'block';
    btn.classList.add('open');

    const isGenerated = box.getAttribute('data-generated') === 'true';
    if (!isGenerated) {
      const title = card.getAttribute('data-title') || '';
      const content = card.getAttribute('data-content') || title;
      const keyword = card.getAttribute('data-keyword') || '이슈';
      const apiKey = StorageManager.getFactChatKey();

      const listElem = box.querySelector('.ai-summary-list');
      if (listElem) {
        listElem.innerHTML = `<li style="color:#64748B;"><span class="spin-icon">●</span> FactChat AI 핵심 요약 분석 중...</li>`;
      }

      if (!apiKey) {
        if (listElem) {
          listElem.innerHTML = `
            <li style="color:#D97706; font-weight:700;">FactChat API 키 설정 필요</li>
            <li style="font-size:11.5px; color:#64748B; margin-bottom: 6px;">우측 상단 설정 아이콘을 눌러 FactChat API 키를 등록하시면 실시간 AI 요약이 가동됩니다.</li>
            <li style="list-style:none; margin-top:4px;"><button onclick="toggleSettingsModal()" style="background:#2563EB; color:white; border:none; padding:5px 12px; border-radius:6px; font-size:11.5px; font-weight:700; cursor:pointer;">설정에서 API 키 등록</button></li>
          `;
        }
        return;
      }

      try {
        const res = await IssueApi.generateSummary({ title, keyword, content, apiKey });
        if (res && res.summary && res.summary.length > 0) {
          box.setAttribute('data-generated', 'true');
          listElem.innerHTML = res.summary.map(s => `<li>${s}</li>`).join('');
        } else {
          listElem.innerHTML = `<li>본 기사의 주요 팩트 및 핵심 소식입니다.</li>`;
        }
      } catch (err) {
        console.warn('AI summary error:', err);
        if (listElem) {
          listElem.innerHTML = `<li style="color:#EF4444;">AI 요약 생성 중 오류가 발생했습니다 (${err.message}).</li>`;
        }
      }
    }
  } else {
    box.style.display = 'none';
    btn.classList.remove('open');
  }
}

function toggleScrap(btn) {
  const card = btn.closest('.issue-card');
  if (!card) return;

  const title = card.getAttribute('data-title');
  const url = card.getAttribute('data-url');
  const content = card.getAttribute('data-content');
  const keyword = card.getAttribute('data-keyword');
  const publisher = card.getAttribute('data-publisher');
  const badge = card.getAttribute('data-badge');
  const time = card.getAttribute('data-time');

  const { isScrapped } = StorageManager.toggleScrap({ title, url, content, keyword, publisher, badge, time });

  if (isScrapped) {
    btn.classList.add('scrapped');
    btn.innerHTML = `
      <svg class="card-btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
      </svg>
      <span>보관됨</span>
    `;
    showToast('보관함에 추가되었습니다.');
  } else {
    btn.classList.remove('scrapped');
    btn.innerHTML = `
      <svg class="card-btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
      </svg>
      <span>보관</span>
    `;
    showToast('보관함에서 삭제되었습니다.');
  }

  updateHeaderScrapBadge();

  if (currentNavTab === 'bookmark') {
    renderIssues();
  }
}

function shareArticle(btn) {
  const card = btn.closest('.issue-card');
  if (!card) return;
  const title = card.getAttribute('data-title') || '용인 핫이슈';
  const url = card.getAttribute('data-url') || window.location.href;
  const shareText = `[용인 핫이슈] ${title}\n${url}`;

  if (navigator.share) {
    navigator.share({ title: title, text: title, url: url }).catch(() => { });
  } else {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(shareText);
      } else {
        const ta = document.createElement('textarea');
        ta.value = shareText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      showToast('기사 링크가 복사되었습니다.');
    } catch (e) {
      showToast(url);
    }
  }
}

// --- Paper View logic ---
function getPaperScrollY() {
  const container = document.getElementById('feedContainer');
  return container ? container.scrollTop : 0;
}

function saveCurrentPaperScroll() {
  // Purposely empty: Never store or restore mid-article scroll positions in paper view
}

function restorePaperScrollY() {
  // Always guarantee paper view starts cleanly at the top (scrollTop = 0)
  const container = document.getElementById('feedContainer');
  if (container) container.scrollTop = 0;
  scrollToTop();
}

async function loadPaperForCurrentDate(forceRefresh = false) {
  const cacheKey = `${currentPaperProvider}_${currentPaperDate}`;

  const picker = document.getElementById('etnewsDatePicker');
  if (picker) picker.value = currentPaperDate;

  const savedSection = sessionStorage.getItem(`paper_sec_${cacheKey}`) || localStorage.getItem(`paper_sec_${cacheKey}`);
  const container = document.getElementById('feedContainer');

  if (forceRefresh && container) {
    container.removeAttribute('data-rendered-key');
  }

  // 1. Instant rendering from Memory / Local Storage Cache
  let cachedData = paperFeedsCache[cacheKey] || StorageManager.getPaperCache(cacheKey);
  let hasRenderedCache = false;

  if (cachedData && cachedData.articles && cachedData.articles.length > 0) {
    paperData = cachedData;
    paperFeedsCache[cacheKey] = cachedData;
    currentPaperSection = (savedSection && (savedSection === 'all' || (cachedData.sections && cachedData.sections.includes(savedSection)))) ? savedSection : 'all';
    renderPaperSections();
    renderPaperView();
    hasRenderedCache = true;
  }

  // 2. Only show loading placeholder if container is completely empty
  const currentKey = `${currentPaperProvider}_${currentPaperDate}_${currentPaperSection}`;
  if (!hasRenderedCache && container && !container.querySelector('.issue-card')) {
    container.innerHTML = `
      <div class="empty-state-wrap">
        <div class="empty-icon-circle">
          <svg class="spin-icon" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
        </div>
        <div class="empty-title">지면 신문 데이터 수집 중</div>
        <div class="empty-desc">오늘의 최신 지면 기사를 준비하고 있습니다.</div>
      </div>
    `;
  }

  // 3. Background live fetch & silent update
  try {
    const liveData = await IssueApi.fetchPaperNews(currentPaperProvider, currentPaperDate);
    if (liveData && liveData.articles && liveData.articles.length > 0) {
      paperData = liveData;
      paperFeedsCache[cacheKey] = liveData;
      StorageManager.savePaperCache(cacheKey, liveData);

      if (currentNavTab === 'paper') {
        currentPaperSection = (savedSection && (savedSection === 'all' || (liveData.sections && liveData.sections.includes(savedSection)))) ? savedSection : 'all';
        renderPaperSections();
        renderPaperView();
      }
    }
  } catch (err) {
    console.warn('Paper fetch error:', err);
  }
}

function renderPaperSections() {
  const sectionContainer = document.getElementById('etnewsSectionChips');
  if (!sectionContainer || !paperData || !paperData.sections) return;

  let html = `
    <span class="chip ${currentPaperSection === 'all' ? 'active' : ''}" onclick="selectPaperSection('all')">
      전체 면 (${paperData.articles ? paperData.articles.length : 0})
    </span>
  `;
  paperData.sections.forEach(sec => {
    const count = paperData.categorized[sec] ? paperData.categorized[sec].length : 0;
    const isActive = currentPaperSection === sec;
    html += `
      <span class="chip ${isActive ? 'active' : ''}" onclick="selectPaperSection('${sec}')">
        ${sec} (${count})
      </span>
    `;
  });

  sectionContainer.innerHTML = html;
}

function selectPaperSection(sec) {
  currentPaperSection = sec;
  const cacheKey = `${currentPaperProvider}_${currentPaperDate}`;
  try {
    sessionStorage.setItem(`paper_sec_${cacheKey}`, sec);
    localStorage.setItem(`paper_sec_${cacheKey}`, sec);
  } catch (e) { }

  const container = document.getElementById('feedContainer');
  if (container) {
    container.removeAttribute('data-rendered-key');
    container.scrollTop = 0;
  }
  scrollToTop();

  renderPaperSections();
  renderPaperView(false);
}

function onPaperDateChange(val) {
  if (val) {
    currentPaperDate = val;
    const container = document.getElementById('feedContainer');
    if (container) {
      container.removeAttribute('data-rendered-key');
      container.scrollTop = 0;
    }
    scrollToTop();
    loadPaperForCurrentDate();
  }
}

function setPaperToday() {
  currentPaperDate = getTodayKstStr();
  const picker = document.getElementById('etnewsDatePicker');
  if (picker) picker.value = currentPaperDate;
  const container = document.getElementById('feedContainer');
  if (container) {
    container.removeAttribute('data-rendered-key');
    container.scrollTop = 0;
  }
  scrollToTop();
  loadPaperForCurrentDate();
}

function renderPaperView(isRestoring = false) {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  const providerObj = PAPER_PROVIDERS.find(p => p.id === currentPaperProvider) || PAPER_PROVIDERS[0];

  if (!paperData || !paperData.articles || paperData.articles.length === 0) {
    container.innerHTML = `
      <div class="empty-state-wrap">
        <div class="empty-icon-circle">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/>
            <path d="M3 9h18"/>
            <path d="M9 21V9"/>
          </svg>
        </div>
        <div class="empty-title">${providerObj.name} 지면 기사 수집 중</div>
        <div class="empty-desc">선택하신 날짜(${currentPaperDate})의 인쇄 지면 데이터를 불러오는 중입니다.</div>
      </div>
    `;
    container.removeAttribute('data-rendered-key');
    container.scrollTop = 0;
    scrollToTop();
    return;
  }

  const currentKey = `${currentPaperProvider}_${currentPaperDate}_${currentPaperSection}`;
  const existingKey = container.getAttribute('data-rendered-key');

  // If container ALREADY has rendered cards for this exact provider, date & section, simply ensure top
  if (existingKey === currentKey && container.querySelector('.issue-card')) {
    container.scrollTop = 0;
    scrollToTop();
    return;
  }

  let articlesToRender = [];
  if (currentPaperSection === 'all') {
    // 전체 면 선택 시: 모든 분야의 기사를 최신순으로 정렬하여 표시
    articlesToRender = [...(paperData.articles || [])];
    articlesToRender.forEach(it => prepareIssueMetadata(it));
    articlesToRender.sort((a, b) => (b._meta ? b._meta.ts : 0) - (a._meta ? a._meta.ts : 0));
  } else if (paperData.categorized && paperData.categorized[currentPaperSection]) {
    // 분야별 필터 선택 시: 해당 분야의 기존 기사 목록 표시
    articlesToRender = paperData.categorized[currentPaperSection];
  } else {
    articlesToRender = paperData.articles || [];
  }

  let html = `
    <div class="realtime-bar" style="background:#F8FAFC; border-color:#CBD5E1; color:#334155; cursor:pointer;" onclick="executeTabRefresh()" title="클릭 시 지면 신문 최신화">
      <div class="realtime-indicator">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="18" height="18" x="3" y="3" rx="2"/>
          <path d="M3 9h18"/>
          <path d="M9 21V9"/>
        </svg>
        <span>${providerObj.name} 지면 (${articlesToRender.length}건)</span>
      </div>
      <div style="display:flex; align-items:center; gap:4px; font-size:11.5px; opacity:0.85;">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
          <path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
          <path d="M8 16H3v5"/>
        </svg>
        <span>${currentPaperDate}</span>
      </div>
    </div>
  `;

  articlesToRender.forEach(item => {
    const isScrapped = StorageManager.isScrapped(item.title);
    html += renderIssueCardHtml(item, isScrapped);
  });

  container.innerHTML = html;
  container.setAttribute('data-rendered-key', currentKey);
  container.scrollTop = 0;
  scrollToTop();
}

function handleBackOrRestore() {
  if (currentNavTab === 'paper') {
    const container = document.getElementById('feedContainer');
    if (container) container.scrollTop = 0;
    scrollToTop();
  }
}

window.addEventListener('popstate', () => {
  handleBackOrRestore();
});

window.addEventListener('pageshow', () => {
  handleBackOrRestore();
});

// --- Settings Modal ---
function toggleSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (!modal) return;
  const isShow = modal.classList.contains('show');
  if (isShow) {
    modal.classList.remove('show');
  } else {
    modal.classList.add('show');
    renderKeywordChips();
    const apiKey = StorageManager.getFactChatKey();
    const input = document.getElementById('factchatApiKeyInput');
    const badge = document.getElementById('factchatKeyBadge');
    if (input) input.value = apiKey;
    if (badge) {
      if (apiKey) {
        badge.className = 'api-key-badge active';
        badge.textContent = 'Key 등록됨';
      } else {
        badge.className = 'api-key-badge warning';
        badge.textContent = '키 입력 필요';
      }
    }
  }
}

function saveFactchatKey() {
  const input = document.getElementById('factchatApiKeyInput');
  if (!input) return;
  const val = input.value.trim();
  StorageManager.saveFactChatKey(val);
  showToast(val ? 'FactChat API 키가 저장되었습니다.' : 'API 키가 삭제되었습니다.');
  toggleSettingsModal();
}

function togglePasswordVisibility() {
  const input = document.getElementById('factchatApiKeyInput');
  if (!input) return;
  const isPw = input.type === 'password';
  input.type = isPw ? 'text' : 'password';

  const icon = document.getElementById('eyeIcon');
  if (icon) {
    if (isPw) {
      // Eye Slash SVG
      icon.innerHTML = `
        <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>
        <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/>
        <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/>
        <line x1="2" x2="22" y1="2" y2="22"/>
      `;
    } else {
      // Normal Eye SVG
      icon.innerHTML = `
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
        <circle cx="12" cy="12" r="3"/>
      `;
    }
  }
}

function showToast(msg) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.className = 'app-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => { toast.classList.remove('show'); }, 2200);
}

function checkOnboardingGuide() {
  const completed = localStorage.getItem('onboarding_seen_v1');
  if (!completed) {
    const modal = document.getElementById('onboardingModal');
    if (modal) {
      setTimeout(() => {
        modal.classList.add('show');
      }, 200);
    }
  }
}

function closeOnboardingModal() {
  localStorage.setItem('onboarding_seen_v1', 'true');
  const modal = document.getElementById('onboardingModal');
  if (modal) {
    modal.classList.remove('show');
  }
}

// Initializer
document.addEventListener('DOMContentLoaded', () => {
  const userKws = StorageManager.getKeywords();
  currentKeyword = userKws.length ? userKws[0] : '용인시';
  renderKeywordChips();
  updateHeaderScrapBadge();
  checkOnboardingGuide();

  const savedTab = StorageManager.getActiveNavTab();
  if (savedTab && savedTab !== 'feed') {
    const navBtn = document.querySelector(`.app-bottom-nav .nav-item[data-tab="${savedTab}"]`);
    switchNavTab(savedTab, navBtn);
  } else {
    // Restore cached feed state instantly on initial load if available
    const kwKey = [currentKeyword].join(',');
    const localCached = localStorage.getItem(`cached_tab_issues_${kwKey}`) || 
                        localStorage.getItem('cached_tab_issues_realtime') || 
                        localStorage.getItem('cached_tab_issues_feed');
    let restored = false;
    if (localCached) {
      try {
        const parsed = JSON.parse(localCached);
        if (Array.isArray(parsed) && parsed.length > 0) {
          tabFeeds['feed'] = parsed;
          keywordFeeds[currentKeyword] = parsed;
          currentIssues = parsed;
          renderIssues();
          restored = true;
        }
      } catch (e) {}
    }

    if (!restored) {
      const feedCache = StorageManager.getFeedCache();
      if (Array.isArray(feedCache) && feedCache.length > 0) {
        tabFeeds['feed'] = feedCache;
        keywordFeeds[currentKeyword] = feedCache;
        currentIssues = feedCache;
        renderIssues();
        restored = true;
      }
    }

    if (!restored) {
      renderSkeletonFeed(currentKeyword);
    }

    fetchKeywordIssues([currentKeyword], { silent: true });
  }

  // Initialize Pull-To-Refresh on all tabs
  initPullToRefresh();
});

function openInstallModal() {
  const modal = document.getElementById('installModal');
  if (modal) modal.classList.add('show');
}

function closeInstallModal() {
  const modal = document.getElementById('installModal');
  if (modal) modal.classList.remove('show');
}

function switchInstallTab(type) {
  const iosGuide = document.getElementById('installIosGuide');
  const androidGuide = document.getElementById('installAndroidGuide');
  const iosBtn = document.getElementById('tabIosBtn');
  const androidBtn = document.getElementById('tabAndroidBtn');

  if (type === 'ios') {
    if (iosGuide) iosGuide.style.display = 'block';
    if (androidGuide) androidGuide.style.display = 'none';
    if (iosBtn) {
      iosBtn.style.background = 'white';
      iosBtn.style.color = '#1E293B';
      iosBtn.style.boxShadow = '0 2px 4px rgba(0,0,0,0.06)';
    }
    if (androidBtn) {
      androidBtn.style.background = 'transparent';
      androidBtn.style.color = '#64748B';
      androidBtn.style.boxShadow = 'none';
    }
  } else {
    if (iosGuide) iosGuide.style.display = 'none';
    if (androidGuide) androidGuide.style.display = 'block';
    if (androidBtn) {
      androidBtn.style.background = 'white';
      androidBtn.style.color = '#1E293B';
      androidBtn.style.boxShadow = '0 2px 4px rgba(0,0,0,0.06)';
    }
    if (iosBtn) {
      iosBtn.style.background = 'transparent';
      iosBtn.style.color = '#64748B';
      iosBtn.style.boxShadow = 'none';
    }
  }
}

/* --- Pull-To-Refresh (PTR) Implementation Across All Tabs --- */
function getPtrBanner() {
  return document.getElementById('ptrBanner');
}

function initPullToRefresh() {
  const container = document.getElementById('feedContainer');
  const banner = document.getElementById('ptrBanner');
  const screen = document.querySelector('.app-screen') || document.body;
  if (!container || !banner) return;

  let startY = 0;
  let isPulling = false;
  let isRefreshing = false;
  let isMouseDown = false;
  const THRESHOLD = 52;

  const updatePtrVisuals = (dy) => {
    if (dy <= 0) return;
    const pullDist = Math.min(Math.pow(dy, 0.82), 52);
    banner.classList.add('pulling');
    banner.style.height = `${pullDist}px`;
    banner.style.opacity = `${Math.min(pullDist / THRESHOLD, 1)}`;
    banner.style.marginTop = '0';
    banner.style.marginBottom = '0';

    const text = banner.querySelector('.ptr-text');
    if (pullDist >= THRESHOLD) {
      banner.classList.add('release');
      if (text) text.textContent = '손을 놓으면 최신 소식 수집';
    } else {
      banner.classList.remove('release');
      if (text) text.textContent = '아래로 당겨서 새로고침';
    }
  };

  const handleDragEnd = async () => {
    if (!isPulling || isRefreshing) return;
    isPulling = false;
    isMouseDown = false;

    const currentHeight = parseFloat(banner.style.height || '0');
    banner.classList.remove('pulling');

    if (currentHeight >= THRESHOLD) {
      isRefreshing = true;
      try {
        await executeTabRefresh();
      } finally {
        isRefreshing = false;
      }
    } else {
      banner.style.height = '0';
      banner.style.opacity = '0';
      banner.style.marginTop = '0';
      banner.style.marginBottom = '0';
      banner.classList.remove('release');
    }
  };

  // Touch events for Mobile: attached to screen so pulling on header works on all tabs
  screen.addEventListener('touchstart', (e) => {
    if (container.scrollTop <= 0 && !isRefreshing && e.touches.length === 1) {
      startY = e.touches[0].pageY;
      isPulling = true;
    }
  }, { passive: true });

  screen.addEventListener('touchmove', (e) => {
    if (!isPulling || isRefreshing || e.touches.length !== 1) return;
    const currentY = e.touches[0].pageY;
    const dy = currentY - startY;
    if (dy > 0 && container.scrollTop <= 0) {
      updatePtrVisuals(dy);
    }
  }, { passive: true });

  screen.addEventListener('touchend', handleDragEnd, { passive: true });
  screen.addEventListener('touchcancel', handleDragEnd, { passive: true });

  // Mouse drag support for Desktop preview
  screen.addEventListener('mousedown', (e) => {
    if (e.target.closest('button, input, select, .nav-item, .chip, .etnews-today-btn, .ai-summary-toggle-btn')) return;
    if (container.scrollTop <= 0 && !isRefreshing && e.button === 0) {
      startY = e.pageY;
      isMouseDown = true;
      isPulling = true;
    }
  });

  window.addEventListener('mousemove', (e) => {
    if (!isMouseDown || !isPulling || isRefreshing) return;
    const dy = e.pageY - startY;
    if (dy > 0 && container.scrollTop <= 0) {
      updatePtrVisuals(dy);
    }
  });

  window.addEventListener('mouseup', () => {
    if (isMouseDown) {
      handleDragEnd();
    }
  });
}

// Unified Refresh Architecture across ALL 4 TABS
async function executeTabRefresh() {
  const banner = document.getElementById('ptrBanner');
  const feedContainer = document.getElementById('feedContainer');
  const realtimeBar = document.querySelector('.realtime-bar');

  setRefreshProgress(true);
  if (realtimeBar) realtimeBar.classList.add('refreshing');
  if (feedContainer) feedContainer.style.opacity = '0.7';

  const currentTab = currentNavTab;
  let tabLabel = '언론보도';
  if (currentTab === 'paper') tabLabel = '지면신문';
  else if (currentTab === 'exclusive') tabLabel = '주요기사';
  else if (currentTab === 'press') tabLabel = '보도자료';
  else if (currentTab === 'bookmark') tabLabel = '보관함';

  if (banner) {
    banner.className = 'ptr-banner refreshing';
    banner.style.height = '38px';
    banner.style.opacity = '1';
    banner.style.marginTop = '0';
    banner.style.marginBottom = '0';
    const text = banner.querySelector('.ptr-text');
    if (text) text.textContent = `${tabLabel} 최신화 중...`;
  }

  try {
    switch (currentTab) {
      case 'feed':
        await refreshFeed();
        break;
      case 'paper':
        await loadPaperForCurrentDate(true);
        break;
      case 'exclusive':
      case 'press':
        const liveIssues = await IssueApi.fetchLiveTabIssues(currentTab);
        if (liveIssues && liveIssues.length > 0) {
          tabFeeds[currentTab] = liveIssues;
          currentIssues = liveIssues;
          renderIssues();
        }
        break;
      case 'bookmark':
        renderIssues();
        break;
      default:
        await refreshFeed();
        break;
    }
  } catch (err) {
    console.warn('executeTabRefresh error:', err);
  } finally {
    if (feedContainer) feedContainer.style.opacity = '1';
    setRefreshProgress(false);
    if (realtimeBar) realtimeBar.classList.remove('refreshing');
    if (banner) {
      banner.className = 'ptr-banner success';
      const text = banner.querySelector('.ptr-text');
      if (text) text.textContent = `${tabLabel} 동기화 완료`;
      setTimeout(() => {
        banner.style.height = '0';
        banner.style.opacity = '0';
        setTimeout(() => {
          banner.className = 'ptr-banner';
          if (text) text.textContent = '아래로 당겨서 새로고침';
        }, 260);
      }, 550);
    }
  }
}
