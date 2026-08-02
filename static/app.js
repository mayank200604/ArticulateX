/* ═══════════════════════════════════════════════════════════
   ArticulateX — app.js
   Complete frontend logic matching server.py exactly.
   ═══════════════════════════════════════════════════════════ */

'use strict';

/* ══════════════════════════════════════════════════════════
   STATE
   ══════════════════════════════════════════════════════════ */
const STATE = {
  // Session setup
  currentMode: 'freestyle',   // freestyle|debate1|debate2|debate3|weird
  currentLevel: 0,            // 0|1|2|3
  selectedTopic: '',
  selectedSide: '',           // for|against
  assignedSide: '',           // for level 3 (random)

  // Active session
  sessionToken: null,
  sessionTopic: '',
  sessionUserSide: '',
  sessionAiSide: '',
  sessionLevel: 0,
  sessionMode: '',
  silenceSeconds: 3.0,
  turnNumber: 0,
  lastWpm: 0,
  lastFillers: 0,
  lastHedging: 0,

  // Recording
  recordState: 'idle',        // idle|recording|processing|stopped
  mediaRecorder: null,
  audioChunks: [],
  audioContext: null,
  scriptProcessor: null,
  sourceNode: null,
  mediaStream: null,
  wsSTT: null,
  liveTranscript: '',
  submitting: false,
  interruptedByServer: false,
  wasInterrupted: false,

  // Dashboard
  dashboardData: null,
  chartFillers: null,
  chartWpm: null,
  chartModes: null,
  expandedRow: null,          // currently expanded table row index
  dashFilter: 'overview',     // overview|freestyle|debate|weird

  // Report
  reportToken: null,

  // Weird situation
  weirdSituation: null,

  // Freestyle pre-fetch: holds the /api/setup response fetched early
  // so we can show the topic before the user clicks Begin Session
  prefetchedSetup: null,
  freestyle_type: 'word',     // word|scenario (selected in setup step)

  // Unlock state
  unlockState: null,
};

/* ══════════════════════════════════════════════════════════
   UTILITY — Screen navigation
   ══════════════════════════════════════════════════════════ */
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(id);
  if (target) target.classList.add('active');

  // Show/hide global nav
  const nav = document.getElementById('global-nav');
  if (id === 'screen-landing' || id === 'screen-auth') {
    nav.classList.add('hidden');
  } else {
    nav.classList.remove('hidden');
  }

  // Update nav active link
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active-link'));
  if (id === 'screen-home') {
    document.getElementById('nav-home')?.classList.add('active-link');
  } else if (id === 'screen-dashboard') {
    document.getElementById('nav-progress')?.classList.add('active-link');
  }

  // Body class for toast positioning
  if (id === 'screen-session') {
    document.body.classList.add('session-active');
  } else {
    document.body.classList.remove('session-active');
  }

  // Session-specific: scroll conversation to bottom
  if (id === 'screen-session') {
    scrollConversationToBottom();
  }

  // Calibration report nav awareness
  if (id === 'screen-calibration-report') {
    nav.classList.remove('hidden');
  }
}

/* ══════════════════════════════════════════════════════════
   UTILITY — Toast notifications
   ══════════════════════════════════════════════════════════ */
let toastTimer = null;

function notify(msg, type = 'default') {
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toast-msg');
  if (!toast || !toastMsg) return;

  toastMsg.textContent = msg;
  toast.className = 'toast';
  if (type === 'error')   toast.classList.add('toast-error');
  if (type === 'success') toast.classList.add('toast-success');
  toast.classList.add('toast-show');

  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('toast-show');
  }, 3500);
}

/* ══════════════════════════════════════════════════════════
   UTILITY — Count-up animation
   ══════════════════════════════════════════════════════════ */
function animateCountUp(el, target, duration = 600, decimals = 0) {
  if (!el) return;
  const start = performance.now();
  const startVal = 0;
  const targetNum = parseFloat(target) || 0;

  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = startVal + (targetNum - startVal) * eased;
    el.textContent = decimals > 0 ? current.toFixed(decimals) : Math.round(current).toString();
    if (progress < 1) requestAnimationFrame(step);
  }

  requestAnimationFrame(step);
}

/* ══════════════════════════════════════════════════════════
   UTILITY — Set button loading state
   ══════════════════════════════════════════════════════════ */
function setLoading(el, loading) {
  if (!el) return;
  if (loading) {
    el.classList.add('loading-pulse');
    el.disabled = true;
  } else {
    el.classList.remove('loading-pulse');
    el.disabled = false;
  }
}

/* ══════════════════════════════════════════════════════════
   VOICE CIRCLE — Reusable animated rings
   ══════════════════════════════════════════════════════════ */
function initVoiceCircle(containerId, size = 200) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  container.style.width  = size + 'px';
  container.style.height = size + 'px';

  // Add echoing wave ripple effects
  for (let j = 0; j < 2; j++) {
    const wave = document.createElement('div');
    wave.classList.add('vc-wave');
    wave.style.animationDelay = `${j * 1.5}s`;
    container.appendChild(wave);
  }

  // Radii for concentric rings (fraction of size/2)
  const ringFractions = [0.75, 0.88, 0.96, 1.0];
  const speeds = [18, 24, 30, 22]; // rotation seconds

  ringFractions.forEach((frac, i) => {
    const ring = document.createElement('div');
    ring.classList.add('vc-ring');
    const diameter = Math.round(size * frac);
    ring.style.width  = diameter + 'px';
    ring.style.height = diameter + 'px';
    ring.style.opacity = String(0.08 + i * 0.04);
    ring.style.animation = `
      vcRingFadeIn 0.6s var(--ease-enter) ${i * 0.12}s forwards,
      vcRingSpin${i} ${speeds[i]}s linear infinite ${i * 0.12}s
    `;

    // Inject keyframes for each ring's unique rotation direction
    const dir = i % 2 === 0 ? '360deg' : '-360deg';
    const styleId = `vc-keyframe-${i}`;
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style');
      style.id = styleId;
      style.textContent = `
        @keyframes vcRingSpin${i} {
          from { transform: rotate(0deg); }
          to   { transform: rotate(${dir}); }
        }
      `;
      document.head.appendChild(style);
    }

    container.appendChild(ring);
  });

  // Center dot
  const dot = document.createElement('div');
  dot.classList.add('vc-center-dot');
  container.appendChild(dot);
}

/* ══════════════════════════════════════════════════════════
   API — Dashboard
   ══════════════════════════════════════════════════════════ */
async function fetchDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    if (!res.ok) throw new Error('Dashboard fetch failed');
    const data = await res.json();
    STATE.dashboardData = data;
    return data;
  } catch (e) {
    console.error('[Dashboard]', e);
    return null;
  }
}

/* ══════════════════════════════════════════════════════════
   API — Topics for Level 1
   ══════════════════════════════════════════════════════════ */
async function fetchTopics(level = 1) {
  try {
    const res = await fetch(`/api/topics?level=${level}`);
    if (!res.ok) throw new Error('Topics fetch failed');
    const data = await res.json();
    return data.topics || [];
  } catch (e) {
    console.error('[Topics]', e);
    return [];
  }
}

/* ══════════════════════════════════════════════════════════
   API — Weird situation
   ══════════════════════════════════════════════════════════ */
async function fetchWeirdSituation() {
  try {
    const res = await fetch('/api/weird-situation');
    if (!res.ok) throw new Error('Weird situation fetch failed');
    return await res.json();
  } catch (e) {
    console.error('[Weird]', e);
    return null;
  }
}

/* ════════════════════════════════════════════════════════
   API — Unlock state
   ════════════════════════════════════════════════════════ */
async function fetchUnlockState() {
  try {
    const res = await fetch('/api/unlock-state');
    if (!res.ok) throw new Error('Unlock state fetch failed');
    const data = await res.json();
    STATE.unlockState = data;
    return data;
  } catch (e) {
    console.error('[UnlockState]', e);
    return null;
  }
}

/* ════════════════════════════════════════════════════════
   API — Calibration report
   ════════════════════════════════════════════════════════ */
async function fetchCalibrationReport() {
  const res = await fetch('/api/calibration-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: STATE.sessionToken }),
  });
  if (!res.ok) throw new Error('Calibration report failed');
  return await res.json();
}

/* ══════════════════════════════════════════════════════════
   API — Begin session (POST /api/setup)
   ══════════════════════════════════════════════════════════ */
async function beginSession() {
  const body = {
    mode: STATE.currentMode,
    level: STATE.currentLevel,
    topic: STATE.selectedTopic,
    user_side: STATE.selectedSide || STATE.assignedSide,
    freestyle_type: STATE.currentMode === 'freestyle' ? 'word' : '',
  };

  const res = await fetch('/api/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(`Setup failed: ${res.status}`);
  return await res.json();
}

/* ══════════════════════════════════════════════════════════
   API — Submit turn (POST /api/turn)
   ══════════════════════════════════════════════════════════ */
async function submitTurnToServer(audioBlob) {
  const buf = await audioBlob.arrayBuffer();
  const b64 = arrayBufferToBase64(buf);

  const res = await fetch('/api/turn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_token: STATE.sessionToken,
      audio_b64: b64,
      sample_rate: 16000,
      streaming_transcript: STATE.liveTranscript || '',
    }),
  });

  if (!res.ok) throw new Error(`Turn submit failed: ${res.status}`);
  return await res.json();
}

/* ══════════════════════════════════════════════════════════
   API — Get feedback (POST /api/feedback)
   ══════════════════════════════════════════════════════════ */
async function getFeedbackFromServer() {
  const res = await fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: STATE.sessionToken }),
  });
  if (!res.ok) throw new Error(`Feedback failed: ${res.status}`);
  return await res.json();
}

/* ══════════════════════════════════════════════════════════
   API — Play summary (POST /api/play-summary)
   ══════════════════════════════════════════════════════════ */
async function playSummary() {
  const res = await fetch('/api/play-summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: STATE.reportToken || STATE.sessionToken }),
  });
  if (!res.ok) return;
  const data = await res.json();
  if (data.audio_ready) playTTSAudio();
}

/* ══════════════════════════════════════════════════════════
   API — Play full report (POST /api/play-report)
   ══════════════════════════════════════════════════════════ */
async function playFullReport() {
  const res = await fetch('/api/play-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: STATE.reportToken || STATE.sessionToken }),
  });
  if (!res.ok) return;
  const data = await res.json();
  if (data.audio_ready) playTTSAudio();
}

/* ══════════════════════════════════════════════════════════
   AUDIO — Play TTS from /audio/response
   ══════════════════════════════════════════════════════════ */
function playTTSAudio() {
  return new Promise((resolve) => {
    const audio = document.getElementById('tts-audio');
    if (!audio) return resolve();
    
    audio.src = '/audio/response?t=' + Date.now();
    audio.load();
    
    // Resolve when audio finishes naturally or errors
    audio.onended = () => resolve();
    audio.onerror = () => resolve();
    
    audio.play().catch(err => {
      console.warn('[TTS] Autoplay blocked:', err);
      resolve();
    });
  });
}

/* ══════════════════════════════════════════════════════════
   UTILITY — ArrayBuffer to base64
   ══════════════════════════════════════════════════════════ */
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunkSize = 8192;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

/* ══════════════════════════════════════════════════════════
   RECORDING — WebSocket STT streaming
   ══════════════════════════════════════════════════════════ */
function openSTTSocket() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const tokenParam = STATE.sessionToken ? `?session_token=${encodeURIComponent(STATE.sessionToken)}` : '';
  const ws = new WebSocket(`${protocol}://${location.host}/ws/stt${tokenParam}`);
  STATE.wsSTT = ws;

  ws.onopen = () => console.log('[WS-STT] Connected');

  ws.onmessage = (ev) => {
    const ts = Date.now();
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type !== 'partial' && msg.type !== 'final') {
        console.log(`[WS-INT-DEBUG] ${ts} — onmessage received type: ${msg.type}`);
      }
      if (msg.type === 'ready') {
        console.log('[WS-STT] Streaming ready');
      } else if (msg.type === 'fallback') {
        console.log('[WS-STT] Fallback mode (batch STT)');
      } else if (msg.type === 'partial') {
        STATE.liveTranscript = msg.text || '';
        updateTranscriptBar(STATE.liveTranscript);
      } else if (msg.type === 'final') {
        STATE.liveTranscript = msg.text || '';
        updateTranscriptBar(STATE.liveTranscript);
      } else if (msg.type === 'interrupt_start') {
        STATE.wasInterrupted = true;
        console.log(`[WS-INT-DEBUG] ${Date.now()} — interrupt_start parsed and wasInterrupted flag set true`);
        console.log('[WS-STT] ⚡ SERVER INTERRUPT START:', msg.rule);
        handleServerInterruptStart(msg);
      } else if (msg.type === 'interrupt') {
        console.log('[WS-STT] ⚡ SERVER INTERRUPT FINAL');
        handleServerInterruptFinal(msg);
      }
    } catch (e) {
      console.warn('[WS-STT] Bad message:', ev.data);
    }
  };

  ws.onerror = (e) => console.error('[WS-STT] Error:', e);
  ws.onclose = () => console.log('[WS-STT] Closed');
}

