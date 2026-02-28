// ── Jike API ──────────────────────────────────────────────────────────────────

const JIKE_API = 'https://api.ruguoapp.com';
const JIKE_HEADERS = {
  Origin: 'https://web.okjike.com',
  'User-Agent':
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
  Accept: 'application/json, text/plain, */*',
  DNT: '1',
  'Content-Type': 'application/json',
};

function jikeHeaders(at) {
  return { ...JIKE_HEADERS, 'x-jike-access-token': at };
}

async function jikeFetch(method, path, at, body) {
  const resp = await fetch(`${JIKE_API}${path}`, {
    method,
    headers: jikeHeaders(at),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401) throw new Error('TOKEN_EXPIRED');
  if (!resp.ok) throw new Error(`Jike ${resp.status}: ${path}`);
  return resp.json();
}

async function searchKeyword(keyword, at, pages = 2) {
  const posts = [];
  let loadMoreKey = null;
  for (let i = 0; i < pages; i++) {
    const body = { keyword, limit: 20 };
    if (loadMoreKey) body.loadMoreKey = loadMoreKey;
    try {
      const data = await jikeFetch('POST', '/1.0/search/integrate', at, body);
      posts.push(...(data.data || []));
      loadMoreKey = data.loadMoreKey;
      if (!loadMoreKey) break;
    } catch {
      break;
    }
  }
  return posts;
}

function extractUsersFromPosts(posts) {
  const seen = new Set();
  const users = [];
  for (const post of posts) {
    const u = post.user;
    if (!u) continue;
    const id = u.username || u.id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    users.push({ id, screenName: u.screenName || '' });
  }
  return users;
}

async function fetchProfile(username, at) {
  try {
    const data = await jikeFetch('GET', `/1.0/users/profile?username=${encodeURIComponent(username)}`, at);
    const u = data.user || data;
    return {
      username,
      screenName: u.screenName || '',
      bio: u.bio || '',
      profileUrl: `https://okjike.com/u/${username}`,
      followersCount: u.followersCount || 0,
    };
  } catch {
    return null;
  }
}

async function fetchPosts(username, at, limit = 50) {
  const posts = [];
  let loadMoreKey = null;
  while (posts.length < limit) {
    const body = { username };
    if (loadMoreKey) body.loadMoreKey = loadMoreKey;
    try {
      const data = await jikeFetch('POST', '/1.0/personalUpdate/single', at, body);
      const page = data.data || [];
      posts.push(...page);
      loadMoreKey = data.loadMoreKey;
      if (!loadMoreKey || page.length === 0) break;
    } catch {
      break;
    }
  }
  return posts.slice(0, limit);
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function extractContact(bio) {
  const c = [];
  const wechat = bio.match(/微信[：:]\s*(\S+)/);
  if (wechat) c.push(`微信: ${wechat[1]}`);
  const twitter = bio.match(/(?:twitter|x\.com)[：:\s@]*([A-Za-z0-9_]+)/i);
  if (twitter) c.push(`Twitter: @${twitter[1]}`);
  const email = bio.match(/[\w.+-]+@[\w-]+\.[a-z]{2,}/);
  if (email) c.push(`Email: ${email[0]}`);
  const github = bio.match(/github\.com\/([A-Za-z0-9_-]+)/i);
  if (github) c.push(`GitHub: github.com/${github[1]}`);
  return c.join(' | ');
}

function extractAge(bio) {
  const m = bio.match(/(\d{2})\s*(?:岁|y\/o\b|yo\b)/);
  if (m) {
    const a = parseInt(m[1]);
    if (a >= 14 && a <= 40) return `${a}岁`;
  }
  return '';
}

function postsToText(posts) {
  return posts
    .map((p, i) => {
      const date = (p.createdAt || '').slice(0, 10);
      const topic = p.topic?.content ? `[${p.topic.content}] ` : '';
      const content = p.content || '';
      const repost = p.target
        ? `\n  > 转发自@${p.target.user?.screenName || '?'}：${(p.target.content || '').slice(0, 100)}`
        : '';
      return `${i + 1}. ${date} ${topic}${content}${repost}`;
    })
    .join('\n\n');
}

function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Claude ────────────────────────────────────────────────────────────────────

async function claudeChat(ak, prompt, stream = false) {
  return fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': ak,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-opus-4-6',
      max_tokens: 4096,
      stream,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
}

// ── Handlers ──────────────────────────────────────────────────────────────────

async function handleSearch(request) {
  const { keywords, criteria, pages = 2, access_token: at, anthropic_key: ak } = await request.json();
  if (!at || !ak) return jsonErr('缺少 Access Token 或 Anthropic Key');

  const kwList = keywords.split(',').map((k) => k.trim()).filter(Boolean);
  const allUsers = new Map();

  for (const kw of kwList) {
    const posts = await searchKeyword(kw, at, pages);
    for (const u of extractUsersFromPosts(posts)) {
      if (!allUsers.has(u.id)) allUsers.set(u.id, { ...u, foundVia: [kw] });
      else allUsers.get(u.id).foundVia.push(kw);
    }
    await delay(300);
  }

  // Fetch profiles in batches of 6
  const userList = [...allUsers.values()];
  const profiles = [];
  const BATCH = 6;
  for (let i = 0; i < userList.length; i += BATCH) {
    const batch = userList.slice(i, i + BATCH);
    const results = await Promise.all(batch.map((u) => fetchProfile(u.id, at)));
    for (let j = 0; j < results.length; j++) {
      if (results[j]) {
        profiles.push({
          ...results[j],
          foundVia: batch[j].foundVia,
          contact: extractContact(results[j].bio),
          age: extractAge(results[j].bio),
        });
      }
    }
    await delay(200);
  }

  // Claude scoring
  const summary = profiles
    .map(
      (p, i) =>
        `${i + 1}. ${p.screenName} (@${p.username})\nBio: ${p.bio.slice(0, 160)}\n粉丝: ${p.followersCount} | 关键词: ${p.foundVia.join(', ')}`
    )
    .join('\n\n');

  const resp = await claudeChat(
    ak,
    `以下是从即刻平台搜索到的用户列表，请根据筛选条件，从中选出最符合条件的用户，为每人写一句推荐理由（中文，20字以内）。

筛选条件：
${criteria || '技术型创业者：有技术深度（技术栈/开源/竞赛），有产品执行力（已发布产品/用户数据），顶校或大厂背景'}

用户列表：
${summary}

请输出 JSON 数组，只包含符合条件的用户，格式：
[{"index": 1, "reason": "推荐理由"}, ...]
只输出 JSON，不要任何其他文字。`
  );

  const claudeData = await resp.json();
  let scored = [];
  try {
    const text = claudeData.content[0].text.trim();
    const start = text.indexOf('[');
    const end = text.lastIndexOf(']') + 1;
    const parsed = JSON.parse(text.slice(start, end));
    scored = parsed
      .map(({ index, reason }) => ({ ...profiles[index - 1], reason }))
      .filter(Boolean);
  } catch {
    scored = profiles.slice(0, 20).map((p) => ({ ...p, reason: '符合搜索关键词' }));
  }

  return jsonOk({ users: scored });
}

async function handleAnalyze(request) {
  const { input, question, limit = 50, access_token: at, anthropic_key: ak } = await request.json();
  if (!at || !ak) return jsonErr('缺少 Access Token 或 Anthropic Key');

  let username = input.trim();
  const urlMatch = username.match(/\/u\/([^/?#\s]+)/);
  if (urlMatch) username = urlMatch[1];

  const [profile, posts] = await Promise.all([
    fetchProfile(username, at),
    fetchPosts(username, at, limit),
  ]);

  if (!profile) return jsonErr('用户不存在或无法访问', 404);

  const postsText = postsToText(posts);
  const prompt = `以下是即刻用户「${profile.screenName}」（@${profile.username}）的资料和帖子内容。

**个人简介**：${profile.bio}
**粉丝数**：${profile.followersCount}
**帖子（共 ${posts.length} 条，时间倒序）**：

${postsText}

---

${
  question
    ? question
    : `请从以下维度进行深度分析，每个维度给出具体帖子内容作为佐证：

1. **核心兴趣领域** — 高频话题和圈子分布
2. **内容风格** — 写作特点、表达方式、信息密度
3. **技术/产品深度** — 技术栈偏好、产品视角、思考深度
4. **代表性观点** — 3-5句最有代表性的金句或洞察
5. **整体画像** — 用一段话概括这个人是谁、在做什么、核心驱动力是什么`
}

请用中文输出，结构清晰，使用 Markdown 格式（标题用 ##，重点用 **加粗**）。`;

  const claudeResp = await claudeChat(ak, prompt, true);

  // SSE streaming response
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const enc = new TextEncoder();

  const sse = (obj) => writer.write(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));

  // Send user info first
  await sse({
    type: 'user_info',
    profile: {
      screenName: profile.screenName,
      username: profile.username,
      bio: profile.bio,
      profileUrl: profile.profileUrl,
      followersCount: profile.followersCount,
      postCount: posts.length,
    },
  });

  // Pipe Claude stream
  (async () => {
    const reader = claudeResp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          if (raw === '[DONE]') continue;
          try {
            const evt = JSON.parse(raw);
            if (evt.type === 'content_block_delta' && evt.delta?.text) {
              await sse({ type: 'text', text: evt.delta.text });
            }
          } catch {}
        }
      }
      await sse({ type: 'done' });
    } finally {
      writer.close();
    }
  })();

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function jsonOk(data) {
  return new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
  });
}

