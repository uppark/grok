"""Freemail Web GUI - 本地 Web 邮箱客户端，运行后在浏览器中打开。"""
import os
import webbrowser
import threading

from flask import Flask, request, jsonify, Response as FlaskResponse
from dotenv import load_dotenv
import requests as http_requests

load_dotenv()

WORKER_DOMAIN = os.getenv("WORKER_DOMAIN", "")
FREEMAIL_TOKEN = os.getenv("FREEMAIL_TOKEN", "")
BASE_URL = f"https://{WORKER_DOMAIN}".rstrip("/")
HEADERS = {"Authorization": f"Bearer {FREEMAIL_TOKEN}"}

app = Flask(__name__)


def proxy(method, path, **kwargs):
    """将请求代理到 freemail 后端。"""
    headers = dict(HEADERS)
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"
    resp = http_requests.request(
        method, f"{BASE_URL}{path}", headers=headers, timeout=15, **kwargs
    )
    excluded = {"content-encoding", "transfer-encoding", "connection"}
    resp_headers = {
        k: v for k, v in resp.headers.items() if k.lower() not in excluded
    }
    return FlaskResponse(resp.content, status=resp.status_code, headers=resp_headers)


# ── API 代理 ──────────────────────────────────────────────

@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_proxy(path):
    params = dict(request.args)
    data = request.get_data() or None
    content_type = request.content_type or ""
    kwargs = {"params": params}
    if data:
        if "json" in content_type:
            import json
            kwargs["json"] = json.loads(data)
        else:
            kwargs["data"] = data
    return proxy(request.method, f"/api/{path}", **kwargs)


# ── 前端页面 ──────────────────────────────────────────────