function closeSTTSocket() {
  if (STATE.wsSTT) {
    try {
      if (STATE.wsSTT.readyState === WebSocket.OPEN) {
        STATE.wsSTT.send(JSON.stringify({ action: 'stop' }));
      }
    } catch (e) {}
    STATE.wsSTT = null;
  }
}

/* ══════════════════════════════════════════════════════════
   INTERRUPT — Handle server-side mid-speech interrupt
   ══════════════════════════════════════════════════════════ */
async function handleServerInterruptStart(msg) {
  console.log(`[WS-INT-DEBUG] ${Date.now()} — handleServerInterruptStart begins`);
  // Set flag IMMEDIATELY so nothing else tries to submit
  STATE.interruptedByServer = true;

  // Kill recording pipeline — mic, MediaRecorder, AudioContext
  // Don't use stopRecording() because it sends WS stop action
  // which is redundant
  if (STATE.scriptProcessor) {
    STATE.scriptProcessor.disconnect();
    STATE.scriptProcessor = null;
  }
  if (STATE.sourceNode) {
    STATE.sourceNode.disconnect();
    STATE.sourceNode = null;
  }
  if (STATE.audioContext) {
    try { await STATE.audioContext.close(); } catch (_) {}
    STATE.audioContext = null;
  }
  if (STATE.mediaRecorder && STATE.mediaRecorder.state !== 'inactive') {
    try { 
      console.log(`[WS-INT-DEBUG] ${Date.now()} — Calling MediaRecorder.stop()`);
      STATE.mediaRecorder.stop(); 
    } catch (_) {}
  }
  if (STATE.mediaStream) {
    STATE.mediaStream.getTracks().forEach(t => t.stop());
    STATE.mediaStream = null;
  }

  // Discard all buffered audio — prevents any /api/turn submission
  console.log(`[WS-INT-DEBUG] ${Date.now()} — Clearing STATE.audioChunks`);
  STATE.audioChunks = [];

  // Set UI to processing immediately
  setRecordState('processing');

  // Notify user
  const ruleLabels = {
    word_overload:      'RAMBLING DETECTED',
    filler_overload:    'FILLER OVERLOAD',
    claim_no_evidence:  'UNSUPPORTED CLAIM',
  };
  notify(`⚡ ${ruleLabels[msg.rule] || 'INTERRUPTED'} — AI is cutting in`, 'error');
}

async function handleServerInterruptFinal(msg) {
  STATE.wsSTT = null;

  // Update turn counter and metrics
  STATE.turnNumber  = msg.turn_number;
  STATE.lastWpm     = msg.wpm;
  STATE.lastFillers = msg.fillers;
  STATE.lastHedging = msg.confidence_signals;
  updateTurnCounter(msg.turn_number);
  updateMetrics(msg.wpm, msg.fillers, msg.confidence_signals);

  // Add user bubble with partial transcript
  if (msg.transcript) {
    const userBubble = buildUserBubble(
      msg.transcript, msg.wpm, msg.fillers, msg.turn_number
    );
    appendToChat(userBubble);
  }

  // Add AI interrupt bubble
  if (msg.ai_response) {
    const aiBubble = buildAIBubble(msg.ai_response, true);
    appendToChat(aiBubble);
  }

  // Play TTS
  if (msg.audio_ready) {
    playTTSAudio();
  }

  // Clear empty state
  const emptyState = document.getElementById('session-empty-state');
  if (emptyState) emptyState.style.display = 'none';

  // Reset recording state so user can speak again
  STATE.recordState = 'idle';
  STATE.submitting = false;
  STATE.liveTranscript = '';
  STATE.interruptedByServer = false;
  setRecordState('idle');
  updateTranscriptBar('', false);
}

function sendPCMChunk(float32Array) {
  if (!STATE.wsSTT || STATE.wsSTT.readyState !== WebSocket.OPEN) return;
  // Convert Float32 → Int16
  const int16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    int16[i] = Math.max(-32768, Math.min(32767, Math.round(float32Array[i] * 32768)));
  }
  STATE.wsSTT.send(int16.buffer);
}

/* ══════════════════════════════════════════════════════════
   RECORDING — Start / Stop
   ══════════════════════════════════════════════════════════ */
async function startRecording() {
  if (STATE.recordState === 'recording') return;

  try {
    STATE.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (err) {
    notify('Microphone access denied. Please allow microphone.', 'error');
    return;
  }

  // Reset state
  STATE.audioChunks = [];
  STATE.liveTranscript = '';
  STATE.recordState = 'recording';
  STATE.wasInterrupted = false;

  // Open STT WebSocket
  openSTTSocket();

  // MediaRecorder for capturing chunks to send to /api/turn
  STATE.mediaRecorder = new MediaRecorder(STATE.mediaStream);
  STATE.mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) {
      STATE.audioChunks.push(e.data);
    }
  };
  STATE.mediaRecorder.start(250);

  // AudioContext for real-time PCM streaming to WebSocket
  STATE.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
  STATE.sourceNode = STATE.audioContext.createMediaStreamSource(STATE.mediaStream);
  STATE.scriptProcessor = STATE.audioContext.createScriptProcessor(2048, 1, 1);
  
  let lastActiveTime = Date.now();
  let hasSpoken = false;

  STATE.scriptProcessor.onaudioprocess = (e) => {
    const inputData = e.inputBuffer.getChannelData(0);
    sendPCMChunk(inputData);

    // Silence detection
    if (STATE.silenceSeconds && STATE.silenceSeconds > 0) {
      let sum = 0;
      for (let i = 0; i < inputData.length; i++) {
        sum += inputData[i] * inputData[i];
      }
      const rms = Math.sqrt(sum / inputData.length);

      const threshold = 0.008; // slightly sensitive threshold for speech detection
      const now = Date.now();

      if (rms >= threshold) {
        lastActiveTime = now;
        hasSpoken = true;
      } else {
        const silentDuration = (now - lastActiveTime) / 1000;
        // Auto-submit after specified silence duration if the user has spoken,
        // or after a longer grace period if they haven't spoken yet (e.g. 10s)
        const maxGracePeriod = Math.max(10.0, STATE.silenceSeconds * 2.5);
        if ((hasSpoken && silentDuration >= STATE.silenceSeconds) || (!hasSpoken && silentDuration >= maxGracePeriod)) {
          if (STATE.recordState === 'recording' && !STATE.submitting && !STATE.interruptedByServer) {
            console.log(`[Silence Detector] Silence detected for ${silentDuration.toFixed(1)}s. Auto-submitting...`);
            notify('Silence detected — auto-submitting...', 'default');
            stopRecording().then(() => {
              handleSubmitTurn();
            });
          }
        }
      }
    }
  };
  STATE.sourceNode.connect(STATE.scriptProcessor);
  STATE.scriptProcessor.connect(STATE.audioContext.destination);

  // Update UI
  setRecordState('recording');
  updateTranscriptBar('', true);

  // Clear empty state
  const emptyState = document.getElementById('session-empty-state');
  if (emptyState) emptyState.style.display = 'none';
}

async function stopRecording() {
  if (STATE.recordState !== 'recording') return;
  STATE.recordState = 'processing';
  setRecordState('processing');

  // Stop AudioContext pipeline
  if (STATE.scriptProcessor) {
    STATE.scriptProcessor.disconnect();
    STATE.scriptProcessor = null;
  }
  if (STATE.sourceNode) {
    STATE.sourceNode.disconnect();
    STATE.sourceNode = null;
  }
  if (STATE.audioContext) {
    await STATE.audioContext.close();
    STATE.audioContext = null;
  }

  // Stop WebSocket (send stop action)
  closeSTTSocket();

  // Stop MediaRecorder
  return new Promise((resolve) => {
    STATE.mediaRecorder.onstop = resolve;
    STATE.mediaRecorder.stop();
    STATE.mediaStream?.getTracks().forEach(t => t.stop());
  }).then(() => {
    setRecordState('stopped');
    updateTranscriptBar(STATE.liveTranscript, false);
    STATE.recordState = 'stopped';
  });
}

/* ══════════════════════════════════════════════════════════
   UI — Record button state
   ══════════════════════════════════════════════════════════ */
function setRecordState(state) {
  const wrap = document.querySelector('.record-button-wrap');
  const status = document.getElementById('rec-status');

  if (!wrap) return;

  wrap.classList.remove('recording', 'processing', 'stopped');
  if (state !== 'idle') wrap.classList.add(state);

  // Propagate state to voice circles so they animate reactively
  document.querySelectorAll('.voice-circle-container').forEach(vc => {
    vc.classList.remove('recording', 'processing', 'stopped', 'idle');
    vc.classList.add(state);
  });

  const statusMap = {
    idle:       'PRESS TO RECORD',
    recording:  'RECORDING',
    processing: 'PROCESSING',
    stopped:    'SUBMIT YOUR TURN',
  };
  if (status) status.textContent = statusMap[state] || '';
}

/* ══════════════════════════════════════════════════════════
   UI — Live transcript bar
   ══════════════════════════════════════════════════════════ */
function updateTranscriptBar(text, active) {
  const bar    = document.getElementById('transcript-bar');
  const span   = document.getElementById('transcript-text');
  const cursor = document.getElementById('transcript-cursor');
  if (!bar || !span) return;

  if (!text && active !== true) {
    span.textContent = 'Your words will appear here as you speak...';
    span.classList.add('placeholder');
    cursor?.classList.add('hidden');
    bar.classList.remove('active');
    return;
  }

  span.textContent = text || '';
  span.classList.remove('placeholder');
  bar.classList.add('active');

  if (active === true) {
    cursor?.classList.remove('hidden');
  } else {
    cursor?.classList.add('hidden');
    bar.classList.remove('active');
  }
}

/* ══════════════════════════════════════════════════════════
   UI — Turn counter animation
   ══════════════════════════════════════════════════════════ */
function updateTurnCounter(n) {
  const el = document.getElementById('turn-counter');
  if (!el) return;
  el.style.transform = 'translateY(-4px)';
  el.style.opacity   = '0';
  setTimeout(() => {
    el.textContent   = n;
    el.style.transition = 'all 0.2s var(--ease-enter)';
    el.style.transform = 'translateY(0)';
    el.style.opacity   = '1';
  }, 120);
}

/* ══════════════════════════════════════════════════════════
   UI — Update session metrics
   ══════════════════════════════════════════════════════════ */
function updateMetrics(wpm, fillers, hedging) {
  const wpmEl   = document.getElementById('metric-wpm');
  const filEl   = document.getElementById('metric-fillers');
  const hedEl   = document.getElementById('metric-hedging');

  function countUpMetric(el, val) {
    if (!el) return;
    const from = parseInt(el.textContent) || 0;
    const to   = val;
    const steps = 10;
    let i = 0;
    const diff = to - from;
    const interval = setInterval(() => {
      i++;
      el.textContent = Math.round(from + diff * (i / steps));
      if (i >= steps) {
        clearInterval(interval);
        el.textContent = to;
      }
    }, 20);
  }

  countUpMetric(wpmEl, Math.round(wpm));
  countUpMetric(filEl, Math.round(fillers));
  countUpMetric(hedEl, Math.round(hedging));
}

/* ══════════════════════════════════════════════════════════
   UI — Build chat bubble (user turn)
   ══════════════════════════════════════════════════════════ */
function buildUserBubble(transcript, wpm, fillers, turnNum) {
  const turn = document.createElement('div');
  turn.classList.add('chat-turn', 'user-turn');

  const bubble = document.createElement('div');
  bubble.classList.add('chat-bubble');
  bubble.textContent = transcript;

  // Metric chips
  const chips = document.createElement('div');
  chips.classList.add('bubble-metrics');

  const wpmChip = document.createElement('span');
  wpmChip.classList.add('metric-chip');
  if (wpm > 185) wpmChip.classList.add('chip-warn-wpm');
  wpmChip.textContent = `${Math.round(wpm)} wpm`;

  const filChip = document.createElement('span');
  filChip.classList.add('metric-chip');
  if (fillers > 4) filChip.classList.add('chip-warn-fillers');
  filChip.textContent = `${fillers} filler${fillers !== 1 ? 's' : ''}`;

  const turnChip = document.createElement('span');
  turnChip.classList.add('metric-chip');
  turnChip.textContent = `turn ${turnNum}`;

  chips.appendChild(wpmChip);
  chips.appendChild(filChip);
  chips.appendChild(turnChip);

  turn.appendChild(bubble);
  turn.appendChild(chips);
  return turn;
}

