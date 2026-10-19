// ListeningLab Frontend — Vanilla ES Module
const API_BASE = '';

async function apiGet(path) {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function apiPost(path, data) {
  const r = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function apiDelete(path) {
  const r = await fetch(API_BASE + path, { method: 'DELETE' });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

const state = {
  papers: [],
  currentPaper: null,
  currentSentenceIdx: 0,
  sentences: [],
  bookmarks: [],
  settings: {},
  stats: {},
  player: {
    audio: new Audio(),
    isPlaying: false,
    playbackRate: 1.0,
    loopMode: 'sentence',
    loopCountTarget: 2,
    currentLoopIteration: 0,
    abPointA: null,
    abPointB: null,
    transcriptVisibility: 'visible',
  },
  dictationResult: null,
};

function showView(viewName) {
  const viewId = 'view-' + viewName;
  $$('.view-container').forEach(v => v.classList.remove('active'));
  const el = document.getElementById(viewId);
  if (el) el.classList.add('active');
  $$('.nav-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === viewName));
}

function formatTime(s) {
  if (!s || !isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s % 1) * 10);
  return m + ':' + String(sec).padStart(2, '0') + (ms ? '.' + ms : '');
}

async function init() {
  state.settings = await apiGet('/api/settings');
  applyTheme(state.settings.theme || 'light');
  state.papers = (await apiGet('/api/papers')).papers || [];
  state.bookmarks = (await apiGet('/api/bookmarks')).bookmarks || [];
  state.stats = await apiGet('/api/stats');
  renderLibrary();
  renderReview();
  renderStats();
  renderSettings();
  setupPlayer();
  setupNav();
  setupKeyboard();
  setupImport();
  setupModals();
  showView('library');
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const sun = $('#themeIconSun');
  const moon = $('#themeIconMoon');
  if (sun) sun.style.display = theme === 'dark' ? 'none' : 'block';
  if (moon) moon.style.display = theme === 'dark' ? 'block' : 'none';
}

function setupNav() {
  $$('.nav-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      if (view === 'review') loadBookmarks();
      if (view === 'stats') loadStats();
      if (view === 'settings') loadSettings();
      showView(view);
    });
  });
  $('.brand-section').addEventListener('click', () => showView('library'));
  $('#themeToggleBtn').addEventListener('click', toggleTheme);
  $('#shortcutHelpBtn').addEventListener('click', () => {
    $('#shortcutsModal').classList.add('active');
  });
  $('#shortcutsModalOkBtn').addEventListener('click', () => {
    $('#shortcutsModal').classList.remove('active');
  });
  $('#closeShortcutsModalBtn').addEventListener('click', () => {
    $('#shortcutsModal').classList.remove('active');
  });
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  apiPost('/api/settings', { ...state.settings, theme: next });
  state.settings.theme = next;
}

// ==================== Library ====================
function renderLibrary() {
  const grid = $('#setGridContainer');
  if (!grid) return;
  if (!state.papers.length) {
    grid.innerHTML = '<div class="card" style="grid-column:1/-1;padding:40px;text-align:center;color:var(--text-muted)">暂无听力材料，请点击右上角导入本地音频/字幕。</div>';
    return;
  }
  grid.innerHTML = state.papers.map(p => {
    const progress = p.progress || {};
    const pct = p.sentence_count ? Math.round(((progress.current_sentence_idx || 0) / p.sentence_count) * 100) : 0;
    return `
    <div class="set-card ${p.id === (state.currentPaper?.id) ? 'is-active-card' : ''}" data-id="${p.id}">
      <div class="set-card-header">
        <div>
          <div class="set-card-title">${p.title}</div>
          <div class="set-meta-tags">
            <span class="badge badge-neutral">${p.year || '自定义'}</span>
            <span class="badge badge-neutral">${p.category === 'custom-import' ? '导入' : '真题'}</span>
            <span class="badge badge-neutral">${p.sentence_count || 0} 句</span>
          </div>
        </div>
      </div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
      <div class="set-stats-row">
        <span>进度 ${pct}%</span>
        <span>${p.sentence_count || 0} 句</span>
      </div>
      <div class="set-card-footer">
        <button class="btn btn-primary btn-sm btn-start" data-id="${p.id}">
          ${pct > 0 ? '继续练习' : '开始精听'}
        </button>
        <button class="btn btn-outline btn-sm btn-dictation" data-id="${p.id}">听写</button>
      </div>
    </div>
    `;
  }).join('');

  $$('.btn-start').forEach(b => b.addEventListener('click', e => loadPaper(e.target.closest('.btn-start').dataset.id, 'practice')));
  $$('.btn-dictation').forEach(b => b.addEventListener('click', e => loadPaper(e.target.closest('.btn-dictation').dataset.id, 'dictation')));

  $('#libraryCountBadge').textContent = state.papers.length;
}

