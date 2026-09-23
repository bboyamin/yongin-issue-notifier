/**
 * IssueApi Deep Module
 * Interface for backend endpoint collection and FactChat Gateway AI OnDemandSummary.
 */
const IssueApi = (() => {
  const FACTCHAT_ENDPOINT = 'https://factchat-cloud.mindlogic.ai/v1/gateway/chat/completions';

  return {
    /**
     * Collect issues dynamically for the provided keywords (Realtime feed 100% original)
     * @param {string[]} keywordsList 
     * @returns {Promise<Array>}
     */
    async fetchKeywordIssues(keywordsList = ['용인시']) {
      try {
        const kwParam = encodeURIComponent(keywordsList.join(','));
        const res = await fetch(`/api/collect?keywords=${kwParam}&force=true&v=78&t=${Date.now()}`);
        if (res.ok) {
          const liveData = await res.json();
          if (Array.isArray(liveData) && liveData.length > 0) {
            return liveData;
          }
        }
      } catch (err) {
        console.warn('Live API collect error for keywords, loading default dataset:', err);
      }
      return await this.loadDefaultIssues('realtime');
    },

    /**
     * Collect issues dynamically for the specified tab ('exclusive', 'ranking', 'press')
     * @param {string} tabName 
     * @returns {Promise<Array>}
     */
    async fetchTabIssues(tabName = 'realtime') {
      try {
        const res = await fetch(`/api/collect?tab=${tabName}&force=true&v=78&t=${Date.now()}`);
        if (res.ok) {
          const liveData = await res.json();
          if (Array.isArray(liveData) && liveData.length > 0) {
            return liveData;
          }
        }
      } catch (err) {
        console.warn(`Live API collect error for tab [${tabName}]:`, err);
      }
      return await this.loadDefaultIssues(tabName);
    },

    async loadDefaultIssues(tabName = 'realtime') {
      const timestamp = Date.now();
      const paths = [
        `./data/issues_${tabName}.json?v=78&t=${timestamp}`,
        `data/issues_${tabName}.json?v=78&t=${timestamp}`,
        `./data/issues.json?v=78&t=${timestamp}`
      ];
      for (const p of paths) {
        try {
          const res = await fetch(p);
          if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data) && data.length > 0) {
              return data;
            }
          }
        } catch (err) {
          console.warn(`Fetch error for ${p}:`, err);
        }
      }
      return [];
    },

    /**
     * Fetch paper news for 5 newspapers (etnews, mknews, chosun, joongang, donga)
     * @param {string} provider 
     * @param {string} dateStr 
     */
    async fetchPaperNews(provider = 'etnews', dateStr = '') {
      try {
        const url = `/api/papernews?provider=${encodeURIComponent(provider)}&date=${encodeURIComponent(dateStr)}&v=108&t=${Date.now()}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && data.articles && data.articles.length > 0) {
            return data;
          }
        }
      } catch (err) {
        console.warn(`Fetch paper news API error for ${provider}:`, err);
      }

      // Client-side Direct RSS Fallback (Zero-failure mechanism for browser)
      try {
        const domainMap = {
          chosun: { domain: 'chosun.com', name: '조선일보', badge: '🗞️ 조선일보' },
          joongang: { domain: 'joongang.co.kr', name: '중앙일보', badge: '🏢 중앙일보' },
          donga: { domain: 'donga.com', name: '동아일보', badge: '📰 동아일보' }
        };
        const info = domainMap[provider];
        if (info) {
          const gUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(`https://news.google.com/rss/search?q=site:${info.domain}&hl=ko&gl=KR&ceid=KR:ko`)}`;
          const gRes = await fetch(gUrl);
          if (gRes.ok) {
            const xmlText = await gRes.text();
            const parser = new DOMParser();
            const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
            const items = Array.from(xmlDoc.querySelectorAll('item'));
            const articles = [];
            const categorized = {};
            const curDate = new Date().toISOString().split('T')[0].replace(/-/g, '/');

            items.forEach((item, idx) => {
              let title = item.querySelector('title')?.textContent || '';
              if (title.includes(' - ')) title = title.split(' - ')[0].trim();
              if (!title || title.length < 5) return;

              const link = item.querySelector('link')?.textContent || '#';

              let section = '주요뉴스';
              if (/정치|대통령|국회|정당|여당|야당/.test(title)) section = '정치면';
              else if (/경제|금융|증시|주식|금리|부동산|기업/.test(title)) section = '경제면';
              else if (/사회|검찰|경찰|사건|사고/.test(title)) section = '사회면';
              else if (/IT|AI|과학|반도체|기술/.test(title)) section = 'IT·과학면';

              const art = {
                id: `${provider}_client_${idx}`,
                keyword: info.name,
                type: 'news',
                badge: `${info.badge} · ${section}`,
                publisher: info.name,
                title: title,
                time: curDate,
                url: link,
                content: title,
                section: section
              };
              articles.push(art);
              if (!categorized[section]) categorized[section] = [];
              categorized[section].push(art);
            });

            if (articles.length > 0) {
              return { sections: Object.keys(categorized), categorized, articles };
            }
          }
        }
      } catch (err) {
        console.warn('Client-side RSS fallback error:', err);
      }

      return { sections: [], categorized: {}, articles: [] };
    },

    /**
     * Generate On-Demand 3-line AI summary via FactChat Gateway
     */
    async generateSummary({ title, keyword = '이슈', content = '', apiKey }) {
      if (!apiKey) {
        throw new Error('FactChat API Key is missing');
      }

      const prompt = `아래 이슈 기사/보도자료를 읽고 핵심 내용과 주요 팩트(2~4개 포인트)를 명확히 정리하고 부정/위험 여부를 판단해 JSON으로 응답해 주세요.
[제목]: ${title}
[키워드]: ${keyword}
[내용]: ${(content || title).slice(0, 1500)}
JSON 응답 형식: {"summary": ["핵심 포인트1", "핵심 포인트2", "핵심 포인트3"], "is_negative": true 또는 false}`;

      const res = await fetch(FACTCHAT_ENDPOINT, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: 'gpt-5.5',
          messages: [{ role: 'user', content: prompt }],
          temperature: 0.3
        })
      });

      if (!res.ok) {
        throw new Error(`FactChat API returned HTTP ${res.status}`);
      }

      const data = await res.json();
      const aiText = data.choices[0].message.content.trim();
      let summary = [];
      let is_negative = false;

      if (aiText.includes('{') && aiText.includes('}')) {
        const jsonStr = aiText.substring(aiText.indexOf('{'), aiText.lastIndexOf('}') + 1);
        const parsed = JSON.parse(jsonStr);
        summary = parsed.summary || [];
        is_negative = parsed.is_negative || false;
      } else {
        summary = aiText.split('\n').map(l => l.replace(/^[-\s\d.]*/, '').trim()).filter(l => l).slice(0, 3);
      }

      return { summary, is_negative };
    }
  };
})();