/* ══════════════════════════════════════════════════════════
   UI — Build chat bubble (AI turn)
   ══════════════════════════════════════════════════════════ */
function buildAIBubble(text, isInterrupt) {
  const turn = document.createElement('div');
  turn.classList.add('chat-turn', 'ai-turn');

  if (isInterrupt) {
    const pill = document.createElement('span');
    pill.classList.add('interrupt-pill');
    pill.textContent = 'INTERRUPT';
    turn.appendChild(pill);
  }

  const marker = document.createElement('div');
  marker.classList.add('ai-marker');
  marker.textContent = 'AX';

  const bubble = document.createElement('div');
  bubble.classList.add('chat-bubble');
  bubble.textContent = text;

  turn.appendChild(marker);
  turn.appendChild(bubble);
  return turn;
}

/* ══════════════════════════════════════════════════════════
   UI — Append to conversation
   ══════════════════════════════════════════════════════════ */
function appendToChat(el) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.appendChild(el);
  scrollConversationToBottom();
}

function scrollConversationToBottom() {
  const conv = document.getElementById('session-conversation');
  if (conv) {
    setTimeout(() => {
      conv.scrollTop = conv.scrollHeight;
    }, 50);
  }
}

/* ══════════════════════════════════════════════════════════
   EVENT — Record button toggle
   ══════════════════════════════════════════════════════════ */
async function toggleRecord() {
  if (STATE.recordState === 'idle') {
    await startRecording();
  } else if (STATE.recordState === 'recording') {
    await stopRecording();
  } else if (STATE.recordState === 'stopped') {
    // Reset to idle — allow re-recording
    STATE.audioChunks = [];
    STATE.liveTranscript = '';
    STATE.recordState = 'idle';
    setRecordState('idle');
    updateTranscriptBar('', false);
  }
}

/* ══════════════════════════════════════════════════════════
   EVENT — Submit Turn
   ══════════════════════════════════════════════════════════ */
async function handleSubmitTurn() {
  console.log(`[WS-INT-DEBUG] ${Date.now()} — handleSubmitTurn called`);
  if (STATE.submitting) return;
  if (STATE.interruptedByServer) {
    console.log('[Turn] Blocked — server interrupt already handled this turn');
    return;
  }
  if (STATE.audioChunks.length === 0) {
    notify('Record something first!', 'error');
    return;
  }

  // If still recording, stop first
  if (STATE.recordState === 'recording') {
    await stopRecording();
  }

  STATE.submitting = true;
  setRecordState('processing');

  const blob = new Blob(STATE.audioChunks, { type: 'audio/webm' });

  try {
    const data = await submitTurnToServer(blob);

    if (data.error) {
      notify(data.error, 'error');
      resetAfterTurn();
      return;
    }

    // Update state
    STATE.turnNumber    = data.turn_number;
    STATE.lastWpm       = data.wpm;
    STATE.lastFillers   = data.fillers;
    STATE.lastHedging   = data.confidence_signals;

    // Update UI — turn counter
    updateTurnCounter(data.turn_number);

    // Update metrics
    updateMetrics(data.wpm, data.fillers, data.confidence_signals);

    // Enforce frontend interrupt tracking
    console.log(`[WS-INT-DEBUG] ${Date.now()} — Evaluating guard check: STATE.wasInterrupted = ${STATE.wasInterrupted}, data.is_interrupt = ${data.is_interrupt}`);
    const isReallyInterrupt = STATE.wasInterrupted && data.is_interrupt;

    // Add user bubble
    const userBubble = buildUserBubble(
      data.transcript,
      data.wpm,
      data.fillers,
      data.turn_number
    );
    appendToChat(userBubble);

    // Add AI bubble
    if (data.ai_response) {
      const aiBubble = buildAIBubble(data.ai_response, isReallyInterrupt);
      appendToChat(aiBubble);
    }

    // Play TTS audio
    let ttsPromise = Promise.resolve();
    if (data.audio_ready) {
      ttsPromise = playTTSAudio();
    }

    // Reset recording state
    resetAfterTurn();

    // Calibration auto-complete check
    if (data.calibration_complete) {
      notify('Calibration complete! Generating your baseline...', 'success');
      
      // Wait for AI to finish speaking
      await ttsPromise;
      
      try {
        const calData = await fetchCalibrationReport();
        buildCalibrationReport(calData);
        showScreen('screen-calibration-report');
      } catch (err) {
        console.error('[Calibration Report]', err);
        notify('Could not generate calibration report.', 'error');
      }
    }

  } catch (err) {
    console.error('[Turn]', err);
    notify('Something went wrong. Try again.', 'error');
    resetAfterTurn();
  }
}

function resetAfterTurn() {
  STATE.submitting          = false;
  STATE.interruptedByServer = false;
  STATE.audioChunks         = [];
  STATE.liveTranscript      = '';
  STATE.recordState         = 'idle';
  setRecordState('idle');
  updateTranscriptBar('', false);
}

/* ══════════════════════════════════════════════════════════
   EVENT — Get Feedback
   ══════════════════════════════════════════════════════════ */
async function handleGetFeedback() {
  if (STATE.turnNumber === 0) {
    notify('Complete at least one turn first.', 'error');
    return;
  }

  const btn = document.getElementById('btn-get-feedback');
  setLoading(btn, true);
  notify('Generating your feedback…');

  try {
    const data = await getFeedbackFromServer();

    if (data.error) {
      notify(data.error, 'error');
      setLoading(btn, false);
      return;
    }

    STATE.reportToken = STATE.sessionToken;
    buildReport(data);
    showScreen('screen-report');

  } catch (err) {
    console.error('[Feedback]', err);
    notify('Could not generate feedback.', 'error');
  }

  setLoading(btn, false);
}

/* ══════════════════════════════════════════════════════════
   UI — Build report sections from feedback data
   ══════════════════════════════════════════════════════════ */
function buildReport(data) {
  // Top strip
  const modeDisplay = {
    freestyle: 'FreeStyle',
    debate1:   'Debate · Easy',
    debate2:   'Debate · Medium',
    debate3:   'Debate · Hard',
    weird:     'Weird Situation',
  };

  setText('rstrip-mode',  modeDisplay[data.mode] || data.mode);
  setText('rstrip-topic', data.topic || '');
  setText('rstrip-turns', `${data.total_turns} TURNS`);
  setText('rstrip-wpm',   `AVG ${data.avg_wpm} WPM`);

  // Sidebar metrics
  setText('rsm-turns',   data.total_turns);
  setText('rsm-wpm',     data.avg_wpm);
  setText('rsm-fillers', data.total_fillers);
  setText('rsm-hedging', data.total_confidence_signals);

  // Parse the full_report text into sections
  parseAndRenderReport(data.full_report, data);

  // Hedge dots
  buildHedgeDots(data.total_confidence_signals, data.total_turns);

  // Stagger cards in
  scheduleCardReveals();

  // Next session recommendation
  const recCard = document.getElementById('rcard-recommendation');
  const recText = document.getElementById('r-recommendation');
  if (data.next_recommendation && recCard && recText) {
    recText.textContent = data.next_recommendation;
    recCard.classList.remove('hidden');
  } else if (recCard) {
    recCard.classList.add('hidden');
  }

  // Before and After Audio Milestone
  const milestoneCard = document.getElementById('rcard-milestone');
  const btnPlayBefore = document.getElementById('btn-play-before');
  const btnPlayAfter = document.getElementById('btn-play-after');
  
  if (data.milestone_playback && milestoneCard && btnPlayBefore && btnPlayAfter) {
    milestoneCard.classList.remove('hidden');
    
    // Cleanup any existing audio instances
    if (window._milestoneAudioBefore) { window._milestoneAudioBefore.pause(); window._milestoneAudioBefore = null; }
    if (window._milestoneAudioAfter) { window._milestoneAudioAfter.pause(); window._milestoneAudioAfter = null; }
    
    // Reset button states
    btnPlayBefore.textContent = '▶ Play Before';
    btnPlayBefore.classList.remove('playing');
    btnPlayAfter.textContent = '▶ Play After';
    btnPlayAfter.classList.remove('playing');
    
    // Set up audio objects
    window._milestoneAudioBefore = new Audio(data.milestone_playback.before_url);
    window._milestoneAudioAfter = new Audio(data.milestone_playback.after_url);
    
    // Shared playback toggle logic
    const setupAudioButton = (btn, audioObj, otherBtn, otherAudio) => {
      btn.onclick = () => {
        if (otherAudio && !otherAudio.paused) {
          otherAudio.pause();
          otherAudio.currentTime = 0;
          otherBtn.textContent = otherBtn.textContent.replace('⏸ Pause', '▶ Play');
          otherBtn.classList.remove('playing');
        }
        
        if (audioObj.paused) {
          audioObj.play();
          btn.textContent = btn.textContent.replace('▶ Play', '⏸ Pause');
          btn.classList.add('playing');
        } else {
          audioObj.pause();
          btn.textContent = btn.textContent.replace('⏸ Pause', '▶ Play');
          btn.classList.remove('playing');
        }
      };
      
      audioObj.onended = () => {
        btn.textContent = btn.textContent.replace('⏸ Pause', '▶ Play');
        btn.classList.remove('playing');
      };
    };
    
    setupAudioButton(btnPlayBefore, window._milestoneAudioBefore, btnPlayAfter, window._milestoneAudioAfter);
    setupAudioButton(btnPlayAfter, window._milestoneAudioAfter, btnPlayBefore, window._milestoneAudioBefore);
    
  } else if (milestoneCard) {
    milestoneCard.classList.add('hidden');
    if (window._milestoneAudioBefore) { window._milestoneAudioBefore.pause(); window._milestoneAudioBefore = null; }
    if (window._milestoneAudioAfter) { window._milestoneAudioAfter.pause(); window._milestoneAudioAfter = null; }
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(val ?? '');
}

/* ══════════════════════════════════════════════════════════
   UI — Parse report text into sections
   ══════════════════════════════════════════════════════════ */
function parseAndRenderReport(fullReport, data) {
  if (!fullReport) {
    // Fallback minimal display
    setInnerText('r-verdict',    'Report generated. Review your metrics.');
    setInnerText('r-worked',     'See your turn metrics above for details.');
    setInnerText('r-problem',    '—');
    setInnerText('r-pattern',    '—');
    setInnerText('r-confidence', '—');
    setInnerText('r-encourage',  'Keep practising.');
    buildFixes([]);
    return;
  }

  // Split by numbered section headings or common headers
  const sections = extractSections(fullReport);

  setInnerText('r-verdict',    sections.verdict    || extractFirstLine(fullReport));
  setInnerText('r-worked',     sections.worked     || '—');
  setInnerText('r-problem',    sections.problem    || '—');
  setInnerText('r-pattern',    sections.pattern    || '—');
  setInnerText('r-confidence', sections.confidence || '—');
  setInnerText('r-encourage',  sections.encourage  || '');
  // Hide encouragement card entirely when LLM omitted the section
  const encourageCard = document.getElementById('rcard-encourage');
  if (encourageCard) {
    if (sections.encourage && sections.encourage.trim()) {
      encourageCard.classList.remove('hidden');
    } else {
      encourageCard.classList.add('hidden');
    }
  }
  buildFixes(sections.fixes || []);
}

function setInnerText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(val ?? '');
}

function extractFirstLine(text) {
  return (text || '').split('\n').find(l => l.trim().length > 10) || '';
}

/**
 * Attempt to extract named sections from the LLM report.
 * The report format is free-form text, so we use heuristic matching.
 */
