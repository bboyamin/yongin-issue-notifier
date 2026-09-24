/**
 * Application Controller & UI View Coordinator
 */
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
  { id: 'mknews', name: '매일경제', badge: '📈' },
  { id: 'etnews', name: '전자신문', badge: '📰' },
  { id: 'khan', name: '경향신문', badge: '🗞️' }
];

let currentPaperProvider = StorageManager.getPaperProvider() || 'mknews';
if (!PAPER_PROVIDERS.some(p => p.id === currentPaperProvider)) {
  currentPaperProvider = 'mknews';
  StorageManager.savePaperProvider('mknews');
}
let currentPressDept = 'all';
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
        ${p.badge} ${p.name}
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

// Realtime Feed Refresh Function
async function refreshFeed() {
  const feedContainer = document.getElementById('feedContainer');
  showToast('🔄 실시간 이슈 수집 및 새로고침 중...');
  if (feedContainer) feedContainer.style.opacity = '0.5';
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
    if (feedContainer) feedContainer.style.opacity = '1';
    showToast('✅ 실시간 피드 새로고침 완료!');
  }
}

// 100% Original Realtime Feed Fetcher
async function fetchKeywordIssues(keywordsList) {
  showToast(`🔄 [${keywordsList.join(', ')}] 소식 수집 중...`);
  try {
    const issues = await IssueApi.fetchKeywordIssues(keywordsList);
    currentIssues = issues || [];
  } catch (e) {
    console.warn('Realtime feed fetch error:', e);
    currentIssues = [];
  } finally {
    renderIssues();
  }
}

async function fetchTabIssues(tabName) {
  showToast(`🔄 [${tabName}] 수집 중...`);
  try {
    const issues = await IssueApi.fetchTabIssues(tabName);
    tabFeeds[tabName] = issues || [];
    currentIssues = tabFeeds[tabName];
  } catch (e) {
    console.warn(`Tab [${tabName}] fetch error:`, e);
    tabFeeds[tabName] = [];
    currentIssues = [];
  } finally {
    renderIssues();
  }
}

async function switchNavTab(tab, btn) {
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
      await fetchKeywordIssues([currentKeyword]);
    } else {
      if (keywordChips) keywordChips.style.display = 'none';
      if (tab === 'bookmark') {
        renderIssues();
      } else {
        if (tab === 'press') currentPressDept = 'all';
        await fetchTabIssues(tab);
      }
    }
  }
}

