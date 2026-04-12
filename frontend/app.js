// ============================================
// FRONTEND
// ============================================

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8080'
  : '';

// ---- STATE ----

let token = localStorage.getItem('sr_token');
let username = localStorage.getItem('sr_username');

// ---- DOM REFS ----

const authScreen     = document.getElementById('auth-screen');
const dashScreen     = document.getElementById('dashboard-screen');
const loginForm      = document.getElementById('login-form');
const signupForm     = document.getElementById('signup-form');
const authError      = document.getElementById('auth-error');
const agentName      = document.getElementById('agent-name');
const logoutBtn      = document.getElementById('logout-btn');
const searchInput    = document.getElementById('search-input');
const searchBtn      = document.getElementById('search-btn');
const searchResults  = document.getElementById('search-results');
const searchEmpty    = document.getElementById('search-empty');
const resultsList    = document.getElementById('results-list');
const resultsCount   = document.getElementById('results-count');
const uploadArea     = document.getElementById('upload-area');
const fileInput      = document.getElementById('file-input');
const uploadStatus   = document.getElementById('upload-status');
const docList        = document.getElementById('doc-list');

// ---- INIT ----

if (token && username) {
  showDashboard();
} else {
  showAuth();
}

// ---- AUTH TABS ----

document.querySelectorAll('.auth-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
    tab.classList.add('active');
    const formId = tab.dataset.tab === 'login' ? 'login-form' : 'signup-form';
    document.getElementById(formId).classList.add('active');
    hideAuthError();
  });
});

// ---- LOGIN ----

loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const user = document.getElementById('login-username').value.trim();
  const pass = document.getElementById('login-password').value;
  if (!user || !pass) return;

  const btn = loginForm.querySelector('.btn-primary');
  setLoading(btn, true);

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || 'Login failed');

    token = data.token;
    username = user;
    localStorage.setItem('sr_token', token);
    localStorage.setItem('sr_username', username);
    showDashboard();
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setLoading(btn, false);
  }
});

// ---- SIGNUP ----

signupForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const user = document.getElementById('signup-username').value.trim();
  const pass = document.getElementById('signup-password').value;
  if (!user || !pass) return;

  const btn = signupForm.querySelector('.btn-primary');
  setLoading(btn, true);

  try {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || 'Signup failed');

    // Auto-login after signup
    const loginRes = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass }),
    });
    const loginData = await loginRes.json();
    if (!loginRes.ok) throw new Error('Account created but login failed. Please log in manually.');

    token = loginData.token;
    username = user;
    localStorage.setItem('sr_token', token);
    localStorage.setItem('sr_username', username);
    showDashboard();
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setLoading(btn, false);
  }
});

// ---- LOGOUT ----

logoutBtn.addEventListener('click', () => {
  token = null;
  username = null;
  localStorage.removeItem('sr_token');
  localStorage.removeItem('sr_username');
  showAuth();
});

// ---- SEARCH ----

searchBtn.addEventListener('click', doSearch);
searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') doSearch();
});

async function doSearch() {
  const query = searchInput.value.trim();
  if (!query) return;

  searchResults.classList.add('hidden');
  searchEmpty.classList.add('hidden');
  setLoading(searchBtn, true);

  try {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (res.status === 401) return handleExpired();
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || 'Search failed');

    if (!data.length) {
      searchEmpty.classList.remove('hidden');
      return;
    }

    renderResults(data);
  } catch (err) {
    searchEmpty.classList.remove('hidden');
    document.querySelector('.search-empty p').textContent = `ERROR: ${err.message}`;
  } finally {
    setLoading(searchBtn, false);
  }
}

function renderResults(results) {
  resultsCount.textContent = `${results.length} MATCH${results.length !== 1 ? 'ES' : ''}`;
  resultsList.innerHTML = results.map(r => {
    const pct = Math.round(r.score * 100);
    const scoreClass = pct >= 80 ? 'score-high' : pct >= 50 ? 'score-mid' : 'score-low';
    return `
      <div class="result-card">
        <div class="result-meta">
          <span class="result-score ${scoreClass}">${pct}%</span>
          <span class="result-filename">${escapeHtml(r.filename)}</span>
        </div>
        <p class="result-text">${escapeHtml(r.text)}</p>
      </div>
    `;
  }).join('');
  searchResults.classList.remove('hidden');
}

// ---- FILE UPLOAD ----

uploadArea.addEventListener('click', () => fileInput.click());

uploadArea.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
  uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  uploadFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => {
  uploadFiles(fileInput.files);
});