function extractSections(text) {
  const result = {
    verdict:    '',
    worked:     '',
    problem:    '',
    pattern:    '',
    confidence: '',
    encourage:  '',
    fixes:      [],
    fixesRaw:   '',
  };

  if (!text) return result;

  // Normalize line endings
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  let current = null;
  let buffer  = [];

  const flush = () => {
    if (!current) return;
    const content = buffer.join('\n').trim();
    if (current === 'verdict')      result.verdict    = content;
    if (current === 'worked')       result.worked     = content;
    if (current === 'problem')      result.problem    = content;
    if (current === 'pattern')      result.pattern    = content;
    if (current === 'confidence')   result.confidence = content;
    if (current === 'encourage')    result.encourage  = content;
    if (current === 'fixes_header') result.fixesRaw   = content;
    buffer = [];
  };

  // Robust header matching: collapse multiple whitespace before comparison
  // to handle LLM output with irregular spacing
  const matchHeader = (line, patterns) => {
    const normalized = line.toLowerCase().replace(/\s+/g, ' ').replace(/[*#_]/g, '');
    return patterns.some(p => normalized.includes(p));
  };

  for (const line of lines) {
    const l = line.trim();
    if (!l) { buffer.push(''); continue; }

    if (matchHeader(l, ['overall verdict'])) {
      flush(); current = 'verdict';
    } else if (matchHeader(l, ['what worked'])) {
      flush(); current = 'worked';
    } else if (matchHeader(l, ['the main problem'])) {
      flush(); current = 'problem';
    } else if (matchHeader(l, ['the pattern'])) {
      flush(); current = 'pattern';
    } else if (matchHeader(l, ['confidence report'])) {
      flush(); current = 'confidence';
    } else if (matchHeader(l, ['earned encouragement'])) {
      flush(); current = 'encourage';
    } else if (matchHeader(l, ['things to fix'])) {
      flush(); current = 'fixes_header';
    } else if (matchHeader(l, ['spoken summary'])) {
      flush(); current = null; // skip
    } else {
      if (current !== null) {
        buffer.push(l);
      }
    }
  }
  flush();

  // Section-header keywords used to detect bleed-through in fix items
  const sectionHeaderKeywords = [
    'earned encouragement', 'spoken summary', 'overall verdict',
    'what worked', 'the main problem', 'confidence report',
  ];

  // Extract 3 fix items from the fixes section only (not full report)
  const fixSource = result.fixesRaw || '';
  if (fixSource) {
    const parseFixBlock = (blockText, index) => {
      const match = blockText.match(/\b(REASON|EXAMPLE|TRY THIS( INSTEAD)?):/i);
      let tStr = '';
      let bStr = '';
      if (match && match.index > 0) {
        tStr = blockText.substring(0, match.index).trim();
        bStr = blockText.substring(match.index).trim();
      } else {
        const lines = blockText.trim().split('\n');
        tStr = lines[0];
        bStr = lines.slice(1).join('\n').trim();
      }
      const title = tStr.replace(/^(?:POINT|[1-3][.)\s:])+\s*/i, '').replace(/^[•\-*\d.)\s]+/, '').trim() || `Point ${index+1}`;
      return { title, body: bStr };
    };

    // Try structured POINT/REASON/EXAMPLE/TRY THIS parsing first
    const pointBlocks = fixSource.split(/(?=(?:^|\n)\s*(?:POINT|[1-3][.)]))/).filter(Boolean);
    if (pointBlocks.length >= 2) {
      result.fixes = pointBlocks.slice(0, 3).map((block, i) => parseFixBlock(block, i));
    } else {
      // Fallback: split by double-newlines
      const chunks = fixSource.split(/\n\n+/).filter(Boolean).slice(0, 3);
      result.fixes = chunks.map((c, i) => parseFixBlock(c, i));
    }

    // Filter out any fix items that are actually bled section headers
    result.fixes = result.fixes.filter(fix => {
      const titleLower = fix.title.toLowerCase().replace(/\s+/g, ' ');
      return !sectionHeaderKeywords.some(kw => titleLower.includes(kw));
    });
  }

  // Filter encouragement placeholder text — LLM sometimes still outputs it
  if (result.encourage) {
    const encLower = result.encourage.toLowerCase().trim();
    const placeholders = [
      'no standout moment',
      'nothing stood out',
      'no earned encouragement',
      'no genuinely earned',
      'nothing genuinely stood out',
    ];
    if (placeholders.some(p => encLower.includes(p))) {
      result.encourage = '';
    }
  }

  // If verdict is empty, use first meaningful paragraph
  if (!result.verdict) {
    result.verdict = extractFirstLine(text);
  }

  return result;
}

/* ══════════════════════════════════════════════════════════
   UI — Build fix expandable cards
   ══════════════════════════════════════════════════════════ */
function buildFixes(fixes) {
  const container = document.getElementById('r-fixes');
  if (!container) return;
  container.innerHTML = '';

  if (!fixes || fixes.length === 0) {
    const p = document.createElement('p');
    p.style.cssText = 'font-family:Jost,sans-serif;font-size:13px;color:var(--text-3);font-style:italic;';
    p.textContent = 'No specific fixes identified.';
    container.appendChild(p);
    return;
  }

  fixes.forEach((fix, i) => {
    const item = document.createElement('div');
    item.classList.add('fix-item');

    // Header
    const header = document.createElement('div');
    header.classList.add('fix-header');
    header.setAttribute('role', 'button');
    header.setAttribute('aria-expanded', 'false');
    header.id = `fix-header-${i}`;

    const num = document.createElement('span');
    num.classList.add('fix-num');
    num.textContent = i + 1;

    const title = document.createElement('span');
    title.classList.add('fix-title');
    title.textContent = fix.title || `Point ${i + 1}`;

    const chevron = document.createElement('span');
    chevron.classList.add('fix-chevron');
    chevron.textContent = '▾';

    header.appendChild(num);
    header.appendChild(title);
    header.appendChild(chevron);

    // Body
    const body = document.createElement('div');
    body.classList.add('fix-body');

    const inner = document.createElement('div');
    inner.classList.add('fix-body-inner');

    if (fix.body) {
      let formattedBody = fix.body;
      
      // If the LLM omitted the keyword, add a default one for structure
      if (!formattedBody.match(/^\s*(REASON|EXAMPLE|TRY THIS( INSTEAD)?):/i)) {
         formattedBody = 'REASON: ' + formattedBody;
      }

      // Replace the keywords with stylized labels
      formattedBody = formattedBody.replace(/\b(REASON|EXAMPLE|TRY THIS( INSTEAD)?):\s*/gi, '<div class="fix-reason" style="margin-top: 12px; margin-bottom: 4px;">$1</div>');
      
      // Remove the first margin-top so it aligns well at the top of the box
      formattedBody = formattedBody.replace('style="margin-top: 12px; margin-bottom: 4px;"', 'style="margin-bottom: 4px;"');

      const reasonText = document.createElement('div');
      reasonText.classList.add('fix-reason-text');
      reasonText.innerHTML = formattedBody;

      inner.appendChild(reasonText);
    }

    body.appendChild(inner);
    item.appendChild(header);
    item.appendChild(body);
    container.appendChild(item);

    // Toggle
    header.addEventListener('click', () => {
      const expanded = item.classList.toggle('expanded');
      header.setAttribute('aria-expanded', expanded);
    });
  });
}

/* ══════════════════════════════════════════════════════════
   UI — Build hedge dots
   ══════════════════════════════════════════════════════════ */
function buildHedgeDots(signals, turns) {
  const container = document.getElementById('r-hedge-dots');
  if (!container) return;
  container.innerHTML = '';

  const total = 10;
  const filled = Math.min(signals || 0, total);

  for (let i = 0; i < total; i++) {
    const dot = document.createElement('div');
    dot.classList.add('hedge-dot');
    if (i < filled) dot.classList.add('filled');
    container.appendChild(dot);
  }
}

/* ══════════════════════════════════════════════════════════
   UI — Stagger-reveal report cards
   ══════════════════════════════════════════════════════════ */
function scheduleCardReveals() {
  const cards = document.querySelectorAll('.stagger-card');
  cards.forEach((card, i) => {
    card.style.animationDelay = '';
    card.classList.remove('card-visible');
  });

  // Trigger reflow
  void document.getElementById('report-sections')?.offsetHeight;

  cards.forEach((card, i) => {
    setTimeout(() => {
      card.classList.add('card-visible');
    }, i * 80);
  });
}

/* ══════════════════════════════════════════════════════════
   HOME — Mode detail rendering
   ══════════════════════════════════════════════════════════ */
const MODE_META = {
  freestyle: {
    name:     'FreeStyle',
    tagline:  'Speak freely on any prompt',
    desc:     'Warm up your voice with a random word or scenario. No rules, no opponent. Just you, speaking clearly. Perfect for daily warm-ups and building the habit of structured thought.',
    level:    0,
  },
  debate1: {
    name:     'Debate · Easy',
    tagline:  'Choose your topic, choose your side',
    desc:     'Pick a debate topic from a curated list, choose whether you\'re for or against it, and engage in a structured argument. The AI adapts to your points — stay calm, be clear.',
    level:    1,
  },
  debate2: {
    name:     'Debate · Medium',
    tagline:  'Topic assigned. Side chosen. Time to hold your ground.',
    desc:     'Your topic is assigned at random. You choose your side. The AI is more aggressive — it changes angles, introduces new evidence, and won\'t let weak arguments go unchallenged.',
    level:    2,
  },
  debate3: {
    name:     'Debate · Hard',
    tagline:  'Nothing is in your hands. Everything is in your words.',
    desc:     'Topic and side are both randomly assigned. The AI interrupts, challenges aggressively, and rewards only real-time thinking. High pressure. Honest feedback. Maximum growth.',
    level:    3,
  },
  weird: {
    name:     'Weird Situation',
    tagline:  'React to anything',
    desc:     'You\'re thrown into an unexpected, absurd, or challenging situation. Defend, explain, improvise. This mode tests adaptability, composure, and the ability to think on your feet.',
    level:    0,
  },
};

function renderModeDetail(mode) {
  const meta = MODE_META[mode] || MODE_META.freestyle;

  document.getElementById('mode-detail')?.setAttribute('data-mode', mode);
  setText('mode-detail-name',    meta.name);
  setText('mode-detail-tagline', meta.tagline);

  const descEl = document.getElementById('mode-detail-desc');
  if (descEl) descEl.textContent = meta.desc;

  // Difficulty bar
  const diffEl = document.getElementById('mode-difficulty');
  if (diffEl) {
    if (meta.level > 0) {
      diffEl.classList.remove('hidden');
      ['diff-1', 'diff-2', 'diff-3'].forEach((id, i) => {
        const seg = document.getElementById(id);
        if (!seg) return;
        seg.className = 'difficulty-seg';
        if (i < meta.level) {
          if (meta.level === 1) seg.classList.add('active-d1');
          else if (meta.level === 2) seg.classList.add('active-d2');
          else seg.classList.add('active-d3');
        }
      });
    } else {
      diffEl.classList.add('hidden');
    }
  }

  // Recent sessions for this mode
  renderRecentSessions(mode);
}

function renderRecentSessions(mode) {
  const container = document.getElementById('mode-recent-sessions');
  if (!container) return;
  container.innerHTML = '';

  const data = STATE.dashboardData;
  if (!data || !data.sessions) return;

  const modeDisplay = MODE_META[mode]?.name || '';
  const filtered = data.sessions
    .filter(s => s.mode === modeDisplay || s.mode?.toLowerCase().includes(mode))
    .slice(0, 3);

  if (filtered.length === 0) return;

  filtered.forEach(s => {
    const card = document.createElement('div');
    card.classList.add('recent-session-card');
    card.innerHTML = `
      <div class="rs-date">${s.date || '—'}</div>
      <div class="rs-meta">${s.turns} turns · ${s.wpm} wpm</div>
    `;
    container.appendChild(card);
  });
}

/* ══════════════════════════════════════════════════════════
   HOME — Landing stats
   ══════════════════════════════════════════════════════════ */
function updateLandingStats(data) {
  if (!data) return;
  const sessEl  = document.getElementById('stat-sessions');
  const turnsEl = document.getElementById('stat-turns');
  if (sessEl)  sessEl.textContent  = data.total_sessions;
  if (turnsEl) turnsEl.textContent = data.total_turns;
}

function updateSidebarStats(data) {
  if (!data) return;
  const sbSess   = document.getElementById('sb-sessions');
  const sbStreak = document.getElementById('sb-streak');
  const sbWpm    = document.getElementById('sb-wpm');
  if (sbSess)   sbSess.textContent   = data.total_sessions;
  if (sbStreak) sbStreak.textContent = data.streak || 0;
  if (sbWpm)    sbWpm.textContent    = data.avg_wpm || 0;
}

/* ══════════════════════════════════════════════════════════
   HOME — Apply unlock state to mode nav items
   ══════════════════════════════════════════════════════════ */