async function loadPaper(paperId, targetView) {
  const paper = await apiGet('/api/papers/' + encodeURIComponent(paperId));
  state.currentPaper = paper;
  state.sentences = paper.sentences || [];
  state.currentSentenceIdx = (paper.progress && paper.progress.current_sentence_idx) || 0;
  if (state.currentSentenceIdx >= state.sentences.length) state.currentSentenceIdx = 0;

  if (paper.audio_path) {
    state.player.audio.src = paper.audio_path;
  } else if (paper.sentences && paper.sentences[0] && paper.sentences[0].audio_path) {
    state.player.audio.src = paper.sentences[0].audio_path;
  } else {
    state.player.audio.removeAttribute('src');
    showToast(`该套题音频缺失，请在终端执行: python3 content/tts/synthesize.py content/papers/${paperId}.json`);
  }
  state.player.audio.playbackRate = state.settings.default_playback_rate || 1.0;
  state.player.playbackRate = state.settings.default_playback_rate || 1.0;
  state.player.loopCountTarget = state.settings.default_loop_count || 2;
  state.player.transcriptVisibility = state.settings.default_transcript_visibility || 'visible';

  if (targetView === 'practice') {
    renderPractice();
    showView('practice');
  } else if (targetView === 'dictation') {
    renderDictation();
    showView('dictation');
  }
}

// ==================== Practice ====================
function renderPractice() {
  const paper = state.currentPaper;
  if (!paper) return;
  $('#practiceSetTitle').textContent = paper.title;
  $('#practiceSectionBadge').textContent = (paper.sections && paper.sections[0] && paper.sections[0].title) || 'Section A';
  $('#sentenceProgressRatio').textContent = (state.currentSentenceIdx + 1) + ' / ' + state.sentences.length;

  const list = $('#sentenceListEl');
  list.innerHTML = state.sentences.map((s, i) => `
    <div class="sentence-nav-item ${i === state.currentSentenceIdx ? 'active' : ''}" data-idx="${i}">
      <div class="item-top-row">
        <span class="item-num">#${i + 1}</span>
        <span class="item-time">${formatTime(s.start_time)} - ${formatTime(s.end_time)}</span>
      </div>
      <div class="item-text-preview">${s.english ? s.english.slice(0, 40) + (s.english.length > 40 ? '...' : '') : ''}</div>
    </div>
  `).join('');
  $$('#sentenceListEl .sentence-nav-item').forEach(el => {
    el.addEventListener('click', () => {
      state.currentSentenceIdx = parseInt(el.dataset.idx);
      refreshPracticeSentence();
      saveProgress();
    });
  });

  refreshPracticeSentence();
}