@app.route("/")
def index():
    return HTML_PAGE


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Freemail</title>
<style>
:root{--bg:#f0f2f5;--card:#fff;--border:#e0e0e0;--pri:#1677ff;--pri-hover:#4096ff;--danger:#ff4d4f;--text:#222;--text2:#666;--text3:#999;--radius:8px;--shadow:0 1px 3px rgba(0,0,0,.08)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"Microsoft YaHei UI","Segoe UI",sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}
button{cursor:pointer;border:1px solid var(--border);background:var(--card);padding:5px 14px;border-radius:4px;font-size:13px;color:var(--text);transition:.2s}
button:hover{border-color:var(--pri);color:var(--pri)}
button.pri{background:var(--pri);color:#fff;border-color:var(--pri)}
button.pri:hover{background:var(--pri-hover);border-color:var(--pri-hover)}
button.danger{color:var(--danger);border-color:var(--danger)}
button.danger:hover{background:var(--danger);color:#fff}
button.sm{padding:3px 10px;font-size:12px}
input,select{border:1px solid var(--border);border-radius:4px;padding:5px 10px;font-size:13px;outline:none}
input:focus,select:focus{border-color:var(--pri)}

/* toolbar */
.toolbar{display:flex;align-items:center;gap:8px;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--border);flex-wrap:wrap}
.toolbar .sep{width:1px;height:24px;background:var(--border)}
.toolbar .spacer{flex:1}
.toolbar .status{font-size:12px;color:var(--text3)}

/* main layout */
.main{flex:1;display:flex;overflow:hidden}
.panel{display:flex;flex-direction:column;border-right:1px solid var(--border);overflow:hidden}
.panel:last-child{border-right:none}
.panel-header{padding:10px 12px;font-weight:600;font-size:13px;border-bottom:1px solid var(--border);background:#fafafa;display:flex;align-items:center;gap:8px}
.panel-header .count{font-weight:400;color:var(--text3);font-size:12px}
.panel-body{flex:1;overflow-y:auto}

#mailbox-panel{width:300px;min-width:220px}
#email-panel{width:320px;min-width:240px}
#detail-panel{flex:1;min-width:400px}

/* list items */
.list-item{padding:10px 12px;border-bottom:1px solid #f0f0f0;cursor:pointer;transition:.15s}
.list-item:hover{background:#f7f8fa}
.list-item.active{background:#e6f4ff;border-left:3px solid var(--pri)}
.list-item .addr{font-size:13px;word-break:break-all}
.list-item .time{font-size:11px;color:var(--text3);margin-top:2px}
.list-item .subject{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.list-item .sender{font-size:12px;color:var(--text2);margin-top:1px}
.list-item .preview{font-size:12px;color:var(--text3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.list-item .code{display:inline-block;background:#f6ffed;color:#52c41a;border:1px solid #b7eb8f;border-radius:3px;padding:0 6px;font-size:11px;font-family:Consolas,monospace;margin-left:6px}
.list-item .actions{display:none;margin-top:4px}
.list-item:hover .actions{display:flex;gap:4px}

/* detail */
.detail-meta{padding:12px 16px;border-bottom:1px solid var(--border);font-size:13px;line-height:1.8}
.detail-meta .label{color:var(--text3);display:inline-block;width:50px}
.detail-meta .code-lg{font-size:16px;font-weight:700;color:#52c41a;font-family:Consolas,monospace;cursor:pointer}
.detail-tabs{display:flex;border-bottom:1px solid var(--border)}
.detail-tabs button{border:none;border-bottom:2px solid transparent;border-radius:0;padding:8px 16px;font-size:13px}
.detail-tabs button.active{border-bottom-color:var(--pri);color:var(--pri);font-weight:600}
.detail-content{flex:1;overflow:hidden;position:relative}
.detail-content .tab-pane{position:absolute;inset:0;overflow:auto;padding:16px;display:none}
.detail-content .tab-pane.active{display:block}
.detail-content pre{white-space:pre-wrap;word-break:break-all;font-family:Consolas,"Courier New",monospace;font-size:13px;line-height:1.6}
.detail-content iframe{width:100%;height:100%;border:none}

/* pagination */
.pagination{display:flex;align-items:center;gap:6px;padding:8px 12px;border-top:1px solid var(--border);font-size:12px;background:#fafafa}
.pagination button{padding:2px 8px;font-size:12px}
.pagination .info{color:var(--text3)}

/* empty */
.empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3);font-size:14px;flex-direction:column;gap:8px}

/* toast */
.toast{position:fixed;top:20px;right:20px;background:#333;color:#fff;padding:10px 20px;border-radius:6px;font-size:13px;z-index:9999;opacity:0;transition:.3s;pointer-events:none}
.toast.show{opacity:1}

/* search */
.search-box{display:flex;gap:4px;padding:8px 12px;border-bottom:1px solid var(--border)}
.search-box input{flex:1;font-size:12px}
</style>
</head>
<body>

<div class="toolbar">
  <button class="pri" onclick="generateMailbox()">生成邮箱</button>
  <button onclick="refreshMailboxes()">刷新邮箱</button>
  <div class="sep"></div>
  <button onclick="refreshEmails()">刷新邮件</button>
  <button onclick="loadLatest()">最新邮件</button>
  <div class="sep"></div>
  <button onclick="copyMailbox()">复制邮箱</button>
  <button onclick="copyCode()">复制验证码</button>
  <div class="spacer"></div>
  <label style="font-size:12px">自动刷新 <input type="checkbox" id="auto-refresh" checked></label>
  <span class="status" id="status">就绪</span>
</div>

<div class="main">
  <!-- 邮箱列表 -->
  <div class="panel" id="mailbox-panel">
    <div class="panel-header">邮箱列表 <span class="count" id="mailbox-count"></span></div>
    <div class="search-box">
      <input id="mailbox-search" placeholder="搜索邮箱..." oninput="onMailboxSearch()">
      <select id="mailbox-size" style="width:70px" onchange="mailboxPage=1;refreshMailboxes()">
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="200">200</option>
        <option value="500">500</option>
      </select>
    </div>
    <div class="panel-body" id="mailbox-list"></div>
    <div class="pagination">
      <button onclick="prevMailboxPage()">&lt;</button>
      <span class="info" id="mailbox-page-info">第1页</span>
      <button onclick="nextMailboxPage()">&gt;</button>
    </div>
  </div>

  <!-- 邮件列表 -->
  <div class="panel" id="email-panel">
    <div class="panel-header">邮件列表 <span class="count" id="email-count"></span></div>
    <div class="panel-body" id="email-list"></div>
  </div>

  <!-- 邮件详情 -->
  <div class="panel" id="detail-panel">
    <div class="detail-meta" id="detail-meta">
      <div><span class="label">主题</span> <span id="d-subject">-</span></div>
      <div><span class="label">发件人</span> <span id="d-sender">-</span></div>
      <div><span class="label">收件人</span> <span id="d-to">-</span></div>
      <div><span class="label">时间</span> <span id="d-time">-</span></div>
      <div><span class="label">验证码</span> <span class="code-lg" id="d-code" title="点击复制" onclick="copyCode()">-</span></div>
    </div>
    <div class="detail-tabs" id="detail-tabs">
      <button class="active" data-tab="text">纯文本</button>
      <button data-tab="html">HTML 预览</button>
      <button data-tab="source">HTML 源码</button>
    </div>
    <div class="detail-content" id="detail-content">
      <div class="tab-pane active" id="tab-text"><pre id="text-body"></pre></div>
      <div class="tab-pane" id="tab-html"><iframe id="html-frame" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe></div>
      <div class="tab-pane" id="tab-source"><pre id="source-body"></pre></div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let currentMailbox = null;
let currentEmailId = null;
let currentDetail = null;
let mailboxPage = 1;
let mailboxTotal = 0;
let mailboxes = [];
let searchTimer = null;

const $ = id => document.getElementById(id);

function toast(msg, ms=2000) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms);
}

function status(msg) { $('status').textContent = msg; }

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  const text = await resp.text();
  try { return JSON.parse(text); } catch { return text; }
}

// ── 邮箱列表 ────────────────────────────────

async function refreshMailboxes() {
  status('加载邮箱...');
  try {
    const size = parseInt($('mailbox-size').value);
    const q = $('mailbox-search').value.trim();
    const offset = (mailboxPage - 1) * size;
    let url = `/api/mailboxes?limit=${size}&offset=${offset}`;
    if (q) url += `&q=${encodeURIComponent(q)}`;
    const data = await api('GET', url);
    const list = data.list || data || [];
    mailboxTotal = data.total || list.length;
    mailboxes = list;
    renderMailboxes(list);
    $('mailbox-count').textContent = `(${mailboxTotal})`;
    const totalPages = Math.max(1, Math.ceil(mailboxTotal / size));
    $('mailbox-page-info').textContent = `第${mailboxPage}/${totalPages}页`;
    status(`已加载 ${list.length} 个邮箱`);
  } catch (e) {
    status('加载邮箱失败: ' + e.message);
  }
}

function renderMailboxes(list) {
  const el = $('mailbox-list');
  if (!list.length) {
    el.innerHTML = '<div class="empty">暂无邮箱<br><button class="pri" onclick="generateMailbox()">生成一个</button></div>';
    return;
  }
  el.innerHTML = list.map(m => {
    const active = currentMailbox === m.address ? ' active' : '';
    const fav = m.is_favorite ? ' ★' : '';
    return `<div class="list-item${active}" onclick="selectMailbox('${m.address}')">
      <div class="addr">${m.address}${fav}</div>
      <div class="time">${m.created_at || ''}</div>
      <div class="actions">
        <button class="sm danger" onclick="event.stopPropagation();deleteMailbox('${m.address}')">删除</button>
      </div>
    </div>`;
  }).join('');
}

function selectMailbox(addr) {
  currentMailbox = addr;
  renderMailboxes(mailboxes);
  refreshEmails();
}

async function generateMailbox() {
  status('生成邮箱...');
  try {
    const data = await api('GET', '/api/generate');
    toast('已生成: ' + data.email);
    mailboxPage = 1;
    await refreshMailboxes();
    selectMailbox(data.email);
  } catch (e) {
    toast('生成失败: ' + e.message);
  }
}

async function deleteMailbox(addr) {
  if (!confirm(`确认删除邮箱 ${addr} 及其所有邮件？`)) return;
  try {
    await api('DELETE', `/api/mailboxes?address=${encodeURIComponent(addr)}`);
    toast('已删除');
    if (currentMailbox === addr) { currentMailbox = null; clearDetail(); $('email-list').innerHTML = ''; }
    refreshMailboxes();
  } catch (e) { toast('删除失败: ' + e.message); }
}

function prevMailboxPage() {
  if (mailboxPage > 1) { mailboxPage--; refreshMailboxes(); }
}
function nextMailboxPage() {
  const size = parseInt($('mailbox-size').value);
  if (mailboxPage * size < mailboxTotal) { mailboxPage++; refreshMailboxes(); }
}

function onMailboxSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { mailboxPage = 1; refreshMailboxes(); }, 300);
}

// ── 邮件列表 ────────────────────────────────

async function refreshEmails() {
  if (!currentMailbox) { toast('请先选择邮箱'); return; }
  status('加载邮件...');
  try {
    const data = await api('GET', `/api/emails?mailbox=${encodeURIComponent(currentMailbox)}&limit=50`);
    const list = data.value || data || [];
    renderEmails(list);
    $('email-count').textContent = `(${list.length})`;
    status(`${currentMailbox} - ${list.length} 封邮件`);
  } catch (e) {
    status('加载邮件失败: ' + e.message);
  }
}

function renderEmails(list) {
  const el = $('email-list');
  if (!list.length) {
    el.innerHTML = '<div class="empty">暂无邮件</div>';
    return;
  }
  el.innerHTML = list.map(m => {
    const active = currentEmailId === m.id ? ' active' : '';
    const code = m.verification_code ? `<span class="code">${m.verification_code}</span>` : '';
    return `<div class="list-item${active}" onclick="selectEmail(${m.id})">
      <div class="subject">${esc(m.subject || '(无主题)')}${code}</div>
      <div class="sender">${esc(m.sender || '')}</div>
      <div class="time">${m.received_at || ''}</div>
      <div class="preview">${esc(m.preview || '')}</div>
      <div class="actions">
        <button class="sm danger" onclick="event.stopPropagation();deleteEmail(${m.id})">删除</button>
      </div>
    </div>`;
  }).join('');
}

async function selectEmail(id) {
  currentEmailId = id;
  status('加载邮件详情...');
  try {
    const data = await api('GET', `/api/email/${id}`);
    currentDetail = data;
    showDetail(data);
    // re-render to highlight
    const emailEls = $('email-list').querySelectorAll('.list-item');
    emailEls.forEach(el => el.classList.toggle('active', el.onclick.toString().includes(String(id))));
    status('邮件已加载');
  } catch (e) {
    status('加载详情失败: ' + e.message);
  }
}

async function loadLatest() {
  if (!currentMailbox) { toast('请先选择邮箱'); return; }
  status('加载最新邮件...');
  try {
    const data = await api('GET', `/api/emails?mailbox=${encodeURIComponent(currentMailbox)}&limit=1`);
    const list = data.value || data || [];
    if (!list.length) { toast('没有邮件'); return; }
    await refreshEmails();
    await selectEmail(list[0].id);
  } catch (e) { status('加载失败: ' + e.message); }
}

async function deleteEmail(id) {
  try {
    await api('DELETE', `/api/email/${id}`);
    toast('邮件已删除');
    if (currentEmailId === id) { currentEmailId = null; clearDetail(); }
    refreshEmails();
  } catch (e) { toast('删除失败: ' + e.message); }
}

// ── 邮件详情 ────────────────────────────────

function showDetail(d) {
  $('d-subject').textContent = d.subject || '-';
  $('d-sender').textContent = d.sender || '-';
  $('d-to').textContent = d.to_addrs || '-';
  $('d-time').textContent = d.received_at || '-';
  $('d-code').textContent = d.verification_code || '-';
  $('text-body').textContent = d.content || '(空)';
  $('source-body').textContent = d.html_content || '(无 HTML)';
  renderHtmlFrame(d.html_content || '', d.subject || '', d.sender || '', d.received_at || '');
}

function renderHtmlFrame(html, subject, sender, time) {
  const frame = $('html-frame');
  const doc = frame.contentDocument || frame.contentWindow.document;
  if (!html) {
    doc.open(); doc.write('<p style="color:#999;font-family:sans-serif;padding:20px">无 HTML 内容</p>'); doc.close();
    return;
  }
  const wrapper = `<!DOCTYPE html><html><head><meta charset="utf-8">
<base target="_blank">
<style>body{font-family:-apple-system,"Microsoft YaHei UI",sans-serif;margin:16px;color:#333;line-height:1.6}</style>
</head><body>${html}</body></html>`;
  doc.open(); doc.write(wrapper); doc.close();
}

function clearDetail() {
  currentDetail = null;
  $('d-subject').textContent = '-';
  $('d-sender').textContent = '-';
  $('d-to').textContent = '-';
  $('d-time').textContent = '-';
  $('d-code').textContent = '-';
  $('text-body').textContent = '';
  $('source-body').textContent = '';
  const frame = $('html-frame');
  const doc = frame.contentDocument || frame.contentWindow.document;
  doc.open(); doc.write(''); doc.close();
}

// ── Tab 切换 ─────────────────────────────────

$('detail-tabs').addEventListener('click', e => {
  const btn = e.target.closest('button');
  if (!btn || !btn.dataset.tab) return;
  $('detail-tabs').querySelectorAll('button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  $('detail-content').querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  $('tab-' + btn.dataset.tab).classList.add('active');
});

// ── 复制功能 ────────────────────────────────

function copyMailbox() {
  if (!currentMailbox) { toast('请先选择邮箱'); return; }
  navigator.clipboard.writeText(currentMailbox);
  toast('已复制: ' + currentMailbox);
}

function copyCode() {
  const code = $('d-code').textContent.trim();
  if (!code || code === '-') { toast('当前没有验证码'); return; }
  navigator.clipboard.writeText(code.replace(/-/g, ''));
  toast('已复制验证码: ' + code);
}

// ── 自动刷新 ────────────────────────────────

setInterval(() => {
  if (!$('auto-refresh').checked) return;
  if (currentMailbox) refreshEmails();
}, 10000);

// ── 工具函数 ────────────────────────────────

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── 初始化 ──────────────────────────────────

refreshMailboxes();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = 5099
    print(f"Freemail Web GUI: http://127.0.0.1:{port}")
    threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