function applyUnlockState(state) {
  if (!state) return;

  const calCard = document.getElementById('calibration-card');
  const beginBtn = document.getElementById('btn-begin-mode');

  // Calibration card visibility
  if (!state.calibration_done && calCard) {
    calCard.classList.remove('hidden');
  } else if (calCard) {
    calCard.classList.add('hidden');
  }

  // Mode unlock conditions
  const lockConditions = {
    freestyle: { unlocked: state.freestyle, text: 'Complete calibration to unlock.' },
    debate1:   { unlocked: state.debate1,   text: 'Complete calibration to unlock.' },
    debate2:   { unlocked: state.debate2,   text: `Complete ${state.debate2_remaining} more Level 1 session${state.debate2_remaining !== 1 ? 's' : ''} to unlock Debate Medium.` },
    debate3:   { unlocked: state.debate3,   text: `Complete ${state.debate3_remaining} more Level 2 session${state.debate3_remaining !== 1 ? 's' : ''} to unlock Debate Hard.` },
    weird:     { unlocked: false, text: 'Will be unlocked in a future update.' },
  };

  const modes = ['freestyle', 'debate1', 'debate2', 'debate3', 'weird'];
  let firstUnlocked = null;

  modes.forEach(mode => {
    const btn = document.getElementById(`mode-btn-${mode}`);
    if (!btn) return;

    const lockInfo = lockConditions[mode];
    const lockIcon = btn.querySelector('.lock-icon');
    const lockCond = btn.querySelector('.lock-condition');

    if (lockInfo.unlocked) {
      btn.classList.remove('mode-locked');
      if (lockIcon) lockIcon.classList.add('hidden');
      if (lockCond) lockCond.classList.add('hidden');
      if (!firstUnlocked) firstUnlocked = mode;
    } else {
      btn.classList.add('mode-locked');
      btn.classList.remove('active');
      if (lockIcon) lockIcon.classList.remove('hidden');
      if (lockCond) {
        lockCond.classList.remove('hidden');
        lockCond.textContent = lockInfo.text;
      }
    }
  });

  // If calibration is not done, disable begin button and select nothing
  if (!state.calibration_done) {
    if (beginBtn) {
      beginBtn.disabled = true;
      beginBtn.style.opacity = '0.3';
    }
    // Deselect all modes
    document.querySelectorAll('.mode-nav-item').forEach(b => b.classList.remove('active'));
  } else {
    if (beginBtn) {
      beginBtn.disabled = false;
      beginBtn.style.opacity = '';
    }
    // Select the first unlocked mode if nothing is active
    const anyActive = document.querySelector('.mode-nav-item.active:not(.mode-locked)');
    if (!anyActive && firstUnlocked) {
      const btn = document.getElementById(`mode-btn-${firstUnlocked}`);
      if (btn) {
        btn.classList.add('active');
        STATE.currentMode = firstUnlocked;
        STATE.currentLevel = MODE_META[firstUnlocked]?.level || 0;
        renderModeDetail(firstUnlocked);
      }
    }
  }
}

/* ══════════════════════════════════════════════════════════
   CALIBRATION — Build calibration report screen
   ══════════════════════════════════════════════════════════ */
function buildCalibrationReport(data) {
  if (!data) return;

  const wpmEl = document.getElementById('cal-wpm');
  const filEl = document.getElementById('cal-fillers');
  const topEl = document.getElementById('cal-top-filler');
  const hedEl = document.getElementById('cal-hedging');
  const recEl = document.getElementById('cal-rec-text');

  if (wpmEl)  animateCountUp(wpmEl, data.avg_wpm, 800, 1);
  if (filEl)  animateCountUp(filEl, data.avg_fillers, 800, 1);
  if (topEl)  topEl.textContent = data.most_common_filler || 'none';
  if (hedEl)  animateCountUp(hedEl, data.hedging_signals, 800);

  if (recEl) {
    const level = data.recommended_level || 1;
    recEl.textContent = `Based on how you speak today, we recommend starting with Debate Level ${level}.`;
  }
}

/* ══════════════════════════════════════════════════════════
   SETUP — Topic step
   ══════════════════════════════════════════════════════════ */
async function renderSetupTopicStep(mode) {
  const topicCardsEl   = document.getElementById('topic-cards');
  const assignedEl     = document.getElementById('topic-assigned');
  const topicAssigned  = document.getElementById('assigned-topic-text');
  if (!topicCardsEl || !assignedEl) return;

  // Clear any existing refresh buttons to avoid leakage between modes
  const assignedCard = document.getElementById('assigned-topic-card');
  if (assignedCard) {
    assignedCard.querySelector('.topic-refresh-btn')?.remove();
  }

  STATE.selectedTopic = '';

  if (mode === 'debate1') {
    // Level 1 — user picks from list
    topicCardsEl.innerHTML = '';
    assignedEl.classList.add('hidden');
    topicCardsEl.classList.remove('hidden');

    let allTopics = await fetchTopics(1);

    function shuffle(arr) {
      const a = [...arr];
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    }

    function renderDebate1Topics(list) {
      topicCardsEl.innerHTML = '';

      // Refresh button row
      const refreshRow = document.createElement('div');
      refreshRow.className = 'topic-refresh-row';

      const refreshBtn = document.createElement('button');
      refreshBtn.className = 'topic-refresh-btn';
      refreshBtn.setAttribute('type', 'button');
      refreshBtn.setAttribute('title', 'Get different topics');
      refreshBtn.textContent = '↺';
      refreshBtn.addEventListener('click', async () => {
        refreshBtn.classList.add('spinning');
        refreshBtn.disabled = true;
        try {
          allTopics = await fetchTopics(1);
          renderDebate1Topics(shuffle(allTopics));
        } catch (e) {
          console.error('[Refresh]', e);
          refreshBtn.classList.remove('spinning');
          refreshBtn.disabled = false;
        }
      });
      refreshRow.appendChild(refreshBtn);
      topicCardsEl.appendChild(refreshRow);

      list.slice(0, 5).forEach(topic => {
        const card = document.createElement('button');
        card.classList.add('topic-card');
        card.setAttribute('type', 'button');

        const text = document.createElement('span');
        text.textContent = topic;

        const check = document.createElement('span');
        check.classList.add('topic-card-check');

        card.appendChild(text);
        card.appendChild(check);
        topicCardsEl.appendChild(card);

        card.addEventListener('click', () => {
          topicCardsEl.querySelectorAll('.topic-card').forEach(c => c.classList.remove('selected'));
          card.classList.add('selected');
          STATE.selectedTopic = topic;
          setTimeout(() => advanceSetupToSide(mode), 280);
        });
      });
    }

    renderDebate1Topics(shuffle(allTopics));

  } else if (mode === 'debate2' || mode === 'debate3') {
    // Level 2/3 — topic is AI-assigned, show placeholder and auto-advance
    topicCardsEl.classList.add('hidden');
    assignedEl.classList.remove('hidden');
    const placeholder = mode === 'debate2' ? 'Topic will be assigned automatically' : 'Topic will be assigned · Adapt.';
    if (topicAssigned) topicAssigned.textContent = placeholder;

    setTimeout(() => advanceSetupToSide(mode), 1200);

  } else if (mode === 'freestyle') {
    topicCardsEl.innerHTML = '';
    assignedEl.classList.add('hidden');
    topicCardsEl.classList.remove('hidden');

    // Helper: fetch from /api/setup and reveal the topic in the card
    async function fetchAndShowFreestyle(freestyleType) {
      const res = await fetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'freestyle',
          level: 0,
          topic: '',
          user_side: '',
          freestyle_type: freestyleType,
        }),
      });
      if (!res.ok) throw new Error('Setup failed');
      return await res.json();
    }

    function showFreestyleTopic(setupData, freestyleType) {
      STATE.prefetchedSetup = setupData;

      topicCardsEl.classList.add('hidden');
      assignedEl.classList.remove('hidden');

      const topicAssignedLabel = assignedEl.querySelector('.setup-label');
      if (topicAssignedLabel) {
        topicAssignedLabel.textContent = freestyleType === 'word' ? 'Your word' : 'Your scenario';
      }

      const topicText = document.getElementById('assigned-topic-text');
      if (topicText) topicText.textContent = setupData.topic || '';

      // Refresh button on the card
      const assignedCard = document.getElementById('assigned-topic-card');
      if (assignedCard) {
        assignedCard.querySelector('.topic-refresh-btn')?.remove();
        const refreshBtn = document.createElement('button');
        refreshBtn.className = 'topic-refresh-btn topic-refresh-inline';
        refreshBtn.setAttribute('type', 'button');
        refreshBtn.setAttribute('title', 'Get a different one');
        refreshBtn.textContent = '↺';
        refreshBtn.addEventListener('click', async () => {
          refreshBtn.classList.add('spinning');
          refreshBtn.disabled = true;
          try {
            const newData = await fetchAndShowFreestyle(freestyleType);
            showFreestyleTopic(newData, freestyleType);
          } catch (e) {
            notify('Could not get a new topic.', 'error');
          }
          // showFreestyleTopic re-creates the button, so no need to un-disable
        });
        assignedCard.appendChild(refreshBtn);
      }
    }

    // Show type options: Random Word or Scenario
    const options = ['Word', 'Scenario'];
    options.forEach(opt => {
      const card = document.createElement('button');
      card.classList.add('topic-card');
      card.setAttribute('type', 'button');

      const text = document.createElement('span');
      text.textContent = opt === 'Word' ? 'Random Word — speak around it' : 'Scenario — respond to a situation';

      const check = document.createElement('span');
      check.classList.add('topic-card-check');

      card.appendChild(text);
      card.appendChild(check);
      topicCardsEl.appendChild(card);

      card.addEventListener('click', async () => {
        if (card.classList.contains('loading-pulse')) return;
        topicCardsEl.querySelectorAll('.topic-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected', 'loading-pulse');

        const freestyleType = opt.toLowerCase();
        STATE.freestyle_type = freestyleType;
        STATE.selectedTopic  = '';
        STATE.prefetchedSetup = null;

        try {
          const setupData = await fetchAndShowFreestyle(freestyleType);
          showFreestyleTopic(setupData, freestyleType);
        } catch (e) {
          console.warn('[Freestyle setup pre-fetch]', e);
          notify('Could not load topic preview.', 'default');
        }

        card.classList.remove('loading-pulse');
        setTimeout(() => advanceSetupToBegin(), 280);
      });
    });

  } else if (mode === 'weird') {
    topicCardsEl.innerHTML = '';
    assignedEl.classList.add('hidden');
    topicCardsEl.classList.remove('hidden');

    // Helper: fetch a weird situation and reveal it
    async function fetchAndShowWeird() {
      const res = await fetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'weird',
          level: 0,
          topic: '',
          user_side: '',
          freestyle_type: '',
        }),
      });
      if (!res.ok) throw new Error('Setup failed');
      return await res.json();
    }

    function showWeirdTopic(setupData) {
      STATE.prefetchedSetup = setupData;

      topicCardsEl.classList.add('hidden');
      assignedEl.classList.remove('hidden');

      const topicAssignedLabel = assignedEl.querySelector('.setup-label');
      if (topicAssignedLabel) topicAssignedLabel.textContent = 'Your situation';

      const topicText = document.getElementById('assigned-topic-text');
      if (topicText) topicText.textContent = setupData.topic || '';

      // Refresh button on the card
      const assignedCard = document.getElementById('assigned-topic-card');
      if (assignedCard) {
        assignedCard.querySelector('.topic-refresh-btn')?.remove();
        const refreshBtn = document.createElement('button');
        refreshBtn.className = 'topic-refresh-btn topic-refresh-inline';
        refreshBtn.setAttribute('type', 'button');
        refreshBtn.setAttribute('title', 'Get a different situation');
        refreshBtn.textContent = '↺';
        refreshBtn.addEventListener('click', async () => {
          refreshBtn.classList.add('spinning');
          refreshBtn.disabled = true;
          try {
            const newData = await fetchAndShowWeird();
            showWeirdTopic(newData);
          } catch (e) {
            notify('Could not get a new situation.', 'error');
          }
        });
        assignedCard.appendChild(refreshBtn);
      }
    }

    const card = document.createElement('button');
    card.classList.add('topic-card');
    card.setAttribute('type', 'button');

    const text = document.createElement('span');
    text.textContent = 'Generate a Weird Situation for me';

    const check = document.createElement('span');
    check.classList.add('topic-card-check');

    card.appendChild(text);
    card.appendChild(check);
    topicCardsEl.appendChild(card);

    card.addEventListener('click', async () => {
      if (card.classList.contains('loading-pulse')) return;
      card.classList.add('selected', 'loading-pulse');
      STATE.selectedTopic = '';
      STATE.prefetchedSetup = null;

      try {
        const setupData = await fetchAndShowWeird();
        showWeirdTopic(setupData);
      } catch (e) {
        console.warn('[Weird setup pre-fetch]', e);
        notify('Could not load situation preview.', 'default');
      }

      card.classList.remove('loading-pulse');
      setTimeout(() => advanceSetupToBegin(), 280);
    });
  }
}

/* ══════════════════════════════════════════════════════════
   SETUP — Advance to side step
   ══════════════════════════════════════════════════════════ */