function getRecencyWeight(timeStr) {
  if (!timeStr) return 0;
  let s = String(timeStr).trim();

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

  match = s.match(/^(\d{1,2})[\.\/-](\d{1,2})\s+(\d{1,2}):(\d{1,2})/);
  if (match) {
    const now = new Date();
    const month = parseInt(match[1], 10) - 1;
    const day = parseInt(match[2], 10);
    const hour = parseInt(match[3], 10);
    const min = parseInt(match[4], 10);
    return new Date(now.getFullYear(), month, day, hour, min).getTime();
  }

  if (s.includes('분 전')) {
    const m = parseInt(s, 10);
    return Date.now() - (m * 60 * 1000);
  }
  if (s.includes('시간 전')) {
    const h = parseInt(s, 10);
    return Date.now() - (h * 60 * 60 * 1000);
  }
  if (s.includes('방금')) return Date.now();
  if (s.includes('어제')) return Date.now() - (24 * 60 * 60 * 1000);

  return 0;
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
          <p style="font-size:12px; color:#64748B;">이슈 카드의 <strong>[⭐ 스크랩]</strong> 버튼을 눌러 보관함에 담아보세요!</p>
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

    displayItems.sort((a, b) => getRecencyWeight(b.time) - getRecencyWeight(a.time));

    let html = `
      <div class="realtime-bar" onclick="refreshFeed()" style="cursor:pointer;" title="클릭 시 실시간 소식 새로고침">
        <div class="realtime-indicator">
          <div class="live-dot"></div>
          <span>접속 시점 기준 실시간 이슈 피드 (${displayItems.length}건)</span>
        </div>
        <span style="font-size: 11px; opacity: 0.8;" id="updateTimestamp">🔄 새로고침</span>
      </div>
    `;

    if (displayItems.length === 0) {
      html += `
        <div style="text-align:center; padding: 60px 20px; color: var(--text-sub);">
          <p style="font-size:36px; margin-bottom:12px;">📰</p>
          <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">'# ${currentKeyword}' 관련 수집 기사를 가져오는 중...</p>
          <p style="font-size:12px; color:#64748B;">위의 <strong>[🔄 새로고침]</strong> 버튼을 누르시거나 잠시만 기다려 주세요.</p>
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
    exclusive: '🎯 단독 뉴스',
    press: '📋 공식 보도자료'
  };

  let displayItems = currentIssues;
  if (currentNavTab === 'press') {
    renderPressDeptChips();
    if (currentPressDept !== 'all') {
      displayItems = currentIssues.filter(item => (item.publisher || '').includes(currentPressDept) || (item.badge || '').includes(currentPressDept));
    }
  }

  let html = `
    <div class="realtime-bar" onclick="switchNavTab('${currentNavTab}')" style="cursor:pointer;">
      <div class="realtime-indicator">
        <div class="live-dot"></div>
        <span>${tabTitles[currentNavTab] || '실시간 피드'} (${displayItems.length}건)</span>
      </div>
      <span style="font-size: 11px; opacity: 0.8;">🔄 새로고침</span>
    </div>
  `;

  if (displayItems.length === 0) {
    html += `
      <div style="text-align:center; padding: 60px 20px; color: var(--text-sub);">
        <p style="font-size:36px; margin-bottom:12px;">📰</p>
        <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">수집된 보도자료가 없습니다.</p>
        <p style="font-size:12px; color:#64748B;">선택하신 부처의 공식 발표 소식을 준비 중입니다.</p>
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

  let html = `
    <span class="chip ${currentPressDept === 'all' ? 'active' : ''}" onclick="selectPressDept('all')">
      전체 부처 (${currentIssues.length})
    </span>
  `;

  Object.keys(deptCounts).forEach(dept => {
    const count = deptCounts[dept];
    const isActive = (currentPressDept === dept);
    html += `
      <span class="chip ${isActive ? 'active' : ''}" onclick="selectPressDept('${dept}')">
        🏛️ ${dept} (${count})
      </span>
    `;
  });

  chipContainer.innerHTML = html;
}

function selectPressDept(dept) {
  currentPressDept = dept;
  renderIssues();
}

function renderIssueCardHtml(item, isScrapped) {
  const hasPreSummary = item.summary && item.summary.length > 0;
  const summaryItems = hasPreSummary ? item.summary.map(s => `<li>${s}</li>`).join('') : '';
  const isNegBadge = item.is_negative ? `<span class="is-neg-tag" style="background:#FEF2F2; color:#EF4444; border:1px solid #FECACA; font-size:10px; font-weight:700; padding:2px 6px; border-radius:10px; margin-left:6px;">🚨 주요 이슈</span>` : '';

  const titleAttr = (item.title || '').replace(/"/g, '&quot;');
  const contentAttr = (item.content || item.title || '').replace(/"/g, '&quot;');
  const urlAttr = (item.url || '#').replace(/"/g, '&quot;');
  const publisherAttr = (item.publisher || '뉴스').replace(/"/g, '&quot;');
  const badgeAttr = (item.badge || '📰 이슈').replace(/"/g, '&quot;');
  const timeAttr = (item.time || '').replace(/"/g, '&quot;');

  return `
    <div class="issue-card" data-title="${titleAttr}" data-url="${urlAttr}" data-content="${contentAttr}" data-keyword="${item.keyword || '뉴스'}" data-publisher="${publisherAttr}" data-badge="${badgeAttr}" data-time="${timeAttr}">
      <div class="card-top">
        <span class="source-tag source-news">${item.badge || '📰 이슈'} ${isNegBadge}</span>
        <span class="card-date card-time">${formatRelativeTime(item.time)}</span>
      </div>
      <h3 class="card-title">${item.title}</h3>
      
      <button class="ai-summary-toggle-btn" onclick="toggleOnDemandAiSummary(this)">
        ✨ AI 핵심 요약 보기 ▾
      </button>

      <div class="ai-summary-box" style="display: none;" data-generated="${hasPreSummary ? 'true' : 'false'}">
        <div class="ai-summary-head">✨ FactChat AI 핵심 요약</div>
        <ul class="ai-summary-list">
          ${summaryItems}
        </ul>
      </div>

      <div class="card-footer">
        <div class="card-btns">
          <button class="card-action-btn ${isScrapped ? 'scrapped' : ''}" onclick="toggleScrap(this)">
            ${isScrapped ? '★ 스크랩됨' : '☆ 스크랩'}
          </button>
          <button class="card-action-btn" onclick="shareArticle(this)">🔗 공유</button>
        </div>
        <a href="${item.url || '#'}" target="_blank" rel="noopener noreferrer" class="link-btn">원문 보기 ↗</a>
      </div>
    </div>
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
    btn.innerHTML = '✨ AI 핵심 요약 접기 ▴';

    const isGenerated = box.getAttribute('data-generated') === 'true';
    if (!isGenerated) {
      const title = card.getAttribute('data-title') || '';
      const content = card.getAttribute('data-content') || title;
      const keyword = card.getAttribute('data-keyword') || '이슈';
      const apiKey = StorageManager.getFactChatKey();

      const listElem = box.querySelector('.ai-summary-list');
      if (listElem) {
        listElem.innerHTML = `<li style="color:#64748B;"><span class="spin-icon">🔄</span> FactChat AI 핵심 요약 분석 중...</li>`;
      }

      if (!apiKey) {
        if (listElem) {
          listElem.innerHTML = `
            <li style="color:#D97706; font-weight:700;">🔑 FactChat API 키 설정 필요</li>
            <li style="font-size:11px; color:#64748B;">우측 상단 ⚙️ 설정 버튼을 눌러 사내/개인 FactChat API 키를 등록하시면 실시간 AI 요약이 생성됩니다.</li>
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
    btn.innerHTML = '✨ AI 핵심 요약 보기 ▾';
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
    btn.innerHTML = '★ 스크랩됨';
    showToast('⭐ 보관함에 추가되었습니다.');
  } else {
    btn.classList.remove('scrapped');
    btn.innerHTML = '☆ 스크랩';
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
  const title = card.getAttribute('data-title');
  const url = card.getAttribute('data-url');

  if (navigator.share) {
    navigator.share({ title: title, url: url }).catch(() => {});
  } else if (navigator.clipboard) {
    navigator.clipboard.writeText(`${title}\n${url}`);
    showToast('📋 기사 링크가 클립보드에 복사되었습니다!');
  } else {
    showToast('🔗 ' + url);
  }
}

// --- Paper View logic ---
async function loadPaperForCurrentDate(forceRefresh = false) {
  const cacheKey = `${currentPaperProvider}_${currentPaperDate}`;

  const picker = document.getElementById('etnewsDatePicker');
  if (picker) picker.value = currentPaperDate;

  // 1. Instant rendering from Memory / Session Cache (0ms delay, no loading spinner)
  if (!forceRefresh) {
    let cachedData = paperFeedsCache[cacheKey];
    if (!cachedData) {
      try {
        const stored = sessionStorage.getItem(`paper_cache_${cacheKey}`);
        if (stored) cachedData = JSON.parse(stored);
      } catch (e) {}
    }

    if (cachedData && cachedData.articles && cachedData.articles.length > 0) {
      paperData = cachedData;
      paperFeedsCache[cacheKey] = cachedData;
      currentPaperSection = 'all';
      renderPaperSections();
      renderPaperView();
      return;
    }
  }

  // 2. Only show loading spinner if NO cached data exists
  const container = document.getElementById('feedContainer');
  if (container) {
    container.innerHTML = `
      <div style="text-align:center; padding: 60px 20px; color:#64748B;">
        <span class="spin-icon" style="font-size:24px; display:inline-block; margin-bottom:8px;">🔄</span>
        <p style="font-weight:700;">지면 신문 데이터 수집 중...</p>
      </div>
    `;
  }

  try {
    paperData = await IssueApi.fetchPaperNews(currentPaperProvider, currentPaperDate);
    if (paperData && paperData.articles && paperData.articles.length > 0) {
      paperFeedsCache[cacheKey] = paperData;
      try {
        sessionStorage.setItem(`paper_cache_${cacheKey}`, JSON.stringify(paperData));
      } catch (e) {}
    }
    currentPaperSection = 'all';
    renderPaperSections();
    renderPaperView();
  } catch (err) {
    console.warn('Paper fetch error:', err);
    if (container) {
      container.innerHTML = `<div style="text-align:center; padding: 40px 20px; color:#EF4444;">지면 데이터를 불러오는 중 오류가 발생했습니다.</div>`;
    }
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
  renderPaperSections();
  renderPaperView();
}

function onPaperDateChange(val) {
  if (val) {
    currentPaperDate = val;
    loadPaperForCurrentDate();
  }
}

function setPaperToday() {
  currentPaperDate = getTodayKstStr();
  const picker = document.getElementById('etnewsDatePicker');
  if (picker) picker.value = currentPaperDate;
  loadPaperForCurrentDate();
}

function renderPaperView() {
  const container = document.getElementById('feedContainer');
  if (!container) return;

  const providerObj = PAPER_PROVIDERS.find(p => p.id === currentPaperProvider) || PAPER_PROVIDERS[0];

  if (!paperData || !paperData.articles || paperData.articles.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding: 60px 20px; color: var(--text-sub);">
        <p style="font-size:36px; margin-bottom:12px;">📰</p>
        <p style="font-size:15px; font-weight:700; color:var(--text-main); margin-bottom:6px;">${providerObj.name} 지면 기사 수집 중</p>
        <p style="font-size:12px; color:#64748B;">선택하신 날짜(${currentPaperDate})의 지면 기사를 준비하고 있습니다.</p>
      </div>
    `;
    return;
  }

  let articlesToRender = paperData.articles;
  if (currentPaperSection !== 'all' && paperData.categorized[currentPaperSection]) {
    articlesToRender = paperData.categorized[currentPaperSection];
  }

  let html = `
    <div class="realtime-bar" style="background:#F1F5F9; border-color:#CBD5E1; color:#334155; cursor:pointer;" onclick="loadPaperForCurrentDate(true)" title="클릭 시 지면 신문 새로고침">
      <div class="realtime-indicator">
        <span>${providerObj.badge} ${providerObj.name} 지면 (${articlesToRender.length}건)</span>
      </div>
      <span style="font-size: 11px; opacity: 0.8;">🔄 ${currentPaperDate} (새로고침)</span>
    </div>
  `;

  articlesToRender.forEach(item => {
    const isScrapped = StorageManager.isScrapped(item.title);
    html += renderIssueCardHtml(item, isScrapped);
  });

  container.innerHTML = html;

  try {
    const savedScroll = sessionStorage.getItem('paper_scroll_y');
    if (savedScroll) {
      setTimeout(() => { window.scrollTo(0, parseInt(savedScroll, 10)); }, 20);
    }
  } catch (e) {}
}

window.addEventListener('scroll', () => {
  if (currentNavTab === 'paper') {
    try { sessionStorage.setItem('paper_scroll_y', window.scrollY); } catch (e) {}
  }
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
        badge.textContent = '✅ Key 등록됨';
      } else {
        badge.className = 'api-key-badge warning';
        badge.textContent = '⚠️ 키 입력 필요';
      }
    }
  }
}

function saveFactchatKey() {
  const input = document.getElementById('factchatApiKeyInput');
  if (!input) return;
  const val = input.value.trim();
  StorageManager.saveFactChatKey(val);
  showToast(val ? '✅ FactChat API 키가 저장되었습니다!' : 'API 키가 삭제되었습니다.');
  toggleSettingsModal();
}

function togglePasswordVisibility() {
  const input = document.getElementById('factchatApiKeyInput');
  if (!input) return;
  input.type = (input.type === 'password') ? 'text' : 'password';
}

function showToast(msg) {
  let toast = document.getElementById('appToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'appToast';
    toast.style.cssText = `
      position: fixed; bottom: 70px; left: 50%; transform: translateX(-50%);
      background: rgba(15, 23, 42, 0.92); color: #FFF; padding: 10px 18px;
      border-radius: 20px; font-size: 12px; font-weight: 700; z-index: 9999;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15); transition: opacity 0.3s ease; opacity: 0; pointer-events: none;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  setTimeout(() => { toast.style.opacity = '0'; }, 2200);
}

// Initializer
document.addEventListener('DOMContentLoaded', () => {
  const userKws = StorageManager.getKeywords();
  currentKeyword = userKws.length ? userKws[0] : '용인시';
  renderKeywordChips();
  updateHeaderScrapBadge();

  const savedTab = StorageManager.getActiveNavTab();
  if (savedTab && savedTab !== 'feed') {
    const navBtn = document.querySelector(`.app-bottom-nav .nav-item[data-tab="${savedTab}"]`);
    switchNavTab(savedTab, navBtn);
  } else {
    fetchKeywordIssues([currentKeyword]);
  }
});