function jsonErr(msg, status = 400) {
  return new Response(JSON.stringify({ error: msg }), {
    status,
    headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
  });
}

// ── HTML ──────────────────────────────────────────────────────────────────────

const HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>即刻人才雷达</title>
<script src="https://cdn.tailwindcss.com"><\/script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"><\/script>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.spinner{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.prose h2{font-size:1.1rem;font-weight:700;margin:1.2rem 0 .5rem;color:#111}
.prose h3{font-size:1rem;font-weight:600;margin:1rem 0 .4rem;color:#333}
.prose p{margin:.5rem 0;line-height:1.7}
.prose strong{font-weight:600;color:#111}
.prose ul,.prose ol{padding-left:1.4rem;margin:.5rem 0}
.prose li{margin:.25rem 0;line-height:1.6}
.prose blockquote{border-left:3px solid #FFD000;padding:.3rem .8rem;margin:.5rem 0;background:#fffde7;color:#555;border-radius:0 4px 4px 0}
.tag{display:inline-block;background:#fef9c3;color:#854d0e;padding:1px 8px;border-radius:99px;font-size:.7rem;font-weight:500}
tr:hover td{background:#fafafa}
</style>
</head>
<body class="bg-gray-100 min-h-screen">

<!-- Header -->
<header class="bg-black sticky top-0 z-50 shadow-lg">
  <div class="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
    <div class="flex items-center gap-2.5">
      <div class="w-7 h-7 bg-yellow-400 rounded-full flex items-center justify-center">
        <span class="text-black text-xs font-black">J</span>
      </div>
      <span class="text-white font-bold tracking-tight">即刻人才雷达</span>
    </div>
    <button id="cfg-btn" class="text-gray-400 hover:text-yellow-400 text-sm transition-colors flex items-center gap-1.5">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
      设置
    </button>
  </div>
</header>

<!-- Settings -->
<div id="cfg" class="hidden bg-gray-900 border-b border-gray-800">
  <div class="max-w-6xl mx-auto px-4 py-5 grid grid-cols-1 md:grid-cols-3 gap-4">
    <div>
      <label class="text-xs text-gray-400 block mb-1.5">Jike Access Token</label>
      <input id="inp-at" type="password" placeholder="eyJ..." class="w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-yellow-400">
    </div>
    <div>
      <label class="text-xs text-gray-400 block mb-1.5">Jike Refresh Token</label>
      <input id="inp-rt" type="password" placeholder="eyJ..." class="w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-yellow-400">
    </div>
    <div>
      <label class="text-xs text-gray-400 block mb-1.5">Anthropic API Key</label>
      <input id="inp-ak" type="password" placeholder="sk-ant-..." class="w-full bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-yellow-400">
    </div>
  </div>
  <div class="max-w-6xl mx-auto px-4 pb-4 flex items-center gap-3">
    <button id="cfg-save-btn" class="bg-yellow-400 hover:bg-yellow-300 text-black text-sm font-semibold px-5 py-1.5 rounded-lg transition-colors">保存到本地</button>
    <span id="cfg-saved" class="text-green-400 text-sm hidden">✓ 已保存</span>
    <span class="text-gray-600 text-xs">Token 仅存储在浏览器 localStorage，不上传服务器</span>
  </div>
</div>

<!-- Main -->
<main class="max-w-6xl mx-auto px-4 py-6">
  <!-- Tabs -->
  <div class="flex gap-2 mb-6">
    <button id="tab-s" class="px-5 py-2 rounded-full text-sm font-semibold bg-black text-white transition-all">🔍 人才搜索</button>
    <button id="tab-a" class="px-5 py-2 rounded-full text-sm font-semibold bg-white text-gray-500 hover:bg-gray-50 transition-all">📊 用户分析</button>
  </div>

  <!-- ── Search Panel ── -->
  <div id="panel-s">
    <div class="bg-white rounded-2xl p-6 shadow-sm mb-5">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div class="md:col-span-2">
          <label class="text-sm font-semibold text-gray-700 block mb-1.5">搜索关键词</label>
          <input id="s-keywords" value="独立开发, 开源, hackathon, 冷启动" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400 transition-colors" placeholder="独立开发, 开源, hackathon, 冷启动">
          <p class="text-xs text-gray-400 mt-1">多个关键词用逗号分隔，每个关键词独立搜索后合并去重</p>
        </div>
        <div>
          <label class="text-sm font-semibold text-gray-700 block mb-1.5">每词搜索页数</label>
          <select id="s-pages" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400">
            <option value="1">1页 ≈ 20条</option>
            <option value="2" selected>2页 ≈ 40条</option>
            <option value="3">3页 ≈ 60条</option>
          </select>
        </div>
      </div>
      <div class="mb-4">
        <label class="text-sm font-semibold text-gray-700 block mb-1.5">筛选条件 <span class="text-gray-400 font-normal text-xs">（Claude 根据此条件打分筛选）</span></label>
        <textarea id="s-criteria" rows="3" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400 resize-none transition-colors" placeholder="描述你想找的人...">技术型创业者：有技术深度（具体技术栈/开源项目/竞赛成绩），有产品执行力（已发布产品/真实用户数据/变现记录），顶校或大厂背景优先</textarea>
      </div>
      <button id="s-btn" class="bg-yellow-400 hover:bg-yellow-300 text-black font-semibold px-8 py-2.5 rounded-xl text-sm transition-colors flex items-center gap-2">
        <span>开始搜索</span>
      </button>
    </div>

    <!-- Status -->
    <div id="s-status" class="hidden text-center py-10">
      <div class="spinner inline-block w-8 h-8 border-[3px] border-gray-200 border-t-yellow-400 rounded-full mb-3"></div>
      <p id="s-status-txt" class="text-gray-500 text-sm">正在搜索，预计需要 20-40 秒...</p>
    </div>

    <!-- Results -->
    <div id="s-results" class="hidden">
      <div class="flex items-center justify-between mb-3">
        <p id="s-count" class="text-sm text-gray-500"></p>
        <button id="export-btn" class="text-sm text-blue-600 hover:underline flex items-center gap-1">↓ 导出 CSV</button>
      </div>
      <div class="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 border-b border-gray-100">
              <tr>
                <th class="text-left px-4 py-3 font-semibold text-gray-600 whitespace-nowrap">用户</th>
                <th class="text-left px-4 py-3 font-semibold text-gray-600">Bio</th>
                <th class="text-left px-4 py-3 font-semibold text-gray-600">推荐理由</th>
                <th class="text-left px-4 py-3 font-semibold text-gray-600 whitespace-nowrap">联系方式</th>
                <th class="text-center px-4 py-3 font-semibold text-gray-600">年龄</th>
                <th class="text-left px-4 py-3 font-semibold text-gray-600 whitespace-nowrap">来源词</th>
              </tr>
            </thead>
            <tbody id="s-tbody" class="divide-y divide-gray-50"></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Analyze Panel ── -->
  <div id="panel-a" class="hidden">
    <div class="bg-white rounded-2xl p-6 shadow-sm mb-5">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div class="md:col-span-2">
          <label class="text-sm font-semibold text-gray-700 block mb-1.5">用户链接或用户名</label>
          <input id="a-input" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400 transition-colors" placeholder="https://okjike.com/u/xxx 或直接输入用户名">
        </div>
        <div>
          <label class="text-sm font-semibold text-gray-700 block mb-1.5">抓取帖子数量</label>
          <select id="a-limit" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400">
            <option value="25">最近 25 条（快）</option>
            <option value="50" selected>最近 50 条（推荐）</option>
            <option value="100">最近 100 条（慢）</option>
          </select>
        </div>
      </div>
      <div class="mb-4">
        <label class="text-sm font-semibold text-gray-700 block mb-1.5">分析维度 <span class="text-gray-400 font-normal text-xs">（留空则全维度分析）</span></label>
        <textarea id="a-question" rows="2" class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-yellow-400 resize-none transition-colors" placeholder="例：分析他的技术栈偏好和产品方向；或：找出他最有洞察力的3个观点并分析..."></textarea>
      </div>
      <button id="a-btn" class="bg-yellow-400 hover:bg-yellow-300 text-black font-semibold px-8 py-2.5 rounded-xl text-sm transition-colors">
        开始分析
      </button>
    </div>

    <!-- User Card + Analysis -->
    <div id="a-results" class="hidden">
      <div id="a-card" class="bg-white rounded-2xl p-5 shadow-sm mb-4 border-l-4 border-yellow-400">
        <div class="flex items-start justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span id="a-name" class="font-bold text-lg text-gray-900"></span>
              <a id="a-link" href="#" target="_blank" class="text-xs text-blue-500 hover:underline">查看主页 →</a>
            </div>
            <p id="a-bio" class="text-sm text-gray-600 mt-1 leading-relaxed"></p>
            <div class="flex gap-4 mt-2.5 text-xs text-gray-400">
              <span id="a-followers"></span>
              <span id="a-posts-count"></span>
            </div>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-2xl p-6 shadow-sm">
        <div id="a-loading" class="flex items-center gap-2 text-gray-400 text-sm mb-4">
          <div class="spinner w-4 h-4 border-2 border-gray-200 border-t-yellow-400 rounded-full"></div>
          <span>正在分析中...</span>
        </div>
        <div id="a-text" class="prose text-gray-800 text-sm leading-relaxed"></div>
      </div>
    </div>
  </div>
</main>

<script>
// ── State ──
let searchData = [];

// ── Settings ──
function toggleCfg() {
  document.getElementById('cfg').classList.toggle('hidden');
}
function saveCfg() {
  localStorage.setItem('jike_at', document.getElementById('inp-at').value);
  localStorage.setItem('jike_rt', document.getElementById('inp-rt').value);
  localStorage.setItem('jike_ak', document.getElementById('inp-ak').value);
  const el = document.getElementById('cfg-saved');
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 2000);
}
function loadCfg() {
  document.getElementById('inp-at').value = localStorage.getItem('jike_at') || '';
  document.getElementById('inp-rt').value = localStorage.getItem('jike_rt') || '';
  document.getElementById('inp-ak').value = localStorage.getItem('jike_ak') || '';
}
function tokens() {
  return {
    access_token: localStorage.getItem('jike_at') || document.getElementById('inp-at').value,
    anthropic_key: localStorage.getItem('jike_ak') || document.getElementById('inp-ak').value,
  };
}
function checkTokens() {
  const t = tokens();
  if (!t.access_token || !t.anthropic_key) {
    document.getElementById('cfg').classList.remove('hidden');
    alert('请先在设置中填写 Jike Access Token 和 Anthropic API Key');
    return false;
  }
  return true;
}

// ── Tabs ──
function tab(id) {
  ['s','a'].forEach(t => {
    document.getElementById('panel-' + t).classList.toggle('hidden', t !== id);
    const btn = document.getElementById('tab-' + t);
    btn.className = t === id
      ? 'px-5 py-2 rounded-full text-sm font-semibold bg-black text-white transition-all'
      : 'px-5 py-2 rounded-full text-sm font-semibold bg-white text-gray-500 hover:bg-gray-50 transition-all';
  });
}

// ── Search ──
async function doSearch() {
  if (!checkTokens()) return;
  const btn = document.getElementById('s-btn');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner w-4 h-4 border-2 border-black/30 border-t-black rounded-full"></div><span>搜索中...</span>';

  document.getElementById('s-status').classList.remove('hidden');
  document.getElementById('s-results').classList.add('hidden');

  try {
    const resp = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        keywords: document.getElementById('s-keywords').value,
        criteria: document.getElementById('s-criteria').value,
        pages: parseInt(document.getElementById('s-pages').value),
        ...tokens(),
      }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    searchData = data.users || [];
    renderTable(searchData);
  } catch (e) {
    alert('搜索失败：' + e.message);
  } finally {
    document.getElementById('s-status').classList.add('hidden');
    btn.disabled = false;
    btn.innerHTML = '<span>开始搜索</span>';
  }
}

function renderTable(users) {
  document.getElementById('s-count').textContent = '筛选出 ' + users.length + ' 位符合条件的用户';
  document.getElementById('s-tbody').innerHTML = users.map(u => \`
    <tr>
      <td class="px-4 py-3 whitespace-nowrap">
        <a href="\${u.profileUrl}" target="_blank" class="font-semibold text-blue-600 hover:underline block">\${esc(u.screenName)}</a>
        <span class="text-xs text-gray-400">@\${esc(u.username)}</span>
      </td>
      <td class="px-4 py-3 text-gray-600 max-w-xs">
        <p class="text-xs leading-relaxed line-clamp-3">\${esc(u.bio.slice(0,120))}</p>
      </td>
      <td class="px-4 py-3 max-w-xs">
        <p class="text-xs text-gray-700 leading-relaxed">\${esc(u.reason || '')}</p>
      </td>
      <td class="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">\${u.contact ? esc(u.contact) : '<span class="text-gray-300">—</span>'}</td>
      <td class="px-4 py-3 text-center text-xs text-gray-500">\${u.age || '—'}</td>
      <td class="px-4 py-3">
        \${(u.foundVia||[]).map(k=>\`<span class="tag mr-1">\${esc(k)}</span>\`).join('')}
      </td>
    </tr>
  \`).join('');
  document.getElementById('s-results').classList.remove('hidden');
}

function exportCSV() {
  const hdr = ['显示名','用户名','主页链接','Bio','推荐理由','联系方式','年龄','来源关键词'];
  const rows = searchData.map(u => [
    u.screenName, u.username, u.profileUrl,
    u.bio.replace(/[\n\r,]/g,' '), (u.reason||'').replace(/,/g,'，'),
    u.contact||'', u.age||'', (u.foundVia||[]).join('|'),
  ]);
  const csv = [hdr,...rows].map(r => r.map(c => '"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\\ufeff'+csv], {type:'text/csv;charset=utf-8'}));
  a.download = 'jike_users_' + new Date().toISOString().slice(0,10) + '.csv';
  a.click();
}

// ── Analyze ──
async function doAnalyze() {
  if (!checkTokens()) return;
  const input = document.getElementById('a-input').value.trim();
  if (!input) { alert('请输入用户链接或用户名'); return; }

  const btn = document.getElementById('a-btn');
  btn.disabled = true;
  btn.textContent = '分析中...';

  document.getElementById('a-results').classList.remove('hidden');
  document.getElementById('a-loading').classList.remove('hidden');
  document.getElementById('a-text').innerHTML = '';
  document.getElementById('a-name').textContent = '加载中...';
  document.getElementById('a-bio').textContent = '';
  document.getElementById('a-followers').textContent = '';
  document.getElementById('a-posts-count').textContent = '';

  let mdBuffer = '';

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input,
        question: document.getElementById('a-question').value.trim(),
        limit: parseInt(document.getElementById('a-limit').value),
        ...tokens(),
      }),
    });
    if (!resp.ok) { const e = await resp.json(); throw new Error(e.error); }

    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'user_info') {
            const p = evt.profile;
            document.getElementById('a-name').textContent = p.screenName;
            document.getElementById('a-link').href = p.profileUrl;
            document.getElementById('a-bio').textContent = p.bio;
            document.getElementById('a-followers').textContent = p.followersCount + ' 粉丝';
            document.getElementById('a-posts-count').textContent = '分析 ' + p.postCount + ' 条帖子';
          } else if (evt.type === 'text') {
            mdBuffer += evt.text;
            document.getElementById('a-text').innerHTML = marked.parse(mdBuffer);
          } else if (evt.type === 'done') {
            document.getElementById('a-loading').classList.add('hidden');
          }
        } catch {}
      }
    }
  } catch (e) {
    document.getElementById('a-loading').classList.add('hidden');
    document.getElementById('a-text').textContent = '分析失败：' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = '开始分析';
  }
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

loadCfg();
document.getElementById('cfg-btn').addEventListener('click', toggleCfg);
document.getElementById('cfg-save-btn').addEventListener('click', saveCfg);
document.getElementById('tab-s').addEventListener('click', function() { tab('s'); });
document.getElementById('tab-a').addEventListener('click', function() { tab('a'); });
document.getElementById('s-btn').addEventListener('click', doSearch);
document.getElementById('export-btn').addEventListener('click', exportCSV);
document.getElementById('a-btn').addEventListener('click', doAnalyze);
<\/script>
</body>
</html>`;

// ── Main ──────────────────────────────────────────────────────────────────────

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    if (url.pathname === '/api/search' && request.method === 'POST') {
      return handleSearch(request);
    }

    if (url.pathname === '/api/analyze' && request.method === 'POST') {
      return handleAnalyze(request);
    }

    return new Response(HTML, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  },
};