function advanceSetupToSide(mode) {
  const sideStep   = document.getElementById('setup-step-side');
  const sideButtons = document.getElementById('side-buttons');
  const sideRandom  = document.getElementById('side-random');
  const sideFor    = document.getElementById('side-for');
  const sideAgainst = document.getElementById('side-against');

  if (!sideStep) return;

  // Update progress dots
  setPdot(2);

  if (mode === 'debate3') {
    // Level 3 — random side reveal
    document.querySelector('.side-buttons')?.classList.add('hidden');
    sideRandom?.classList.remove('hidden');

    const sides = ['FOR', 'AGAINST'];
    const assigned = sides[Math.floor(Math.random() * 2)];
    STATE.assignedSide = assigned.toLowerCase();

    const flipBack = document.getElementById('flip-back-text');
    if (flipBack) {
      flipBack.textContent = assigned;
      flipBack.style.color = assigned === 'FOR' ? 'var(--accent)' : 'var(--red)';
    }

    // Flip animation
    setTimeout(() => {
      const inner = document.getElementById('flip-inner');
      if (inner) inner.classList.add('flipped');
      setTimeout(() => advanceSetupToBegin(), 800);
    }, 600);

  } else {
    // Debate 1 or 2 — user picks side
    document.querySelector('.side-buttons')?.classList.remove('hidden');
    sideRandom?.classList.add('hidden');

    // Reset selection
    sideFor?.classList.remove('selected-for');
    sideAgainst?.classList.remove('selected-against');
    STATE.selectedSide = '';
  }

  revealStep(sideStep);
}

/* ══════════════════════════════════════════════════════════
   SETUP — Advance to begin step
   ══════════════════════════════════════════════════════════ */
function advanceSetupToBegin() {
  const beginStep = document.getElementById('setup-step-begin');
  if (!beginStep) return;
  setPdot(3);
  revealStep(beginStep);

  const silenceNote = document.getElementById('silence-note');
  if (silenceNote) {
    let msg = '';
    if (STATE.currentMode === 'freestyle') {
      msg = 'Unlimited pause time. Take as much time as you need.';
    } else if (STATE.currentMode === 'debate1') {
      msg = 'Silence stops recording after 6 seconds.';
    } else if (STATE.currentMode === 'debate2') {
      msg = 'Silence stops recording after 4 seconds.';
    } else if (STATE.currentMode === 'debate3') {
      msg = 'Silence stops recording after 2 seconds.';
    } else if (STATE.currentMode === 'weird') {
      msg = 'Silence stops recording after 3 seconds.';
    } else {
      const map = { 1: 6, 2: 4, 3: 2 };
      const sec = map[STATE.currentLevel] || 3;
      msg = `Silence stops recording after ${sec} seconds.`;
    }
    silenceNote.textContent = msg;
  }
}

function revealStep(el) {
  el.classList.remove('hidden');
  el.classList.add('step-entering');
  setTimeout(() => el.classList.remove('step-entering'), 320);
}

function setPdot(n) {
  ['pdot-1', 'pdot-2', 'pdot-3'].forEach((id, i) => {
    const dot = document.getElementById(id);
    if (!dot) return;
    dot.classList.toggle('active', i < n);
  });
}

/* ══════════════════════════════════════════════════════════
   SESSION — Initialize live session screen
   ══════════════════════════════════════════════════════════ */
function initSessionScreen(setupData) {
  // Save session state
  STATE.sessionToken   = setupData.token;
  STATE.sessionTopic   = setupData.topic;
  STATE.sessionUserSide = setupData.user_side;
  STATE.sessionAiSide  = setupData.ai_side;
  STATE.sessionLevel   = setupData.level;
  STATE.sessionMode    = setupData.mode;
  
  // Create the session record in the DB now that the session is officially beginning
  fetch('/api/start-session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_token: setupData.token })
  }).catch(e => console.error('[Start Session Error]', e));
  
  // Set silence limit based on level and mode rules
  if (setupData.mode === 'freestyle') {
    STATE.silenceSeconds = null; // No limit
  } else if (setupData.mode === 'debate1') {
    STATE.silenceSeconds = 6.0;
  } else if (setupData.mode === 'debate2') {
    STATE.silenceSeconds = 4.0;
  } else if (setupData.mode === 'debate3') {
    STATE.silenceSeconds = 2.0;
  } else if (setupData.mode === 'weird') {
    STATE.silenceSeconds = 3.0; // Target Situation (Weird)
  } else {
    STATE.silenceSeconds = setupData.silence_seconds || null;
  }

  STATE.turnNumber     = 0;

  // Topic display
  setText('session-topic-display', setupData.topic);

  // Side badge
  const badgeSide  = document.getElementById('badge-side');
  const badgeLevel = document.getElementById('badge-level');

  if (badgeSide) {
    badgeSide.textContent = (setupData.user_side || 'FREESTYLE').toUpperCase();
    badgeSide.className = 'badge';
    if (setupData.user_side === 'for')     badgeSide.classList.add('badge-side-for');
    else if (setupData.user_side === 'against') badgeSide.classList.add('badge-side-against');
    else badgeSide.classList.add('badge-side-default');
  }

  if (badgeLevel) {
    const levelLabels = { 0: 'FREESTYLE', 1: 'EASY', 2: 'MEDIUM', 3: 'HARD' };
    const levelClasses = { 0: 'badge-level-none', 1: 'badge-level-easy', 2: 'badge-level-medium', 3: 'badge-level-hard' };
    badgeLevel.textContent = levelLabels[setupData.level] || 'STANDARD';
    badgeLevel.className = 'badge badge-level ' + (levelClasses[setupData.level] || 'badge-level-none');
  }

  // Turn counter
  updateTurnCounter(0);

  // Reset metrics
  const metricIds = ['metric-wpm', 'metric-fillers', 'metric-hedging'];
  metricIds.forEach(id => setText(id, '—'));

  // Clear chat
  const chatEl = document.getElementById('chat-messages');
  if (chatEl) chatEl.innerHTML = '';

  // Show empty state
  const emptyState = document.getElementById('session-empty-state');
  if (emptyState) emptyState.style.display = '';

  // Fix 1: Ensure feedback button is visible for all regular modes 
  // (it gets explicitly hidden during Calibration)
  const fbBtn = document.getElementById('btn-get-feedback');
  if (fbBtn) {
    if (setupData.mode === 'calibration') {
      fbBtn.style.display = 'none';
    } else {
      fbBtn.style.display = '';
    }
  }

  // Reset recording bar
  STATE.recordState          = 'idle';
  STATE.interruptedByServer  = false;
  setRecordState('idle');
  updateTranscriptBar('', false);
  STATE.audioChunks = [];
  STATE.submitting  = false;

  // Voice circle
  initVoiceCircle('voice-circle-session', 80);
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Load & render
   ══════════════════════════════════════════════════════════ */
async function loadDashboard() {
  const data = await fetchDashboard();
  if (!data) return;

  STATE.dashboardData = data;

  // Reset filter to overview
  STATE.dashFilter = 'overview';
  document.querySelectorAll('.dash-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.filter === 'overview');
  });

  renderDashboard('overview');
  await loadPatterns();
  await loadVoiceIdentity();
  await loadMilestones();
}

async function loadPatterns() {
  try {
    const res = await fetch('/api/patterns');
    if (!res.ok) return;
    const data = await res.json();
    renderPatterns(data.patterns, data.enough_sessions);
  } catch (e) {
    console.error('Failed to load patterns', e);
  }
}

function renderPatterns(patterns, enoughSessions) {
  const listEl = document.getElementById('dash-patterns-list');
  if (!listEl) return;
  listEl.innerHTML = '';

  if (!enoughSessions && patterns.length === 0) {
    listEl.innerHTML = '<div class="dash-empty-patterns">Not enough sessions yet to detect patterns. Complete 5 sessions to unlock your recurring delivery patterns.</div>';
    return;
  }
  
  if (patterns.length === 0) {
    listEl.innerHTML = '<div class="dash-empty-patterns">No recurring patterns discovered yet. Keep practicing!</div>';
    return;
  }

  patterns.forEach(p => {
    const el = document.createElement('div');
    el.className = 'pattern-card';
    
    // Properly escape pattern text to prevent XSS
    const textNode = document.createTextNode(p);
    el.appendChild(textNode);
    
    listEl.appendChild(el);
  });
}

// ── Voice Identity ────────────────────────────────────────────────
async function loadVoiceIdentity() {
  try {
    const res = await fetch('/api/voice-identity');
    if (!res.ok) return;
    const data = await res.json();
    renderVoiceIdentity(data.identity);
  } catch (err) {
    console.error("Error loading voice identity:", err);
  }
}

function renderVoiceIdentity(identity) {
  const wrap = document.getElementById('dash-voice-identity');
  if (!identity) {
    wrap.classList.add('hidden');
    return;
  }
  
  wrap.classList.remove('hidden');
  
  const labelEl = document.getElementById('voice-identity-label');
  const descEl = document.getElementById('voice-identity-desc');
  
  // Clear and safely inject text
  labelEl.innerHTML = '';
  descEl.innerHTML = '';
  labelEl.appendChild(document.createTextNode(identity.label));
  descEl.appendChild(document.createTextNode(identity.description));
}

// ── Milestone Narratives ──────────────────────────────────────────
async function loadMilestones() {
  try {
    const res = await fetch('/api/milestones');
    if (!res.ok) return;
    const data = await res.json();
    renderMilestones(data.milestones || []);
  } catch (err) {
    console.error("Error loading milestones:", err);
  }
}