function refreshPracticeSentence() {
  const s = state.sentences[state.currentSentenceIdx];
  if (!s) return;
  $('#currentSentenceBadge').textContent = '第 ' + (state.currentSentenceIdx + 1) + ' 句';
  $('#currentSentenceTimeRange').textContent = formatTime(s.start_time) + ' - ' + formatTime(s.end_time);

  const statusEl = $('#currentSentenceStatusBadge');
  if (s.status === 'dictated') { statusEl.textContent = '已听写'; statusEl.className = 'badge badge-success'; }
  else if (s.status === 'listened') { statusEl.textContent = '已听过'; statusEl.className = 'badge badge-primary'; }
  else { statusEl.textContent = '未开始'; statusEl.className = 'badge badge-neutral'; }

  const textEl = $('#sentenceEnglishDisplay');
  textEl.textContent = s.english || '';
  updateTranscriptMode();

  const transEl = $('#sentenceChineseDisplay');
  if (transEl) transEl.textContent = s.chinese || '';

  const vocabEl = $('#sentenceVocabChips');
  if (vocabEl) {
    try {
      const vocab = JSON.parse(s.key_vocab || '[]');
      vocabEl.innerHTML = (vocab || []).map(v => `<span class="vocab-chip"><b>${v.word}</b> / ${v.definition || ''}</span>`).join('');
    } catch { vocabEl.innerHTML = ''; }
  }

  $$('#sentenceListEl .sentence-nav-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.idx) === state.currentSentenceIdx);
  });

  $('#sentenceProgressRatio').textContent = (state.currentSentenceIdx + 1) + ' / ' + state.sentences.length;

  const bmBtn = $('#bookmarkToggleBtn');
  const bmText = $('#bookmarkBtnText');
  const bmIcon = $('#bookmarkIcon');
  if (s.is_bookmarked) {
    bmBtn.classList.add('active');
    bmText.textContent = '已收藏';
    if (bmIcon) bmIcon.setAttribute('fill', 'currentColor');
  } else {
    bmBtn.classList.remove('active');
    bmText.textContent = '收藏难句';
    if (bmIcon) bmIcon.setAttribute('fill', 'none');
  }

  if (state.player.audio && s.start_time != null) {
    state.player.audio.currentTime = s.start_time;
  }
  updatePlayerUI();
}

function updateTranscriptMode() {
  const textEl = $('#sentenceEnglishDisplay');
  const notice = $('#sentenceMaskNotice');
  const btnText = $('#maskBtnText');
  const modes = ['visible', 'blur', 'hidden'];
  const labels = ['隐藏原文', '模糊原文', '显示原文'];
  const idx = modes.indexOf(state.player.transcriptVisibility);
  textEl.className = 'sentence-english-text mode-' + state.player.transcriptVisibility;
  if (notice) notice.classList.toggle('visible', state.player.transcriptVisibility !== 'visible');
  if (btnText) btnText.textContent = labels[idx];
}

function cycleTranscript() {
  const modes = ['visible', 'blur', 'hidden'];
  const idx = modes.indexOf(state.player.transcriptVisibility);
  state.player.transcriptVisibility = modes[(idx + 1) % modes.length];
  updateTranscriptMode();
}

