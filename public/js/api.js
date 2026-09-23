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
     * Fetch paper news for 3 news providers (etnews, mknews, jtbc)
     * @param {string} provider 
     * @param {string} dateStr 
     */
    async fetchPaperNews(provider = 'etnews', dateStr = '') {
      const cleanProvider = String(provider || 'etnews').toLowerCase().trim();
      const endpoints = [
        `/api/${cleanProvider}?date=${encodeURIComponent(dateStr)}&t=${Date.now()}`,
        `/api/papernews?provider=${encodeURIComponent(cleanProvider)}&date=${encodeURIComponent(dateStr)}&t=${Date.now()}`
      ];

      for (const url of endpoints) {
        try {
          const res = await fetch(url);
          if (res.ok) {
            const data = await res.json();
            if (data && (data.articles || data.sections) && Array.isArray(data.articles) && data.articles.length > 0) {
              return data;
            }
          }
        } catch (err) {
          console.warn(`Fetch paper news error for ${url}:`, err);
        }
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