function renderMilestones(milestones) {
  const wrap = document.getElementById('dash-milestone-wrap');
  if (!milestones || milestones.length === 0) {
    wrap.classList.add('hidden');
    return;
  }
  
  wrap.classList.remove('hidden');
  
  // Most recent
  const latest = milestones[0];
  const narrativeEl = document.getElementById('milestone-narrative');
  const countEl = document.getElementById('milestone-session-count');
  
  narrativeEl.innerHTML = '';
  narrativeEl.appendChild(document.createTextNode(latest.narrative));
  
  countEl.innerHTML = '';
  countEl.appendChild(document.createTextNode(`Session ${latest.session_count}`));
  
  // Older milestones
  const pastWrap = document.getElementById('milestone-past-wrap');
  const pastList = document.getElementById('milestone-past-list');
  const toggleBtn = document.getElementById('milestone-toggle');
  
  if (milestones.length > 1) {
    pastWrap.classList.remove('hidden');
    pastList.innerHTML = '';
    
    // Skip the first one
    for (let i = 1; i < milestones.length; i++) {
      const m = milestones[i];
      const item = document.createElement('div');
      item.className = 'milestone-past-item';
      
      const title = document.createElement('strong');
      title.appendChild(document.createTextNode(`Session ${m.session_count}`));
      
      const text = document.createElement('p');
      text.appendChild(document.createTextNode(m.narrative));
      
      item.appendChild(title);
      item.appendChild(text);
      pastList.appendChild(item);
    }
    
    // Set up toggle exactly once
    if (!toggleBtn.dataset.bound) {
      toggleBtn.dataset.bound = "true";
      toggleBtn.addEventListener('click', () => {
        const isHidden = pastList.classList.contains('hidden');
        if (isHidden) {
          pastList.classList.remove('hidden');
          toggleBtn.textContent = 'Hide past milestones ▴';
        } else {
          pastList.classList.add('hidden');
          toggleBtn.textContent = 'View past milestones ▾';
        }
      });
    }
  } else {
    pastWrap.classList.add('hidden');
  }
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Filter sessions by mode
   ══════════════════════════════════════════════════════════ */
function filterSessionsByMode(sessions, filter) {
  if (!sessions || filter === 'overview') return sessions;
  if (filter === 'freestyle') return sessions.filter(s => s.mode === 'FreeStyle');
  if (filter === 'debate')    return sessions.filter(s => (s.mode || '').startsWith('Debate'));
  if (filter === 'weird')     return sessions.filter(s => s.mode === 'Weird Situation');
  return sessions;
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Render with filter
   ══════════════════════════════════════════════════════════ */
function renderDashboard(filter) {
  const data = STATE.dashboardData;
  if (!data) return;

  const allSessions = data.sessions || [];
  const filtered = filterSessionsByMode(allSessions, filter);

  // Stat cards — compute from filtered sessions
  const totalSessions = filtered.length;
  const totalTurns = filtered.reduce((sum, s) => sum + (s.turns || 0), 0);
  const wpmVals = filtered.filter(s => s.wpm > 0).map(s => s.wpm);
  const filVals = filtered.map(s => s.fillers).filter(f => f !== undefined);
  const avgWpm = wpmVals.length ? +(wpmVals.reduce((a, b) => a + b, 0) / wpmVals.length).toFixed(1) : 0;
  const avgFillers = filVals.length ? +(filVals.reduce((a, b) => a + b, 0) / filVals.length).toFixed(1) : 0;

  animateCountUp(document.getElementById('ds-sessions'), totalSessions);
  animateCountUp(document.getElementById('ds-turns'),    totalTurns);
  animateCountUp(document.getElementById('ds-wpm'),      avgWpm, 600, 1);
  animateCountUp(document.getElementById('ds-fillers'),  avgFillers, 600, 1);

  // Streak — always global, not filtered
  const streakEl = document.getElementById('streak-num');
  if (streakEl) {
    streakEl.textContent = data.streak || 0;
    streakEl.className   = 'streak-num';
    if ((data.streak || 0) > 7)       streakEl.classList.add('streak-high');
    else if ((data.streak || 0) === 0) streakEl.classList.add('streak-zero');
  }

  // Calendar dots — always global
  buildStreakCalendar(data);

  // Charts — pass filter for donut adaptation
  buildCharts({ ...data, sessions: filtered }, filter);

  // Table — filtered
  buildSessionTable(filtered);

  // Empty state
  const empty = document.getElementById('dash-empty');
  const table = document.querySelector('.dash-table-wrap');
  if (filtered.length === 0) {
    if (empty) empty.classList.remove('hidden');
    if (table) table.style.display = 'none';
  } else {
    if (empty) empty.classList.add('hidden');
    if (table) table.style.display = '';
  }
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Streak calendar
   ══════════════════════════════════════════════════════════ */
function buildStreakCalendar(data) {
  const container = document.getElementById('streak-calendar');
  if (!container) return;
  container.innerHTML = '';

  const sessions = data.sessions || [];
  const dates    = new Set(sessions.map(s => s.date).filter(Boolean));
  const today    = new Date();

  for (let i = 13; i >= 0; i--) {
    const d   = new Date(today);
    d.setDate(d.getDate() - i);
    const str = d.toISOString().slice(0, 10);

    const dot = document.createElement('div');
    dot.classList.add('cal-dot');
    if (dates.has(str)) dot.classList.add('filled');
    if (i === 0)        dot.classList.add('today');
    dot.title = str;
    container.appendChild(dot);
  }
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Charts
   ══════════════════════════════════════════════════════════ */
const CHART_DEFAULTS = {
  responsive: true,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#2C2C28',
      titleColor: '#EEECEA',
      bodyColor: '#908E88',
      borderColor: '#424240',
      borderWidth: 1,
    },
  },
  scales: {
    x: {
      ticks: { color: '#504E4A', font: { family: 'JetBrains Mono', size: 10 } },
      grid:  { color: '#252521' },
    },
    y: {
      ticks: { color: '#504E4A', font: { family: 'JetBrains Mono', size: 10 } },
      grid:  { color: '#252521' },
    },
  },
};

function buildCharts(data, filter) {
  filter = filter || 'overview';
  const sessions = data.sessions || [];
  const labels   = sessions.map(s => `#${s.index}`);

  // Destroy existing
  if (STATE.chartFillers) { STATE.chartFillers.destroy(); STATE.chartFillers = null; }
  if (STATE.chartWpm)     { STATE.chartWpm.destroy();     STATE.chartWpm     = null; }
  if (STATE.chartModes)   { STATE.chartModes.destroy();   STATE.chartModes   = null; }

  // Chart 1 — Fillers
  const ctx1 = document.getElementById('chart-fillers');
  if (ctx1) {
    STATE.chartFillers = new Chart(ctx1, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data: sessions.map(s => s.fillers),
          borderColor: '#D4524A',
          borderWidth: 2,
          pointBackgroundColor: '#D4524A',
          pointRadius: 4,
          fill: false,
          tension: 0.3,
        }],
      },
      options: {
        ...CHART_DEFAULTS,
        animation: { duration: 600, easing: 'easeOutQuart' },
      },
    });
  }

  // Chart 2 — WPM
  const ctx2 = document.getElementById('chart-wpm');
  if (ctx2) {
    STATE.chartWpm = new Chart(ctx2, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            data: sessions.map(s => s.wpm),
            borderColor: '#4A8CD4',
            borderWidth: 2,
            pointBackgroundColor: '#4A8CD4',
            pointRadius: 4,
            fill: false,
            tension: 0.3,
          },
          // Ideal range band — 130–160
          {
            data: sessions.map(() => 160),
            borderColor: 'transparent',
            backgroundColor: 'rgba(74,140,212,0.05)',
            fill: '+1',
            pointRadius: 0,
          },
          {
            data: sessions.map(() => 130),
            borderColor: 'transparent',
            backgroundColor: 'transparent',
            fill: false,
            pointRadius: 0,
          },
        ],
      },
      options: {
        ...CHART_DEFAULTS,
        animation: { duration: 600, easing: 'easeOutQuart' },
        plugins: {
          ...CHART_DEFAULTS.plugins,
          legend: { display: false },
        },
      },
    });
  }

  // Chart 3 — Distribution donut (adapts per filter)
  const ctx3 = document.getElementById('chart-modes');
  const donutTotal = document.getElementById('donut-total');
  const distTitle = document.getElementById('chart-dist-title');
  const distSub = document.getElementById('chart-dist-subtitle');

  const modeColors = {
    'FreeStyle':      '#8FB87A',
    'Debate · Easy':  '#4A8CD4',
    'Debate · Medium':'#D48C4A',
    'Debate · Hard':  '#D4524A',
    'Weird Situation':'#8C6CD4',
  };

  if (ctx3) {
    let donutLabels = [];
    let donutData = [];
    let donutColors = [];
    let titleText = 'TRAINING DISTRIBUTION';
    let subText = 'Sessions by mode';

    if (filter === 'overview') {
      // All modes
      const modeCounts = {};
      sessions.forEach(s => {
        const key = s.mode || 'Unknown';
        modeCounts[key] = (modeCounts[key] || 0) + 1;
      });
      donutLabels = Object.keys(modeCounts);
      donutData = Object.values(modeCounts);
      donutColors = donutLabels.map(k => modeColors[k] || '#504E4A');
      titleText = 'TRAINING DISTRIBUTION';
      subText = 'Sessions by mode';

    } else if (filter === 'debate') {
      // Debate level breakdown
      const levelCounts = { 'Debate · Easy': 0, 'Debate · Medium': 0, 'Debate · Hard': 0 };
      sessions.forEach(s => {
        if (levelCounts[s.mode] !== undefined) levelCounts[s.mode]++;
      });
      donutLabels = Object.keys(levelCounts);
      donutData = Object.values(levelCounts);
      donutColors = donutLabels.map(k => modeColors[k] || '#504E4A');
      titleText = 'DEBATE LEVELS';
      subText = 'Easy · Medium · Hard';

    } else if (filter === 'freestyle') {
      // Single segment — freestyle count vs rest
      const count = sessions.length;
      const allCount = (STATE.dashboardData?.sessions || []).length;
      const rest = Math.max(0, allCount - count);
      donutLabels = ['FreeStyle', 'Other Modes'];
      donutData = [count, rest];
      donutColors = [modeColors['FreeStyle'], '#2C2C28'];
      titleText = 'FREESTYLE SESSIONS';
      subText = `${count} of ${allCount} total`;

    } else if (filter === 'weird') {
      // Single segment — weird count vs rest
      const count = sessions.length;
      const allCount = (STATE.dashboardData?.sessions || []).length;
      const rest = Math.max(0, allCount - count);
      donutLabels = ['Weird Situation', 'Other Modes'];
      donutData = [count, rest];
      donutColors = [modeColors['Weird Situation'], '#2C2C28'];
      titleText = 'WEIRD SITUATION SESSIONS';
      subText = `${count} of ${allCount} total`;
    }

    if (distTitle) distTitle.textContent = titleText;
    if (distSub) distSub.textContent = subText;

    const totalCount = donutData.reduce((a, b) => a + b, 0);
    if (donutTotal) donutTotal.textContent = sessions.length;

    if (totalCount > 0) {
      STATE.chartModes = new Chart(ctx3, {
        type: 'doughnut',
        data: {
          labels: donutLabels,
          datasets: [{
            data: donutData,
            backgroundColor: donutColors,
            borderColor: '#1A1A17',
            borderWidth: 2,
          }],
        },
        options: {
          cutout: '68%',
          responsive: true,
          animation: { duration: 600 },
          plugins: {
            legend: {
              display: true,
              position: 'right',
              labels: {
                color: '#908E88',
                font: { family: 'Jost', size: 11 },
                boxWidth: 10,
                padding: 12,
                filter: (item) => {
                  // Hide "Other Modes" from legend if its value is 0
                  if (item.text === 'Other Modes' && donutData[item.index] === 0) return false;
                  return true;
                },
              },
            },
            tooltip: CHART_DEFAULTS.plugins.tooltip,
          },
        },
      });
    } else {
      if (donutTotal) donutTotal.textContent = '0';
    }
  }
}

/* ══════════════════════════════════════════════════════════
   DASHBOARD — Session history table
   ══════════════════════════════════════════════════════════ */
const MODE_DOT_CLASS = {
  'FreeStyle':       'mode-dot-freestyle',
  'Debate · Easy':   'mode-dot-debate1',
  'Debate · Medium': 'mode-dot-debate2',
  'Debate · Hard':   'mode-dot-debate3',
  'Weird Situation': 'mode-dot-weird',
};