function setupPlayer() {
  const audio = state.player.audio;
  audio.addEventListener('timeupdate', () => {
    updatePlayerUI();
    checkLoopBoundaries();
  });
  audio.addEventListener('play', () => { state.player.isPlaying = true; updatePlayerUI(); });
  audio.addEventListener('pause', () => { state.player.isPlaying = false; updatePlayerUI(); });
  audio.addEventListener('error', () => {
    state.player.isPlaying = false;
    updatePlayerUI();
    const pid = (state.currentPaper && state.currentPaper.id) || '';
    const cmd = pid ? `python3 content/tts/synthesize.py content/papers/${pid}.json` : 'python3 content/tts/synthesize.py';
    showToast(`音频缺失或加载失败，请在终端执行: ${cmd}`);
  });
  audio.addEventListener('ended', () => {
    state.player.isPlaying = false;
    if (state.settings.auto_play_next && state.player.loopMode !== 'sentence') {
      nextSentence();
      return;
    }
    if (state.player.loopMode === 'sentence' && state.player.currentLoopIteration < state.player.loopCountTarget - 1) {
      state.player.currentLoopIteration++;
      const s = state.sentences[state.currentSentenceIdx];
      if (s) audio.currentTime = s.start_time || 0;
      audio.play();
    }
  });

  $('#mainPlayPauseBtn').addEventListener('click', togglePlay);
  $('#prevSentenceBtn').addEventListener('click', () => { prevSentence(); saveProgress(); });
  $('#nextSentenceBtn').addEventListener('click', () => { nextSentence(); saveProgress(); });
  $('#replaySentenceBtn').addEventListener('click', replaySentence);
  $('#speedSelect').addEventListener('change', e => {
    state.player.playbackRate = parseFloat(e.target.value);
    audio.playbackRate = state.player.playbackRate;
  });
  $('#loopSelect').addEventListener('change', e => {
    state.player.loopCountTarget = parseInt(e.target.value);
    state.player.loopMode = state.player.loopCountTarget === 999 ? 'off' : 'sentence';
    $('#loopCounterBadge').textContent = state.player.loopCountTarget === 999 ? '∞' : String(state.player.loopCountTarget);
  });
  $('#toggleMaskBtn').addEventListener('click', cycleTranscript);
  $('#bookmarkToggleBtn').addEventListener('click', toggleBookmarkCurrent);
  $('#jumpToDictationBtn').addEventListener('click', () => {
    renderDictation();
    showView('dictation');
  });
  $('#timelineTrack').addEventListener('click', e => {
    if (!audio.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    audio.currentTime = ratio * audio.duration;
  });
  $('#btnSetA').addEventListener('click', () => {
    state.player.abPointA = audio.currentTime;
    updateABMarkers();
  });
  $('#btnSetB').addEventListener('click', () => {
    state.player.abPointB = audio.currentTime;
    updateABMarkers();
  });
  $('#btnClearAB').addEventListener('click', () => {
    state.player.abPointA = null;
    state.player.abPointB = null;
    updateABMarkers();
  });
}

function updateABMarkers() {
  const a = state.player.abPointA;
  const b = state.player.abPointB;
  const audio = state.player.audio;
  const dur = audio.duration || 1;
  const ma = $('#markerPointA');
  const mb = $('#markerPointB');
  const badge = $('#abStatusBadge');
  if (ma) ma.style.left = (a != null ? (a / dur * 100) : -10) + '%';
  if (mb) mb.style.left = (b != null ? (b / dur * 100) : -10) + '%';
  if (badge) badge.textContent = a != null && b != null ? 'A-B 已设定' : 'A-B 未设定';
}

function updatePlayerUI() {
  const audio = state.player.audio;
  const icon = $('#mainPlayPauseBtn');
  if (icon) icon.innerHTML = state.player.isPlaying
    ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
    : '<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
  $('#audioCurrentTime').textContent = formatTime(audio.currentTime);
  $('#audioDurationTime').textContent = formatTime(audio.duration);
  const pct = audio.duration ? (audio.currentTime / audio.duration * 100) : 0;
  $('#timelineProgress').style.width = pct + '%';
  $('#speedSelect').value = String(state.player.playbackRate);
  $('#loopSelect').value = String(state.player.loopCountTarget);
  $('#loopCounterBadge').textContent = state.player.loopCountTarget === 999 ? '∞' : String(state.player.loopCountTarget);
  updateABMarkers();
}

function togglePlay() {
  const audio = state.player.audio;
  if (!audio.src) {
    const pid = (state.currentPaper && state.currentPaper.id) || '';
    const cmd = pid ? `python3 content/tts/synthesize.py content/papers/${pid}.json` : 'python3 content/tts/synthesize.py';
    showToast(`该套题音频缺失，请在终端执行: ${cmd}`);
    return;
  }
  if (state.player.isPlaying) audio.pause();
  else {
    state.player.currentLoopIteration = 0;
    audio.play().catch(e => {
      const pid = (state.currentPaper && state.currentPaper.id) || '';
      const cmd = pid ? `python3 content/tts/synthesize.py content/papers/${pid}.json` : 'python3 content/tts/synthesize.py';
      showToast(`音频播放失败，请在终端执行: ${cmd}`);
    });
  }
}
function prevSentence() {
  if (state.currentSentenceIdx > 0) {
    state.currentSentenceIdx--;
    refreshPracticeSentence();
  }
}
function nextSentence() {
  if (state.currentSentenceIdx < state.sentences.length - 1) {
    state.currentSentenceIdx++;
    refreshPracticeSentence();
  }
}
function replaySentence() {
  const s = state.sentences[state.currentSentenceIdx];
  if (s && state.player.audio) {
    state.player.audio.currentTime = s.start_time || 0;
    state.player.currentLoopIteration = 0;
    state.player.audio.play();
  }
}
function checkLoopBoundaries() {
  const s = state.sentences[state.currentSentenceIdx];
  if (!s || !state.player.isPlaying) return;
  const audio = state.player.audio;
  const ct = audio.currentTime;
  if (state.player.abPointA != null && state.player.abPointB != null) {
    if (ct >= state.player.abPointB) {
      audio.currentTime = state.player.abPointA;
    }
  } else if (s.end_time > s.start_time) {
    if (ct >= s.end_time) {
      if (state.player.loopMode === 'sentence') {
        if (state.player.currentLoopIteration < state.player.loopCountTarget - 1) {
          state.player.currentLoopIteration++;
          audio.currentTime = s.start_time;
        } else {
          audio.pause();
          state.player.isPlaying = false;
          if (state.settings.auto_play_next) nextSentence();
          updatePlayerUI();
        }
      } else {
        audio.pause();
        state.player.isPlaying = false;
        updatePlayerUI();
      }
    }
  }
}
async function toggleBookmarkCurrent() {
  const s = state.sentences[state.currentSentenceIdx];
  if (!s) return;
  const res = await apiPost('/api/bookmarks', { sentence_id: s.id, paper_id: state.currentPaper.id });
  s.is_bookmarked = res.bookmarked ? 1 : 0;
  refreshPracticeSentence();
  state.bookmarks = (await apiGet('/api/bookmarks')).bookmarks || [];
  renderReview();
}
async function saveProgress() {
  if (!state.currentPaper) return;
  await apiPost('/api/progress', {
    paper_id: state.currentPaper.id,
    current_sentence_idx: state.currentSentenceIdx,
    playback_rate: state.player.playbackRate,
    loop_mode: state.player.loopMode,
    loop_count_target: state.player.loopCountTarget,
    transcript_visibility: state.player.transcriptVisibility,
  });
}

// ==================== Dictation ====================
function renderDictation() {
  const s = state.sentences[state.currentSentenceIdx];
  if (!s) return;
  $('#dictationSentenceTitle').textContent = (state.currentPaper?.title || '') + ' · 第 ' + (state.currentSentenceIdx + 1) + ' 句';
  $('#dictationTextarea').value = '';
  $('#dictationWordCount').textContent = '已输入 0 个单词';
  $('#diffResultPanel').style.display = 'none';
  state.dictationResult = null;
}

function setupDictation() {
  const textarea = $('#dictationTextarea');
  textarea.addEventListener('input', () => {
    const words = textarea.value.trim().split(/\s+/).filter(Boolean);
    $('#dictationWordCount').textContent = '已输入 ' + words.length + ' 个单词';
  });
  $('#submitDictationBtn').addEventListener('click', submitDictation);
  $('#dictationPlayBtn').addEventListener('click', replaySentence);
  $('#dictationSlowBtn').addEventListener('click', () => {
    state.player.audio.playbackRate = 0.75;
    state.player.audio.currentTime = state.sentences[state.currentSentenceIdx]?.start_time || 0;
    state.player.audio.play();
  });
  $('#dictationNextSentenceBtn').addEventListener('click', () => {
    nextSentence();
    renderDictation();
  });
  $('#backToPracticeBtn').addEventListener('click', () => {
    renderPractice();
    showView('practice');
  });
  $('#retryDictationBtn').addEventListener('click', () => {
    $('#dictationTextarea').value = '';
    $('#dictationWordCount').textContent = '已输入 0 个单词';
    $('#diffResultPanel').style.display = 'none';
  });
  $('#diffBookmarkBtn').addEventListener('click', toggleBookmarkCurrent);
  $('#clearDictationInputBtn').addEventListener('click', () => {
    $('#dictationTextarea').value = '';
    $('#dictationWordCount').textContent = '已输入 0 个单词';
  });
  $('#fillCorrectDemoBtn').addEventListener('click', () => {
    const s = state.sentences[state.currentSentenceIdx];
    if (s) $('#dictationTextarea').value = s.english;
  });
  $('#fillErrorDemoBtn').addEventListener('click', () => {
    const s = state.sentences[state.currentSentenceIdx];
    if (s) $('#dictationTextarea').value = s.english.split(' ').slice(1).join(' ') + ' extra';
  });
}

async function submitDictation() {
  const s = state.sentences[state.currentSentenceIdx];
  if (!s) return;
  const input = $('#dictationTextarea').value;
  const res = await apiPost('/api/dictation', {
    sentence_id: s.id,
    paper_id: state.currentPaper.id,
    user_input: input,
    expected: s.english,
  });
  state.dictationResult = res;
  renderDiff(res, s);
}

function renderDiff(result, sentence) {
  $('#diffResultPanel').style.display = 'flex';
  $('#diffAccuracyVal').textContent = result.accuracy + '%';
  const grade = result.accuracy >= 95 ? '优秀' : result.accuracy >= 80 ? '良好' : result.accuracy >= 60 ? '及格' : '需加强';
  $('#diffGradeText').textContent = '正确率 · ' + grade;
  $('#diffReferenceEn').textContent = sentence.english;
  $('#diffReferenceCn').textContent = sentence.chinese || '';

  const container = $('#diffTokensContainer');
  container.innerHTML = result.tokens.map(t => {
    if (t.type === 'correct') return `<span class="diff-token correct">${t.word}</span>`;
    if (t.type === 'wrong') return `<span class="diff-token wrong">${t.actual}</span><span class="diff-token expected-correction">${t.expected}</span>`;
    if (t.type === 'missing') return `<span class="diff-token missing">${t.word}</span>`;
    if (t.type === 'extra') return `<span class="diff-token extra">${t.word}</span>`;
    return '';
  }).join(' ');
}

// ==================== Review ====================
async function loadBookmarks() {
  const data = await apiGet('/api/bookmarks');
  state.bookmarks = data.bookmarks || [];
  renderReview();
}
function renderReview() {
  const list = $('#reviewListContainer');
  if (!list) return;
  if (!state.bookmarks.length) {
    list.innerHTML = '<div class="card" style="grid-column:1/-1;padding:40px;text-align:center;color:var(--text-muted)">暂无收藏难句，在精听或听写时点击星标添加。</div>';
    $('#totalBookmarkCount').textContent = '0';
    $('#unmasteredBookmarkCount').textContent = '0';
    $('#masteredBookmarkCount').textContent = '0';
    $('#reviewCountBadge').textContent = '0';
    return;
  }
  $('#totalBookmarkCount').textContent = state.bookmarks.length;
  $('#unmasteredBookmarkCount').textContent = state.bookmarks.length; // simplified
  $('#masteredBookmarkCount').textContent = '0';
  $('#reviewCountBadge').textContent = state.bookmarks.length;

  list.innerHTML = state.bookmarks.map(b => `
    <div class="review-item-card card" data-sid="${b.sentence_id}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <div style="flex:1;">
          <div style="font-size:15px;font-weight:600;margin-bottom:6px;">${b.english}</div>
          <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">${b.chinese || ''}</div>
          <div class="set-meta-tags">
            <span class="badge badge-neutral">${b.paper_title}</span>
            <span class="badge badge-neutral">#${(b.idx || 0) + 1}</span>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <button class="btn btn-primary btn-sm btn-review-play" data-sid="${b.sentence_id}">▶ 播放</button>
          <button class="btn btn-outline btn-sm btn-review-dictate" data-sid="${b.sentence_id}">听写</button>
          <button class="btn btn-danger btn-sm btn-review-remove" data-sid="${b.sentence_id}">移除</button>
        </div>
      </div>
    </div>
  `).join('');

  $$('.btn-review-remove').forEach(b => b.addEventListener('click', async e => {
    const sid = e.target.closest('.btn-review-remove').dataset.sid;
    await apiDelete('/api/bookmarks/' + encodeURIComponent(sid));
    loadBookmarks();
  }));
  $$('.btn-review-play').forEach(b => b.addEventListener('click', e => playBookmarked(e.target.closest('.btn-review-play').dataset.sid)));
  $$('.btn-review-dictate').forEach(b => b.addEventListener('click', e => {
    const sid = e.target.closest('.btn-review-dictate').dataset.sid;
    const bm = state.bookmarks.find(x => x.sentence_id === sid);
    if (bm) {
      loadPaper(bm.paper_id, 'dictation').then(() => {
        const idx = state.sentences.findIndex(s => s.id === sid);
        if (idx >= 0) { state.currentSentenceIdx = idx; renderDictation(); }
      });
    }
  }));
}
async function playBookmarked(sid) {
  const bm = state.bookmarks.find(x => x.sentence_id === sid);
  if (!bm) return;
  await loadPaper(bm.paper_id, 'practice');
  const idx = state.sentences.findIndex(s => s.id === sid);
  if (idx >= 0) {
    state.currentSentenceIdx = idx;
    refreshPracticeSentence();
    togglePlay();
  }
}

// ==================== Stats ====================
async function loadStats() {
  state.stats = await apiGet('/api/stats');
  renderStats();
}
function renderStats() {
  const s = state.stats;
  // Update KPI cards if we had IDs for them; currently mockup has static numbers
  // We'll keep the static look but update what we can
  const pending = $('#kpiPendingReviewNum');
  if (pending) pending.innerHTML = (s.bookmarked_count || 0) + ' <span style="font-size:15px; font-weight:500; color:var(--text-muted);">句</span>';

  // Build detail table
  const tbody = $('#statsTableBody');
  if (tbody) {
    tbody.innerHTML = state.papers.map(p => {
      const prog = p.progress || {};
      const pct = p.sentence_count ? Math.round(((prog.current_sentence_idx || 0) / p.sentence_count) * 100) : 0;
      return `<tr><td>${p.title}</td><td>${pct}%</td><td>${p.sentence_count || 0}</td><td>-</td></tr>`;
    }).join('');
  }
}

// ==================== Settings ====================
async function loadSettings() {
  state.settings = await apiGet('/api/settings');
  renderSettings();
}
function renderSettings() {
  const s = state.settings;
  $('#settingDefaultSpeed').value = String(s.default_playback_rate || 1.0);
  $('#settingDefaultLoop').value = String(s.default_loop_count || 2);
  $('#settingDefaultVisibility').value = s.default_transcript_visibility || 'visible';
  $('#settingAutoNext').checked = !!s.auto_play_next;
  $('#settingIgnoreCase').checked = !!s.case_sensitive_dictation;
  $('#settingIgnorePunctuation').checked = !!s.ignore_punctuation;
}

function setupSettings() {
  $('#settingsSaveBtn').addEventListener('click', saveSettings);
  $('#resetDataBtn').addEventListener('click', async () => {
    if (!confirm('确定要重置所有学习数据吗？')) return;
    await apiPost('/api/settings', { reset: true });
    location.reload();
  });
}

function saveSettings() {
  const payload = {
    default_playback_rate: parseFloat($('#settingDefaultSpeed').value),
    default_loop_count: parseInt($('#settingDefaultLoop').value),
    default_transcript_visibility: $('#settingDefaultVisibility').value,
    auto_play_next: $('#settingAutoNext').checked,
    case_sensitive_dictation: $('#settingIgnoreCase').checked,
    ignore_punctuation: $('#settingIgnorePunctuation').checked,
    theme: state.settings.theme || 'light',
  };
  apiPost('/api/settings', payload).then(() => {
    state.settings = payload;
    showToast('设置已保存');
  });
}

// ==================== Import ====================
function setupImport() {
  // Add hidden file inputs for the dropzone
  const dropzone = $('#importDropzone');
  if (!dropzone) return;

  // Create a file input for audio
  const audioInput = document.createElement('input');
  audioInput.type = 'file';
  audioInput.id = 'importAudioInput';
  audioInput.accept = 'audio/*';
  audioInput.style.display = 'none';
  dropzone.appendChild(audioInput);

  const subtitleInput = document.createElement('input');
  subtitleInput.type = 'file';
  subtitleInput.id = 'importSubtitleInput';
  subtitleInput.accept = '.srt,.lrc,.txt,.vtt';
  subtitleInput.style.display = 'none';
  dropzone.appendChild(subtitleInput);

  dropzone.addEventListener('click', () => audioInput.click());
  audioInput.addEventListener('change', () => {
    if (audioInput.files.length) {
      // After audio selected, prompt for subtitle
      subtitleInput.click();
    }
  });

  $('#openImportModalBtn').addEventListener('click', () => {
    $('#importModal').classList.add('active');
  });
  $('#closeImportModalBtn').addEventListener('click', () => {
    $('#importModal').classList.remove('active');
  });
  $('#importCancelBtn').addEventListener('click', () => {
    $('#importModal').classList.remove('active');
  });
  $('#importConfirmBtn').addEventListener('click', async () => {
    if (!audioInput.files.length) { showToast('请选择音频文件'); return; }
    const fd = new FormData();
    fd.append('audio', audioInput.files[0]);
    fd.append('paper_id', 'imported_' + Date.now());
    if (subtitleInput.files.length) {
      const text = await subtitleInput.files[0].text();
      fd.append('subtitle', text);
      const ext = subtitleInput.files[0].name.split('.').pop().toLowerCase();
      fd.append('subtitle_format', ext === 'srt' ? 'srt' : ext === 'lrc' ? 'lrc' : 'txt');
    } else {
      fd.append('subtitle', '');
      fd.append('subtitle_format', 'txt');
    }
    const r = await fetch('/api/import', { method: 'POST', body: fd });
    const data = await r.json();
    if (r.ok) {
      showToast('导入成功: ' + data.sentences_imported + ' 句');
      $('#importModal').classList.remove('active');
      state.papers = (await apiGet('/api/papers')).papers || [];
      renderLibrary();
    } else {
      showToast('导入失败: ' + (data.error || '未知错误'));
    }
  });
}

function setupModals() {
  // Close modals on overlay click
  $$('.modal-overlay').forEach(m => {
    m.addEventListener('click', e => {
      if (e.target === m) m.classList.remove('active');
    });
  });
}

// ==================== Keyboard ====================
function setupKeyboard() {
  document.addEventListener('keydown', e => {
    const tag = document.activeElement?.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT') {
      if (e.ctrlKey && e.key === 'Enter' && document.activeElement.id === 'dictationTextarea') {
        e.preventDefault();
        submitDictation();
      }
      return;
    }
    switch (e.key) {
      case ' ':
        e.preventDefault();
        togglePlay();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        prevSentence();
        saveProgress();
        break;
      case 'ArrowRight':
        e.preventDefault();
        nextSentence();
        saveProgress();
        break;
      case 'ArrowUp':
        e.preventDefault();
        state.player.playbackRate = Math.min(2.0, parseFloat((state.player.playbackRate + 0.1).toFixed(1)));
        state.player.audio.playbackRate = state.player.playbackRate;
        $('#speedSelect').value = String(state.player.playbackRate);
        break;
      case 'ArrowDown':
        e.preventDefault();
        state.player.playbackRate = Math.max(0.5, parseFloat((state.player.playbackRate - 0.1).toFixed(1)));
        state.player.audio.playbackRate = state.player.playbackRate;
        $('#speedSelect').value = String(state.player.playbackRate);
        break;
      case 'r':
      case 'R':
        replaySentence();
        break;
      case 'b':
      case 'B':
        toggleBookmarkCurrent();
        break;
      case 'Tab':
        e.preventDefault();
        cycleTranscript();
        break;
      case 'Enter':
        if (!$('#view-dictation').classList.contains('active')) {
          renderDictation();
          showView('dictation');
        }
        break;
      case 'Escape':
        if ($('#importModal').classList.contains('active')) $('#importModal').classList.remove('active');
        else if ($('#shortcutsModal').classList.contains('active')) $('#shortcutsModal').classList.remove('active');
        else showView('practice');
        break;
      case 'a':
      case 'A':
        state.player.abPointA = state.player.audio.currentTime;
        updateABMarkers();
        break;
      case 's':
      case 'S':
        state.player.abPointB = state.player.audio.currentTime;
        updateABMarkers();
        break;
    }
  });
}

// ==================== Toast ====================
function showToast(msg) {
  let toast = $('#toastContainer');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toastContainer';
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:10px 20px;background:var(--text-primary);color:var(--text-inverse);border-radius:var(--radius-md);font-size:13px;z-index:1000;opacity:0;transition:opacity 300ms;pointer-events:none;';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  setTimeout(() => { toast.style.opacity = '0'; }, 2000);
}

// ==================== Start ====================
init().catch(err => console.error('Init failed', err));