async function uploadFiles(fileList) {
  const pdfs = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!pdfs.length) {
    showUploadStatus('Only PDF files are supported.', 'error');
    return;
  }

  const total = pdfs.length;
  let uploaded = 0;
  let failed = 0;

  showUploadStatus(`Uploading ${total} file${total > 1 ? 's' : ''}...`, 'processing');

  for (const file of pdfs) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/documents`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });

      if (res.status === 401) return handleExpired();
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || 'Upload failed');
      uploaded++;
    } catch (err) {
      failed++;
    }

    showUploadStatus(
      `Uploading... ${uploaded + failed}/${total}` + (failed ? ` (${failed} failed)` : ''),
      'processing'
    );
  }

  if (failed === 0) {
    showUploadStatus(`Uploaded ${uploaded} file${uploaded > 1 ? 's' : ''}.`, 'success');
  } else {
    showUploadStatus(`Uploaded ${uploaded}/${total}. ${failed} failed.`, 'error');
  }

  fileInput.value = '';
  loadDocuments();
}

// ---- DOCUMENTS ----

async function loadDocuments() {
  docList.innerHTML = '<div class="doc-loading"><span class="spinner"></span>LOADING DOCUMENTS...</div>';

  try {
    const res = await fetch(`${API_BASE}/documents`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (res.status === 401) return handleExpired();
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || 'Failed to load documents');

    if (!data.length) {
      docList.innerHTML = '<div class="doc-empty">NO DOCUMENTS IN DATABASE</div>';
      return;
    }

    docList.innerHTML = data.map(doc => {
      const statusClass = doc.status === 'ready' ? 'status-ready'
        : doc.status === 'processing' ? 'status-processing'
        : 'status-error';

      const date = new Date(doc.upload_date).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric'
      });

      return `
        <div class="doc-row" data-id="${doc.document_id}">
          <span class="doc-col doc-col-name">${escapeHtml(doc.filename)}</span>
          <span class="doc-col doc-col-status">
            <span class="status-badge ${statusClass}">${doc.status.toUpperCase()}</span>
          </span>
          <span class="doc-col doc-col-pages">${doc.page_count ?? '—'}</span>
          <span class="doc-col doc-col-date">${date}</span>
          <span class="doc-col doc-col-action">
            <button class="btn btn-delete" onclick="deleteDoc('${doc.document_id}')">DELETE</button>
          </span>
        </div>
      `;
    }).join('');

    // If any docs are processing, poll again
    if (data.some(d => d.status === 'processing')) {
      setTimeout(loadDocuments, 5000);
    }
  } catch (err) {
    docList.innerHTML = `<div class="doc-empty">ERROR: ${escapeHtml(err.message)}</div>`;
  }
}

async function deleteDoc(docId) {
  try {
    const res = await fetch(`${API_BASE}/documents/${docId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` },
    });

    if (res.status === 401) return handleExpired();
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.error || data.detail || 'Delete failed');
    }

    loadDocuments();
  } catch (err) {
    showUploadStatus(`DELETE FAILED: ${err.message}`, 'error');
  }
}

// Make deleteDoc available from inline onclick
window.deleteDoc = deleteDoc;

// ---- HELPERS ----

function showAuth() {
  authScreen.classList.add('active');
  dashScreen.classList.remove('active');
  loginForm.reset();
  signupForm.reset();
  hideAuthError();
}

function showDashboard() {
  authScreen.classList.remove('active');
  dashScreen.classList.add('active');
  agentName.textContent = `Logged in as ${username}`;
  loadDocuments();
}

function showAuthError(msg) {
  authError.textContent = msg;
  authError.classList.remove('hidden');
}

function hideAuthError() {
  authError.classList.add('hidden');
}

function showUploadStatus(msg, type) {
  uploadStatus.textContent = msg;
  uploadStatus.className = `upload-status ${type}`;
}

function handleExpired() {
  token = null;
  username = null;
  localStorage.removeItem('sr_token');
  localStorage.removeItem('sr_username');
  showAuth();
  showAuthError('SESSION EXPIRED — PLEASE LOG IN AGAIN');
}

function setLoading(btn, loading) {
  if (loading) {
    btn.disabled = true;
    btn.dataset.origText = btn.querySelector('.btn-text').textContent;
    btn.querySelector('.btn-text').textContent = 'LOADING...';
  } else {
    btn.disabled = false;
    btn.querySelector('.btn-text').textContent = btn.dataset.origText;
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