function buildSessionTable(sessions) {
  const tbody = document.getElementById('dash-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';
  STATE.expandedRow = null;

  sessions.forEach((s, idx) => {
    // Main row
    const tr = document.createElement('tr');
    tr.id = `row-${idx}`;

    const dotClass = MODE_DOT_CLASS[s.mode] || 'mode-dot-freestyle';

    tr.innerHTML = `
      <td>${s.index}</td>
      <td>${s.date || '—'}</td>
      <td>
        <span class="mode-dot ${dotClass}"></span>${s.mode || '—'}
      </td>
      <td>${s.topic || '—'}</td>
      <td>${s.turns}</td>
      <td>${s.wpm}</td>
      <td>${s.fillers}</td>
    `;

    // Expandable detail row
    const expandTr = document.createElement('tr');
    expandTr.classList.add('table-expand-row');
    expandTr.id = `expand-${idx}`;

    const expandTd = document.createElement('td');
    expandTd.colSpan = 7;

    const expandInner = document.createElement('div');
    expandInner.classList.add('table-expand-inner');

    const expandContent = document.createElement('div');
    expandContent.classList.add('table-expand-content');
    expandContent.textContent = `Session ${s.index} · ${s.mode} · ${s.turns} turns · ${s.wpm} WPM · ${s.fillers} avg fillers`;

    expandInner.appendChild(expandContent);
    expandTd.appendChild(expandInner);
    expandTr.appendChild(expandTd);

    tbody.appendChild(tr);
    tbody.appendChild(expandTr);

    // Toggle expansion
    tr.addEventListener('click', () => {
      const isExpanded = expandTr.classList.contains('expanded');

      // Collapse all
      document.querySelectorAll('.table-expand-row.expanded').forEach(r => {
        r.classList.remove('expanded');
        const prev = r.previousElementSibling;
        if (prev) prev.classList.remove('row-expanded');
      });

      if (!isExpanded) {
        expandTr.classList.add('expanded');
        tr.classList.add('row-expanded');
        STATE.expandedRow = idx;
      } else {
        STATE.expandedRow = null;
      }
    });
  });
}

/* ══════════════════════════════════════════════════════════
   EVENT HANDLERS — Wire up all buttons
   ══════════════════════════════════════════════════════════ */
function wireEvents() {
  // Landing → Start Training
  document.getElementById('btn-start-training')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/me');
      const authData = await res.json();
      if (!authData.logged_in) {
        showScreen('screen-auth');
        return;
      }
    } catch (e) {
      showScreen('screen-auth');
      return;
    }

    await loadDashboard();
    const unlock = await fetchUnlockState();
    renderModeDetail(STATE.currentMode);
    updateSidebarStats(STATE.dashboardData);
    applyUnlockState(unlock);
    showScreen('screen-home');
  });

  // Landing → How it works
  document.getElementById('btn-how-it-works')?.addEventListener('click', () => {
    const section = document.getElementById('landing-features-section');
    if (section) {
      section.scrollIntoView({ behavior: 'smooth' });
    }
  });

  // Nav links
  document.getElementById('nav-home')?.addEventListener('click', async () => {
    const unlock = await fetchUnlockState();
    applyUnlockState(unlock);
    showScreen('screen-home');
  });

  // Auth Logout
  document.getElementById('nav-logout')?.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.reload();
  });

  // Auth Tabs Toggle
  const tabSignin = document.getElementById('tab-signin');
  const tabRegister = document.getElementById('tab-register');
  const btnLogin = document.getElementById('btn-login');
  const btnRegister = document.getElementById('btn-register');

  if (tabSignin && tabRegister) {
    tabSignin.addEventListener('click', () => {
      tabSignin.classList.add('active');
      tabRegister.classList.remove('active');
      btnLogin.classList.remove('hidden');
      btnRegister.classList.add('hidden');
      document.getElementById('auth-error').classList.add('hidden');
    });

    tabRegister.addEventListener('click', () => {
      tabRegister.classList.add('active');
      tabSignin.classList.remove('active');
      btnRegister.classList.remove('hidden');
      btnLogin.classList.add('hidden');
      document.getElementById('auth-error').classList.add('hidden');
    });
  }

  // Auth Login / Register
  const authForm = document.getElementById('auth-form');
  if (authForm) {
    authForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('auth-username').value;
      const password = document.getElementById('auth-password').value;
      const submitter = e.submitter;
      const action = submitter.getAttribute('formaction');
      const errEl = document.getElementById('auth-error');
      
      errEl.classList.add('hidden');
      
      try {
        const res = await fetch(`/api/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        
        if (!res.ok) {
          const data = await res.json();
          errEl.textContent = data.detail || 'Authentication failed';
          errEl.classList.remove('hidden');
          return;
        }
        
        window.location.reload();
      } catch (err) {
        errEl.textContent = 'Network error';
        errEl.classList.remove('hidden');
      }
    });
  }

  document.getElementById('nav-progress')?.addEventListener('click', async () => {
    await loadDashboard();
    showScreen('screen-dashboard');
  });

  // Dashboard filter tabs
  document.querySelectorAll('.dash-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const filter = tab.dataset.filter;
      if (filter === STATE.dashFilter) return;

      STATE.dashFilter = filter;
      document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      renderDashboard(filter);
    });
  });

  // Mode nav items
  document.querySelectorAll('.mode-nav-item').forEach(btn => {
    btn.addEventListener('mouseenter', () => {
      if (btn.classList.contains('mode-locked')) return;
      const mode = btn.dataset.mode;
      let multiplier = 1.0;
      if (mode === 'freestyle' || mode === 'calibration') multiplier = 0.5;
      else if (mode === 'debate1') multiplier = 1.0;
      else if (mode === 'debate2') multiplier = 1.5;
      else if (mode === 'debate3') multiplier = 2.0;
      else if (mode === 'weird') multiplier = 1.2;
      document.documentElement.style.setProperty('--intensity-multiplier', multiplier);
    });

    btn.addEventListener('mouseleave', () => {
      document.documentElement.style.setProperty('--intensity-multiplier', 1.0);
    });

    btn.addEventListener('click', () => {
      // Guard against locked modes
      if (btn.classList.contains('mode-locked')) return;
      document.querySelectorAll('.mode-nav-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.currentMode  = btn.dataset.mode;
      STATE.currentLevel = MODE_META[STATE.currentMode]?.level || 0;
      renderModeDetail(STATE.currentMode);
    });
  });

  // Calibration — Start calibration session
  document.getElementById('btn-start-calibration')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-start-calibration');
    setLoading(btn, true);

    try {
      const res = await fetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'calibration',
          level: 0,
          topic: '',
          user_side: '',
          freestyle_type: '',
        }),
      });
      if (!res.ok) throw new Error('Calibration setup failed');
      const data = await res.json();

      // Initialize session screen for calibration
      STATE.currentMode = 'calibration';
      STATE.currentLevel = 0;
      initSessionScreen(data);
      initVoiceCircle('voice-circle-session', 80);
      showScreen('screen-session');

      // Hide the feedback button for calibration (auto-ends after 3 turns)
      const fbBtn = document.getElementById('btn-get-feedback');
      if (fbBtn) fbBtn.style.display = 'none';

    } catch (err) {
      console.error('[Calibration Setup]', err);
      notify('Could not start calibration. Is the server running?', 'error');
    }

    setLoading(btn, false);
  });

  // Calibration report — Continue to training
  document.getElementById('btn-cal-continue')?.addEventListener('click', async () => {
    await loadDashboard();
    const unlock = await fetchUnlockState();
    updateSidebarStats(STATE.dashboardData);
    applyUnlockState(unlock);
    renderModeDetail(STATE.currentMode);
    showScreen('screen-home');
  });

  // Begin mode → setup screen
  document.getElementById('btn-begin-mode')?.addEventListener('click', async () => {
    const mode  = STATE.currentMode;
    const level = MODE_META[mode]?.level || 0;
    STATE.currentLevel = level;

    // Reset setup state
    STATE.selectedTopic   = '';
    STATE.selectedSide    = '';
    STATE.assignedSide    = '';
    STATE.prefetchedSetup = null;
    STATE.freestyle_type  = 'word';

    // Reset steps visibility
    ['setup-step-topic', 'setup-step-side', 'setup-step-begin'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.add('hidden');
    });

    const topicStep = document.getElementById('setup-step-topic');
    topicStep?.classList.remove('hidden');

    // Reset side buttons visibility
    document.querySelector('.side-buttons')?.classList.remove('hidden');
    document.getElementById('side-random')?.classList.add('hidden');
    document.getElementById('flip-inner')?.classList.remove('flipped');

    // Reset progress dots
    setPdot(1);

    // Render topic step
    await renderSetupTopicStep(mode);

    showScreen('screen-setup');
  });

  // Setup back button
  document.getElementById('btn-setup-back')?.addEventListener('click', () => {
    showScreen('screen-home');
  });

  // Side selection buttons
  document.getElementById('side-for')?.addEventListener('click', () => {
    document.getElementById('side-for')?.classList.add('selected-for');
    document.getElementById('side-against')?.classList.remove('selected-against');
    STATE.selectedSide = 'for';
    setTimeout(() => advanceSetupToBegin(), 200);
  });

  document.getElementById('side-against')?.addEventListener('click', () => {
    document.getElementById('side-against')?.classList.add('selected-against');
    document.getElementById('side-for')?.classList.remove('selected-for');
    STATE.selectedSide = 'against';
    setTimeout(() => advanceSetupToBegin(), 200);
  });

  // Begin session button
  document.getElementById('btn-begin-session')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-begin-session');
    setLoading(btn, true);

    try {
      // For freestyle: reuse the pre-fetched setup (topic already revealed);
      // for all other modes: call /api/setup now as usual.
      const data = STATE.prefetchedSetup || await beginSession();
      STATE.prefetchedSetup = null; // consume it
      initSessionScreen(data);
      initVoiceCircle('voice-circle-session', 80);
      initVoiceCircle('voice-circle-home',    120);

      // Level 1: show expectation modal before entering session
      if (STATE.currentMode === 'debate1') {
        const modalL1 = document.getElementById('level1-warning-modal');
        if (modalL1) {
          modalL1.classList.remove('hidden');
          modalL1.classList.add('terminal-flash-enter');
          setLoading(btn, false);
          await new Promise(resolve => {
            const dismissBtnL1 = document.getElementById('btn-l1-dismiss');
            const handlerL1 = () => {
              dismissBtnL1.removeEventListener('click', handlerL1);
              modalL1.classList.add('hidden');
              resolve();
            };
            dismissBtnL1.addEventListener('click', handlerL1);
          });
        }
      }

      // Level 2: show expectation modal before entering session
      if (STATE.currentMode === 'debate2') {
        const modalL2 = document.getElementById('level2-warning-modal');
        if (modalL2) {
          modalL2.classList.remove('hidden');
          modalL2.classList.add('terminal-flash-enter');
          setLoading(btn, false);
          await new Promise(resolve => {
            const dismissBtnL2 = document.getElementById('btn-l2-dismiss');
            const handlerL2 = () => {
              dismissBtnL2.removeEventListener('click', handlerL2);
              modalL2.classList.add('hidden');
              resolve();
            };
            dismissBtnL2.addEventListener('click', handlerL2);
          });
        }
      }

      // Level 3: show warning modal before entering session
      if (STATE.currentMode === 'debate3') {
        const modalL3 = document.getElementById('level3-warning-modal');
        if (modalL3) {
          modalL3.classList.remove('hidden');
          modalL3.classList.add('terminal-flash-enter');
          setLoading(btn, false);
          // Wait for user acknowledgement of L3 warning
          await new Promise(resolve => {
            const dismissBtnL3 = document.getElementById('btn-l3-dismiss');
            const handlerL3 = () => {
              dismissBtnL3.removeEventListener('click', handlerL3);
              modalL3.classList.add('hidden');
              resolve();
            };
            dismissBtnL3.addEventListener('click', handlerL3);
          });
        }
        
        // Check for invisible audience effect (every 5th session)
        if (data.debate3_session_count > 0 && data.debate3_session_count % 5 === 0) {
          const modalAudience = document.getElementById('audience-effect-modal');
          if (modalAudience) {
            modalAudience.classList.remove('hidden');
            modalAudience.classList.add('terminal-flash-enter');
            // Wait for user acknowledgement of audience modal
            await new Promise(resolve => {
              const dismissBtnAud = document.getElementById('btn-audience-dismiss');
              const handlerAud = () => {
                dismissBtnAud.removeEventListener('click', handlerAud);
                modalAudience.classList.add('hidden');
                resolve();
              };
              dismissBtnAud.addEventListener('click', handlerAud);
            });
          }
        }
      }

      showScreen('screen-session');
    } catch (err) {
      console.error('[Setup]', err);
      notify('Could not start session. Is the server running?', 'error');
    }

    setLoading(btn, false);
  });

  // Record button
  document.getElementById('record-btn')?.addEventListener('click', toggleRecord);

  // Submit turn
  document.getElementById('btn-submit-turn')?.addEventListener('click', handleSubmitTurn);

  // Get feedback
  document.getElementById('btn-get-feedback')?.addEventListener('click', handleGetFeedback);

  // Report — audio buttons
  document.getElementById('btn-hear-summary')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-hear-summary');
    setLoading(btn, true);
    await playSummary();
    setLoading(btn, false);
  });

  document.getElementById('btn-hear-report')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-hear-report');
    setLoading(btn, true);
    await playFullReport();
    setLoading(btn, false);
  });

  // Report — Back to home
  document.getElementById('btn-report-back')?.addEventListener('click', async () => {
    const data = await fetchDashboard();
    STATE.dashboardData = data;
    updateSidebarStats(data);
    const unlock = await fetchUnlockState();
    if (unlock) applyUnlockState(unlock);
    renderModeDetail(STATE.currentMode);
    showScreen('screen-home');
  });

  // Report — New session
  document.getElementById('btn-new-session')?.addEventListener('click', async () => {
    const data = await fetchDashboard();
    STATE.dashboardData = data;
    updateSidebarStats(data);
    const unlock = await fetchUnlockState();
    if (unlock) applyUnlockState(unlock);
    renderModeDetail(STATE.currentMode);
    showScreen('screen-home');
  });

  // Report — View progress
  document.getElementById('btn-view-progress')?.addEventListener('click', async () => {
    await loadDashboard();
    showScreen('screen-dashboard');
  });
}

/* ══════════════════════════════════════════════════════════
   INIT
   ══════════════════════════════════════════════════════════ */
window.onload = async function () {
  // Initialize voice circles
  initVoiceCircle('voice-circle-landing', 300);
  initVoiceCircle('voice-circle-home',    120);
  initVoiceCircle('voice-circle-session', 80);

  // Wire all event listeners
  wireEvents();

  // Check Auth
  let isLoggedIn = false;
  try {
    const res = await fetch('/api/me');
    const authData = await res.json();
    isLoggedIn = authData.logged_in;
  } catch (e) {
    isLoggedIn = false;
  }

  if (!isLoggedIn) {
    showScreen('screen-landing');
    return;
  }

  // Load dashboard data in background (for landing stats)
  try {
    const data = await fetchDashboard();
    STATE.dashboardData = data;
    updateLandingStats(data);

    const unlock = await fetchUnlockState();
    if (unlock) {
      applyUnlockState(unlock);
    }
  } catch (e) {
    console.warn('[Init] Initial data fetch failed:', e);
  }

  // Determine starting screen:
  // If user has sessions, start at home; otherwise, landing.
  const hasSessions = STATE.dashboardData?.total_sessions > 0;

  if (hasSessions) {
    updateSidebarStats(STATE.dashboardData);
    renderModeDetail(STATE.currentMode);
    showScreen('screen-home');
    initVoiceCircle('voice-circle-home', 120);
  } else {
    showScreen('screen-landing');
  }

  // Fetch daily quote
  try {
    const qRes = await fetch('/api/daily_quote');
    if (qRes.ok) {
      const qData = await qRes.json();
      if (qData.is_new_today && qData.quote) {
        document.getElementById('daily-quote-category').textContent = qData.quote.category;
        document.getElementById('daily-quote-text').textContent = `"${qData.quote.text}"`;
        document.getElementById('embedded-daily-quote').classList.remove('hidden');
      }
    }
  } catch (e) {
    console.warn('[Init] Failed to fetch daily quote:', e);
  }
};
