(function () {
  'use strict';

  const $ = (s) => document.getElementById(s);
  const terminal    = $('terminal');
  const input       = $('cmd-input');
  const sendBtn     = $('send-btn');
  const micBtn      = $('mic-btn');
  const statusPill  = $('status-pill');
  const statusText  = $('status-text');
  const orbLabel    = $('orb-label');
  const waveform    = $('waveform');
  const waveBars    = $('wave-bars');
  const bootMsgs    = $('boot-msgs');

  let activeSource = null;
  let isProcessing = false;
  let cmdHistory = [];
  let cmdHistoryIdx = -1;
  let cpuHistory = [];
  let cpuCanvas, cpuCtx;
  let sessionNum = String(Math.floor(Math.random() * 999)).padStart(3, '0');

  // ═══ Boot sequence ═══
  const bootLines = [
    'JARVIS — Just A Rather Very Intelligent System',
    'Stark Industries v4.2.0',
    '',
    '<span class="highlight">[BOOT]</span> Initializing neural networks...',
    '<span class="highlight">[BOOT]</span> Loading LLM brain module...',
    '<span class="highlight">[BOOT]</span> Calibrating system agent...',
    '<span class="highlight">[BOOT]</span> Establishing communication channel...',
    '<span class="highlight">[OK]</span> All systems nominal.',
  ];

  async function runBoot() {
    for (let i = 0; i < bootLines.length; i++) {
      await delay(120 + Math.random() * 80);
      const div = document.createElement('div');
      div.className = 'term-line boot' + (i === bootLines.length - 1 ? ' ready' : '');
      div.innerHTML = bootLines[i];
      bootMsgs.appendChild(div);
      scrollToBottom();
    }
  }

  function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

  // ═══ Greeting ═══
  function getGreeting() {
    const h = new Date().getHours();
    if (h < 5)  return 'Good night, Sir.';
    if (h < 12) return 'Good morning, Sir.';
    if (h < 17) return 'Good afternoon, Sir.';
    if (h < 21) return 'Good evening, Sir.';
    return 'Good night, Sir.';
  }

  async function showGreeting() {
    await delay(300);
    const text = getGreeting() + ' All systems operational. I am JARVIS, at your service.';
    const card = createJarvisCard(text, 'greeting');
    terminal.appendChild(card);
    scrollToBottom();
    typewriterAppend(card, text, 18);
    speakText(text);
  }

  // ═══ Clock ═══
  function updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    $('hdr-clock').textContent = `${h}:${m}:${s}`;
  }

  // ═══ Metrics ═══
  async function fetchMetrics() {
    try {
      const r = await fetch('/api/metrics');
      const d = await r.json();
      $('hdr-cpu').textContent = d.cpu + '%';
      $('hdr-mem').textContent = d.memory.percent + '%';
      $('hdr-uptime').textContent = d.uptime;
      $('cpu-val').textContent = d.cpu + '%';
      $('cpu-fill').style.width = d.cpu + '%';
      if (d.cpu > 80) $('cpu-fill').classList.add('high');
      else $('cpu-fill').classList.remove('high');
      $('mem-val').textContent = d.memory.used_mb + ' / ' + d.memory.total_mb + ' MB';
      $('mem-fill').style.width = d.memory.percent + '%';
      $('disk-val').textContent = d.disk.used_gb + ' / ' + d.disk.total_gb + ' GB';
      $('disk-fill').style.width = d.disk.percent + '%';
      $('cwd-display').textContent = d.cwd || '-';
      drawCpuGraph(d.cpu);
    } catch (_) {}
  }

  // ═══ CPU graph ═══
  function initCpuGraph() {
    cpuCanvas = $('cpu-graph');
    if (!cpuCanvas) return;
    cpuCtx = cpuCanvas.getContext('2d');
    cpuCanvas.width = cpuCanvas.offsetWidth * 2;
    cpuCanvas.height = 80;
    cpuCanvas.style.height = '40px';
  }

  function drawCpuGraph(val) {
    if (!cpuCtx) return;
    cpuHistory.push(val);
    if (cpuHistory.length > 50) cpuHistory.shift();
    const w = cpuCanvas.width, h = cpuCanvas.height;
    cpuCtx.clearRect(0, 0, w, h);
    cpuCtx.strokeStyle = 'rgba(0,180,255,0.06)';
    cpuCtx.lineWidth = 1;
    for (let y = 0; y < h; y += h / 4) {
      cpuCtx.beginPath(); cpuCtx.moveTo(0, y); cpuCtx.lineTo(w, y); cpuCtx.stroke();
    }
    const step = w / (cpuHistory.length - 1 || 1);
    cpuCtx.beginPath();
    cpuCtx.strokeStyle = '#00b4ff';
    cpuCtx.lineWidth = 2;
    cpuCtx.shadowColor = 'rgba(0,180,255,0.4)';
    cpuCtx.shadowBlur = 6;
    cpuHistory.forEach((v, i) => {
      const x = i * step, y = h - (v / 100) * h;
      i === 0 ? cpuCtx.moveTo(x, y) : cpuCtx.lineTo(x, y);
    });
    cpuCtx.stroke();
    cpuCtx.shadowBlur = 0;
    cpuCtx.lineTo((cpuHistory.length - 1) * step, h);
    cpuCtx.lineTo(0, h);
    cpuCtx.closePath();
    const grad = cpuCtx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(0,180,255,0.15)');
    grad.addColorStop(1, 'rgba(0,180,255,0.0)');
    cpuCtx.fillStyle = grad;
    cpuCtx.fill();
  }

  // ═══ Status ═══
  function setStatus(state, label) {
    statusPill.className = 'status-pill';
    if (state) statusPill.classList.add(state);
    statusText.textContent = label || 'SYSTEMS ONLINE';
    orbLabel.textContent = label || 'ONLINE';
  }

  // ═══ Scroll ═══
  function scrollToBottom() {
    requestAnimationFrame(() => { terminal.scrollTop = terminal.scrollHeight; });
  }

  // ═══ Card builders ═══

  // JARVIS response card
  function createJarvisCard(text, extraClass) {
    const card = document.createElement('div');
    card.className = 'jarvis-card' + (extraClass ? ' ' + extraClass : '');

    const icon = document.createElement('div');
    icon.className = 'jc-icon';
    icon.innerHTML = '<div class="jc-reactor"><div class="ar-ring ar-ring-2"></div><div class="ar-ring ar-ring-1"></div><div class="ar-core"></div></div>';

    const body = document.createElement('div');
    body.className = 'jc-body';

    const label = document.createElement('div');
    label.className = 'jc-label';
    label.textContent = 'JARVIS';

    const tText = document.createElement('div');
    tText.className = 'jc-text';
    tText.textContent = text || '';

    body.appendChild(label);
    body.appendChild(tText);
    card.appendChild(icon);
    card.appendChild(body);
    return card;
  }

  // Command acknowledgment card
  function createCmdAck(command) {
    const ack = document.createElement('div');
    ack.className = 'cmd-ack';
    ack.innerHTML = '<span class="ca-dot"></span><span class="ca-text">ACKNOWLEDGED</span><span class="ca-cmd">' + escapeHtml(command) + '</span>';
    return ack;
  }

  // Output data card
  function createOutputCard(stdout, stderr, exitCode, status) {
    const card = document.createElement('div');
    card.className = 'output-card' + (status === 'error' ? ' error' : '');

    let content = '';
    if (stdout) content += stdout;
    if (stderr) content += (content ? '\n' : '') + stderr;
    if (!content) content = '[exit code: ' + exitCode + ']';

    card.textContent = sanitizeOutput(content);
    return card;
  }

  function sanitizeOutput(text) {
    if (!text) return '';
    return text
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
      .replace(/\x1b\][0-9;]*[^\x1b]*\x1b\\/g, '')
      .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '')
      .trim();
  }

  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  // ═══ Typewriter ═══
  function typewriterAppend(lineEl, text, speed) {
    return new Promise((resolve) => {
      const tEl = lineEl.querySelector('.jc-text') || lineEl.querySelector('.t-text');
      if (!tEl) { resolve(); return; }
      tEl.textContent = '';
      let i = 0;
      lineEl.classList.add('typing');
      const iv = setInterval(() => {
        if (i < text.length) {
          tEl.textContent += text[i];
          i++;
          scrollToBottom();
        } else {
          clearInterval(iv);
          lineEl.classList.remove('typing');
          resolve();
        }
      }, speed || 14);
    });
  }

  // ═══ Send message ═══
  function sendMessage(text) {
    if (isProcessing || !text.trim()) return;
    const msg = text.trim();
    input.value = '';
    isProcessing = true;
    input.disabled = true;

    cmdHistory.unshift(msg);
    if (cmdHistory.length > 50) cmdHistory.pop();
    cmdHistoryIdx = -1;

    // Command acknowledgment
    terminal.appendChild(createCmdAck(msg));
    scrollToBottom();

    setStatus('thinking', 'ANALYZING QUERY...');

    if (activeSource) activeSource.close();

    activeSource = new EventSourcePolyfill('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });

    activeSource.addEventListener('assistant_response', function (e) {
      const data = JSON.parse(e.data);
      const card = createJarvisCard('', '');
      terminal.appendChild(card);
      scrollToBottom();
      typewriterAppend(card, data.content, 14);
      speakText(data.content);
    });

    activeSource.addEventListener('command', function (e) {
      const data = JSON.parse(e.data);
      const execLine = document.createElement('div');
      execLine.className = 'exec-line';
      execLine.innerHTML = '<span class="el-icon">▶</span><span class="el-cmd">' + escapeHtml(data.content) + '</span>';
      terminal.appendChild(execLine);
      scrollToBottom();
      setStatus('executing', 'EXECUTING: ' + data.content);
    });

    activeSource.addEventListener('command_output', function (e) {
      const data = JSON.parse(e.data);
      terminal.appendChild(createOutputCard(data.stdout, data.stderr, data.exit_code, data.status));
      scrollToBottom();
      setStatus('thinking', 'PROCESSING DATA...');
    });

    activeSource.addEventListener('status', function (e) {
      const data = JSON.parse(e.data);
      setStatus(data.state === 'executing' ? 'executing' : 'thinking', data.label);
    });

    activeSource.addEventListener('done', function () {
      activeSource.close();
      activeSource = null;
      finishProcessing();
    });

    activeSource.addEventListener('error', function (e) {
      let msg = 'Connection lost';
      try { msg = JSON.parse(e.data).content || msg; } catch (_) {}
      const errCard = createJarvisCard('⚠ ' + msg, 'error-card');
      terminal.appendChild(errCard);
      scrollToBottom();
      activeSource.close();
      activeSource = null;
      finishProcessing();
    });
  }

  function finishProcessing() {
    isProcessing = false;
    input.disabled = false;
    input.focus();
    setStatus('', 'SYSTEMS ONLINE');
  }

  // ═══ EventSource POST polyfill ═══
  function EventSourcePolyfill(url, opts) {
    const self = this;
    self._listeners = {};
    self._closed = false;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Accept', 'text/event-stream');
    xhr.setRequestHeader('Cache-Control', 'no-cache');
    if (opts.headers) for (const k in opts.headers) xhr.setRequestHeader(k, opts.headers[k]);
    let lastIdx = 0;
    let eventType = 'message';
    xhr.onprogress = function () {
      const chunk = xhr.responseText.substring(lastIdx);
      lastIdx = xhr.responseText.length;
      const lines = chunk.split('\n');
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.substring(7).trim();
        } else if (line.startsWith('data: ')) {
          const ev = { data: line.substring(6) };
          (self._listeners[eventType] || []).forEach(fn => fn(ev));
          if (eventType !== 'message') (self._listeners['message'] || []).forEach(fn => fn(ev));
        }
      }
    };
    xhr.onerror = function () {
      if (!self._closed) (self._listeners['error'] || []).forEach(fn => fn({ data: JSON.stringify({ content: 'Connection lost' }) }));
    };
    xhr.send(opts.body || null);
    self.addEventListener = function (type, fn) {
      if (!self._listeners[type]) self._listeners[type] = [];
      self._listeners[type].push(fn);
    };
    self.close = function () { self._closed = true; xhr.abort(); };
  }

  // ═══ TTS (server-side edge-tts) ═══
  let currentAudio = null;

  function stopCurrentAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio.src = '';
      currentAudio = null;
    }
    showWaveform(false);
  }

  function speakText(text) {
    if (!text) return;
    const clean = text.replace(/<[^>]*>/g, '').replace(/[*_`#]/g, '').trim();
    if (!clean) return;

    stopCurrentAudio();
    showWaveform(true);

    fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: clean }),
    })
    .then(r => r.blob())
    .then(blob => {
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      currentAudio.onended = () => { showWaveform(false); URL.revokeObjectURL(url); currentAudio = null; };
      currentAudio.onerror = () => { showWaveform(false); URL.revokeObjectURL(url); currentAudio = null; };
      currentAudio.play();
    })
    .catch(() => { showWaveform(false); });
  }

  // ═══ Waveform ═══
  function initWaveBars() {
    waveBars.innerHTML = '';
    for (let i = 0; i < 40; i++) {
      const bar = document.createElement('div');
      bar.className = 'wave-bar';
      bar.style.setProperty('--h', (4 + Math.random() * 18) + 'px');
      bar.style.setProperty('--dur', (0.3 + Math.random() * 0.5) + 's');
      bar.style.animationDelay = (Math.random() * 0.5) + 's';
      bar.style.height = '3px';
      waveBars.appendChild(bar);
    }
  }

  function showWaveform(on) {
    waveform.classList.toggle('active', on);
    if (on) {
      waveBars.querySelectorAll('.wave-bar').forEach(bar => {
        bar.style.setProperty('--h', (4 + Math.random() * 18) + 'px');
        bar.style.setProperty('--dur', (0.3 + Math.random() * 0.5) + 's');
      });
    }
  }

  // ═══ Always-on Voice (Tony Stark JARVIS style) ═══
  let recognition = null;
  let isListening = false;
  let voiceReady = false;
  const WAKE_WORD = 'jarvis';
  let lastTranscript = '';

  // Modes: 'standby' = listening for wake word only, 'command' = listening for a command
  let voiceMode = 'standby';

  function initVoice() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      setListeningState('unsupported');
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR();
    recognition.lang = 'en-GB';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = handleVoiceResult;
    recognition.onerror = handleVoiceError;
    recognition.onend = restartListening;
  }

  function startListening() {
    if (!recognition || isListening) return;
    try {
      recognition.start();
      isListening = true;
      setListeningState('active');
    } catch (_) {}
  }

  function restartListening() {
    if (!voiceReady) return;
    isListening = false;
    setTimeout(() => {
      if (voiceReady) startListening();
    }, 100);
  }

  function enterCommandMode() {
    voiceMode = 'command';
    setListeningState('wake');
    $('listening-text').textContent = 'COMMAND MODE — Speak your command';
    $('listening-transcript').textContent = '';
  }

  function exitCommandMode() {
    voiceMode = 'standby';
    $('listening-transcript').textContent = '';
    setListeningState('active');
  }

  function handleVoiceResult(e) {
    let finalText = '';
    let interimText = '';

    for (let i = e.resultIndex; i < e.results.length; i++) {
      const transcript = e.results[i][0].transcript.toLowerCase().trim();
      if (e.results[i].isFinal) {
        finalText += transcript;
      } else {
        interimText += transcript;
      }
    }

    // Show interim text in transcript area
    if (interimText) {
      $('listening-transcript').textContent = interimText;
    }

    if (!finalText) return;

    $('listening-transcript').textContent = finalText;

    // ── COMMAND MODE: anything said is a command ──
    if (voiceMode === 'command') {
      // Stop any playing TTS from previous response
      stopCurrentAudio();

      // Ignore if they're just repeating the wake word
      const stripped = finalText.replace(new RegExp(WAKE_WORD, 'gi'), '').trim();
      if (!stripped) {
        // They said "JARVIS" again while in command mode — just clear the transcript
        $('listening-transcript').textContent = '';
        return;
      }

      // Got a real command — process it, stay in command mode
      setListeningState('command');
      $('listening-transcript').textContent = '';
      setTimeout(() => {
        sendMessage(stripped);
      }, 300);
      return;
    }

    // ── STANDBY MODE: only listen for the wake word ──
    if (finalText.includes(WAKE_WORD)) {
      // Respond with "Yes, Sir?" then open command window
      setListeningState('wake');
      const jarvisCard = createJarvisCard('Yes, Sir?', '');
      terminal.appendChild(jarvisCard);
      scrollToBottom();
      speakText('Yes, Sir?');
      $('listening-transcript').textContent = '';
      setTimeout(() => enterCommandMode(), 400);
    }
    // In standby, non-wake-word speech is ignored (background chatter)
  }

  function handleVoiceError(e) {
    if (e.error === 'no-speech' || e.error === 'aborted') {
      // Normal — just restart
      return;
    }
    console.warn('[Voice]', e.error);
  }

  function setListeningState(state) {
    const bar = $('listening-bar');
    const text = $('listening-text');
    const dot = bar.querySelector('.lb-dot');
    micBtn.className = 'input-btn mic-btn';

    bar.className = 'listening-bar';
    switch (state) {
      case 'active':
        bar.classList.add('active');
        micBtn.classList.add('listening');
        text.textContent = 'VOICE ACTIVE — Say "JARVIS"';
        break;
      case 'wake':
        bar.classList.add('wake');
        micBtn.classList.add('wake');
        text.textContent = 'JARVIS DETECTED';
        break;
      case 'command':
        bar.classList.add('command');
        micBtn.classList.add('command');
        text.textContent = 'COMMAND MODE — Speak your command';
        break;
      case 'unsupported':
        text.textContent = 'VOICE NOT SUPPORTED';
        break;
      default:
        text.textContent = 'VOICE STANDBY';
    }
  }

  // Mic button click toggles voice on/off
  micBtn.addEventListener('click', () => {
    if (!recognition) return;
    if (!voiceReady) {
      voiceReady = true;
      startListening();
      return;
    }
    if (isListening) {
      voiceReady = false;
      recognition.stop();
      isListening = false;
      setListeningState('off');
    } else {
      voiceReady = true;
      startListening();
    }
  });

  // ═══ Events ═══
  sendBtn.addEventListener('click', () => sendMessage(input.value));

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input.value);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (cmdHistoryIdx < cmdHistory.length - 1) {
        cmdHistoryIdx++;
        input.value = cmdHistory[cmdHistoryIdx];
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (cmdHistoryIdx > 0) {
        cmdHistoryIdx--;
        input.value = cmdHistory[cmdHistoryIdx];
      } else {
        cmdHistoryIdx = -1;
        input.value = '';
      }
    }
  });

  document.querySelectorAll('.hud-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const cmd = btn.dataset.cmd;
      if (cmd) sendMessage(cmd);
    });
  });

  // ═══ Init ═══
  async function init() {
    updateClock();
    setInterval(updateClock, 1000);
    initWaveBars();
    initCpuGraph();

    await runBoot();

    try {
      const r = await fetch('/api/status');
      const d = await r.json();
      $('hdr-provider').textContent = d.provider.toUpperCase() + ' — ' + (d.model || 'N/A');
      $('info-provider').textContent = d.provider;
      $('info-model').textContent = d.model || '-';
      $('info-os').textContent = d.os || '-';
      $('info-user').textContent = d.user || '-';
      $('term-session').textContent = 'SESSION #' + sessionNum;
    } catch (_) {}

    fetchMetrics();
    setInterval(fetchMetrics, 3000);

    const splash = $('splash');
    const activateBtn = $('activate-btn');

    activateBtn.addEventListener('click', async function () {
      splash.classList.add('hidden');
      await delay(600);
      await showGreeting();
      initVoice();
      voiceReady = true;
      startListening();
      input.focus();
    });
  }

  init();
})();
