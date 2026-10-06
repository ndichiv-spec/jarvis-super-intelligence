class JarvisDashboard {
    constructor() {
        console.log('JARVIS: Constructor started');
        this.socket = null;
        this.currentPath = '.';
        this.selectedProcess = null;
        this.cpuHistory = [];
        this.memHistory = [];
        this.netHistory = [];
        this.isListening = false;
        this.recognition = null;
        this.streamingResponse = '';
        this.uptime = 0;
        this.requestCount = 0;
        this.anonMode = true;
        
        console.log('JARVIS: Initializing elements');
        this.initElements();
        
        console.log('JARVIS: Connecting WebSocket');
        this.connectWebSocket();
        
        console.log('JARVIS: Setting up event listeners');
        this.initEventListeners();
        
        console.log('JARVIS: Starting monitoring');
        this.startSystemMonitoring();
        this.updateClock();
        this.initCharts();
        this.loadAIStatus();
        this.initHeroCanvas();
        this.initAmbientBg();
        
        console.log('JARVIS: Initialization complete');
    }

    initElements() {
        this.voiceBtn = document.getElementById('voiceBtn');
        this.transcript = document.getElementById('transcript') || document.querySelector('.transcript-content');
        this.chatInput = document.getElementById('chatInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.chatMessages = document.getElementById('chatMessages');
        this.modelSelect = document.getElementById('modelSelect');
        this.logsContainer = document.getElementById('logsContainer');
        this.statusText = document.getElementById('statusText');
        this.statusBadge = document.getElementById('statusBadge');
        this.cpuValue = document.getElementById('cpuValue');
        this.ramValue = document.getElementById('ramValue');
        this.diskValue = document.getElementById('diskValue');
        this.cpuBar = document.getElementById('cpuBar');
        this.ramBar = document.getElementById('ramBar');
        this.diskBar = document.getElementById('diskBar');
        this.miniCpu = document.getElementById('miniCpu');
        this.miniMem = document.getElementById('miniMem');
        this.miniCpuBar = document.getElementById('miniCpuBar');
        this.miniMemBar = document.getElementById('miniMemBar');
        this.panelTitle = document.getElementById('panelTitle');
        this.panelSubtitle = document.getElementById('panelSubtitle');
        this.commandPalette = document.getElementById('commandPalette');
        this.cmdInput = document.getElementById('cmdInput');
        this.cmdResults = document.getElementById('cmdResults');
        this.chatToggle = document.getElementById('chatToggle');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.toastContainer = document.getElementById('toastContainer');
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}`;
        
        try {
            this.socket = io(wsUrl, {
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionAttempts: 10
            });

            this.socket.on('connect', () => {
                this.addLog('WebSocket connected', 'success');
                this.setStatus('online', 'Online');
                this.showToast('Connected to JARVIS', 'success');
            });

            this.socket.on('disconnect', () => {
                this.addLog('WebSocket disconnected', 'error');
                this.setStatus('offline', 'Offline');
            });

            this.socket.on('connected', (data) => {
                this.addLog(`Server: ${data.status}`, 'info');
            });

            this.socket.on('voice_response', (data) => {
                this.updateTranscript(data.response);
                this.addJarvisMessage(data.response);
            });

            this.socket.on('chat_chunk', (data) => {
                this.appendToLastMessage(data.chunk);
            });

            this.socket.on('chat_complete', () => {
                this.hideTypingIndicator();
            });

            this.socket.on('training_progress', (data) => {
                if (data.validated) {
                    this.addLog(`Trained: ${data.input}`, 'training');
                }
            });
        } catch (err) {
            this.addLog('Using HTTP fallback', 'warn');
        }
    }

    initEventListeners() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                this.showPanel(item.dataset.panel);
            });
        });

        this.voiceBtn?.addEventListener('click', () => this.toggleVoice());
        this.voiceBtn?.addEventListener('mousedown', () => this.startListening());
        this.voiceBtn?.addEventListener('mouseup', () => this.stopListening());
        this.voiceBtn?.addEventListener('mouseleave', () => this.stopListening());

        this.sendBtn?.addEventListener('click', () => this.sendChatMessage());
        
        this.chatInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendChatMessage();
            }
        });

        this.chatInput?.addEventListener('input', () => {
            this.chatInput.style.height = 'auto';
            this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 150) + 'px';
        });

        document.getElementById('clearLogs')?.addEventListener('click', () => this.clearLogs());
        
        document.querySelectorAll('.command-btn, .action-card').forEach(btn => {
            btn.addEventListener('click', () => {
                const cmd = btn.dataset.command || btn.dataset.action;
                if (cmd) this.showPanel(cmd);
            });
        });

        document.getElementById('processSearch')?.addEventListener('input', (e) => {
            this.filterProcesses(e.target.value);
        });

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.toggleCommandPalette();
            }
            if (e.key === 'Escape' && this.commandPalette?.classList.contains('active')) {
                this.closeCommandPalette();
            }
        });

        this.cmdInput?.addEventListener('input', (e) => this.searchCommands(e.target.value));
        this.cmdInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.executeCommand();
        });

        this.chatToggle?.addEventListener('click', () => this.showPanel('chat'));

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });

        document.querySelectorAll('.action-card').forEach(card => {
            card.addEventListener('click', () => {
                const action = card.dataset.action;
                if (action === 'chat') this.showPanel('chat');
                else if (action === 'voice') this.showPanel('voice');
                else if (action === 'search') this.showPanel('web');
            });
        });

        document.querySelectorAll('.checkbox-label input').forEach(cb => {
            cb.addEventListener('change', (e) => {
                if (e.target.id === 'anonMode') {
                    this.anonMode = e.target.checked;
                    this.showToast(`Anonymous mode: ${this.anonMode ? 'ON' : 'OFF}`, 'info');
                }
            });
        });

        document.querySelectorAll('.toggle input').forEach(toggle => {
            toggle.addEventListener('change', () => this.handleToggle(toggle));
        });

        document.getElementById('clearChatBtn')?.addEventListener('click', () => this.clearChat());
        document.getElementById('exportChatBtn')?.addEventListener('click', () => this.exportChat());

        document.getElementById('aiTemp')?.addEventListener('input', (e) => {
            document.getElementById('tempValue').textContent = e.target.value + '%';
        });

        document.getElementById('maxTokens')?.addEventListener('input', (e) => {
            document.getElementById('tokensValue').textContent = e.target.value;
        });
    }

    handleToggle(toggle) {
        const id = toggle.id;
        if (id === 'soundEffects') {
            this.showToast(`Sound effects: ${toggle.checked ? 'ON' : 'OFF}`, 'info');
        } else if (id === 'wsDebug') {
            this.showToast(`WebSocket debug: ${toggle.checked ? 'ON' : 'OFF}`, 'info');
        }
    }

    toggleCommandPalette() {
        if (!this.commandPalette) return;
        const isActive = this.commandPalette.classList.toggle('active');
        if (isActive) {
            this.cmdInput.focus();
            this.populateCommandResults();
        }
    }

    closeCommandPalette() {
        this.commandPalette?.classList.remove('active');
        this.cmdInput.value = '';
    }

    populateCommandResults() {
        const commands = [
            { name: 'Dashboard', icon: '◈', panel: 'dashboard' },
            { name: 'Chat', icon: '💬', panel: 'chat' },
            { name: 'Voice', icon: '🎤', panel: 'voice' },
            { name: 'Web Search', icon: '🔍', panel: 'web' },
            { name: 'Processes', icon: '⚡', panel: 'processes' },
            { name: 'Files', icon: '📁', panel: 'files' },
            { name: 'Monitoring', icon: '📊', panel: 'observation' },
            { name: 'Knowledge', icon: '🧠', panel: 'knowledge' },
            { name: 'Training', icon: '⬢', panel: 'training' },
            { name: 'System', icon: '⚙', panel: 'system' },
            { name: 'Settings', icon: '✎', panel: 'settings' },
            { name: 'Clear Chat', icon: '🗑️', action: 'clearChat' },
            { name: 'Screenshot', icon: '📸', action: 'screenshot' },
            { name: 'Get Weather', icon: '🌤️', action: 'weather' }
        ];

        this.cmdResults.innerHTML = commands.map(c => `
            <div class="cmd-item" data-panel="${c.panel || ''}" data-action="${c.action || ''}">
                <span class="cmd-item-icon">${c.icon}</span>
                <span class="cmd-item-name">${c.name}</span>
            </div>
        `).join('');

        this.cmdResults.querySelectorAll('.cmd-item').forEach(item => {
            item.addEventListener('click', () => {
                const panel = item.dataset.panel;
                const action = item.dataset.action;
                if (panel) this.showPanel(panel);
                if (action) this.executeAction(action);
                this.closeCommandPalette();
            });
        });
    }

    searchCommands(query) {
        const items = this.cmdResults.querySelectorAll('.cmd-item');
        items.forEach(item => {
            const name = item.querySelector('.cmd-item-name').textContent.toLowerCase();
            item.style.display = name.includes(query.toLowerCase()) ? '' : 'none';
        });
    }

    executeCommand() {
        const firstVisible = this.cmdResults.querySelector('.cmd-item:not([style*="display: none"])');
        if (firstVisible) firstVisible.click();
    }

    executeAction(action) {
        if (action === 'clearChat') this.clearChat();
        else if (action === 'screenshot') this.takeScreenshot();
        else if (action === 'weather') this.getWeather();
    }

    showPanel(panelId) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.panel === panelId);
        });

        const titles = {
            'dashboard': ['Dashboard', 'System Overview'],
            'voice': ['Voice Interface', 'Speech Recognition'],
            'chat': ['AI Assistant', 'Natural Language'],
            'web': ['Web Tools', 'Search & APIs'],
            'processes': ['Process Manager', 'Running Tasks'],
            'files': ['File Browser', 'Navigation'],
            'observation': ['Monitoring', 'Real-time Metrics'],
            'knowledge': ['Knowledge Base', 'Data Store'],
            'training': ['Training Engine', 'ML Model'],
            'system': ['System Tools', 'Utilities'],
            'settings': ['Settings', 'Configuration']
        };

        if (titles[panelId]) {
            this.panelTitle.textContent = titles[panelId][0];
            this.panelSubtitle.textContent = titles[panelId][1];
        }

        document.querySelectorAll('.panel').forEach(panel => {
            panel.classList.add('hidden');
            panel.classList.remove('active');
        });

        const panelMap = {
            'dashboard': 'dashboardPanel',
            'voice': 'voicePanel',
            'chat': 'chatPanel',
            'web': 'webPanel',
            'processes': 'processesPanel',
            'files': 'filesPanel',
            'observation': 'observationPanel',
            'knowledge': 'knowledgePanel',
            'training': 'trainingPanel',
            'system': 'systemToolsPanel',
            'settings': 'settingsPanel'
        };

        const targetPanel = document.getElementById(panelMap[panelId]);
        if (targetPanel) {
            targetPanel.classList.remove('hidden');
            targetPanel.classList.add('active');
        }

        if (panelId === 'processes') this.loadProcesses();
        if (panelId === 'files') this.loadFiles(this.currentPath);
        if (panelId === 'observation') this.loadObservation();
        if (panelId === 'knowledge') this.loadKnowledge();
        if (panelId === 'training') this.loadTraining();
        if (panelId === 'settings') this.loadAIStatus();

        this.addLog(`Opened: ${panelId}`, 'info');
    }

    switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.add('hidden');
            content.classList.remove('active');
        });
        const targetTab = document.getElementById(tabId + 'Tab');
        if (targetTab) {
            targetTab.classList.remove('hidden');
            targetTab.classList.add('active');
        }
    }

    toggleVoice() {
        if (this.isListening) {
            this.stopListening();
            this.voiceBtn?.classList.remove('active');
        } else {
            this.startListening();
            this.voiceBtn?.classList.add('active');
        }
    }

    async startListening() {
        this.isListening = true;
        this.updateVoiceVisualizer();
        
        try {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRecognition) {
                this.recognition = new SpeechRecognition();
                this.recognition.continuous = true;
                this.recognition.interimResults = true;
                
                this.recognition.onresult = (event) => {
                    const transcript = Array.from(event.results)
                        .map(result => result[0].transcript)
                        .join('');
                    this.updateTranscript(transcript);
                    
                    if (event.results[0].isFinal) {
                        this.processVoiceCommand(transcript);
                    }
                };
                
                this.recognition.start();
                this.addLog('Microphone activated', 'info');
                this.updateVoiceStatus('Listening...');
            }
        } catch (err) {
            this.addLog('Microphone denied', 'error');
        }
    }

    stopListening() {
        this.isListening = false;
        if (this.recognition) {
            this.recognition.stop();
            this.recognition = null;
        }
        this.addLog('Voice deactivated', 'info');
        this.updateVoiceStatus('Ready');
    }

    updateVoiceStatus(status) {
        const statusEl = document.getElementById('voiceStatus');
        if (statusEl) statusEl.textContent = status;
    }

    updateVoiceVisualizer() {
        const canvas = document.getElementById('voiceCanvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = canvas.offsetHeight;
        
        const animate = () => {
            ctx.fillStyle = 'rgba(3, 5, 8, 0.3)';
            ctx.fillRect(0, 0, w, h);
            
            const time = Date.now() / 1000;
            const centerY = h / 2;
            
            for (let i = 0; i < 50; i++) {
                const x = (i / 50) * w;
                const amplitude = this.isListening ? Math.sin(time * 3 + i * 0.2) * 30 : Math.sin(time + i * 0.1) * 10;
                const y = centerY + amplitude;
                
                const gradient = ctx.createLinearGradient(x, centerY - 20, x, centerY + 20);
                gradient.addColorStop(0, 'rgba(0, 240, 255, 0.8)');
                gradient.addColorStop(0.5, 'rgba(139, 92, 246, 0.6)');
                gradient.addColorStop(1, 'rgba(255, 0, 170, 0.4)');
                
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, Math.PI * 2);
                ctx.fillStyle = gradient;
                ctx.fill();
            }
            
            if (this.isListening || true) requestAnimationFrame(animate);
        };
        
        animate();
    }

    processVoiceCommand(command) {
        if (this.socket && this.socket.connected) {
            this.socket.emit('voice_command', { command: command });
        } else {
            this.sendChatMessage(command);
        }
    }

    updateTranscript(text) {
        const el = document.getElementById('transcript') || document.querySelector('.transcript-content');
        if (el) el.textContent = text || 'Waiting for input...';
    }

    async sendChatMessage(overrideMessage = null) {
        const message = overrideMessage || this.chatInput.value.trim();
        if (!message) return;

        this.addUserMessage(message);
        if (!overrideMessage) this.chatInput.value = '';
        this.chatInput.style.height = 'auto';
        
        this.requestCount++;
        this.showTypingIndicator();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    message, 
                    model: this.modelSelect?.value || 'local',
                    stream: true
                })
            });
            
            if (response.ok) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    this.appendToLastMessage(chunk);
                }
                
                this.hideTypingIndicator();
                this.addLog(`Chat: ${message.substring(0, 30)}`, 'chat');
            } else {
                const data = await response.json();
                this.addJarvisMessage(data.response || 'Processing...');
                this.hideTypingIndicator();
            }
        } catch (err) {
            this.addJarvisMessage('Connection error');
            this.hideTypingIndicator();
        }
    }

    appendToLastMessage(text) {
        const lastMsg = this.chatMessages?.querySelector('.jarvis-message:last-child');
        if (lastMsg) {
            const content = lastMsg.querySelector('.message-text');
            if (content) {
                const rendered = marked.parse(text);
                content.innerHTML += rendered;
                this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
            }
        }
    }

    addUserMessage(text) {
        if (!this.chatMessages) return;
        
        const el = document.createElement('div');
        el.className = 'message user-message';
        const time = new Date().toLocaleTimeString('en-US', { hour12: false });
        el.innerHTML = `
            <div class="message-avatar">U</div>
            <div class="message-content">
                <div class="message-text"><p>${this.escapeHtml(text)}</p></div>
                <div class="message-meta"><span class="message-time">${time}</span></div>
            </div>
            <div class="message-actions">
                <button class="msg-action" title="Copy" onclick="jarvis.copyMessage(this)">📋</button>
            </div>
        `;
        this.chatMessages.appendChild(el);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    addJarvisMessage(text) {
        if (!this.chatMessages) return;
        
        const el = document.createElement('div');
        el.className = 'message jarvis-message';
        const time = new Date().toLocaleTimeString('en-US', { hour12: false });
        
        const rendered = marked.parse(text);
        
        el.innerHTML = `
            <div class="message-avatar">J</div>
            <div class="message-content">
                <div class="message-text">${rendered}</div>
                <div class="message-meta"><span class="message-time">${time}</span></div>
            </div>
            <div class="message-actions">
                <button class="msg-action" title="Copy" onclick="jarvis.copyMessage(this)">📋</button>
                <button class="msg-action" title="Regenerate" onclick="jarvis.regenerateResponse()">🔄</button>
            </div>
        `;
        
        this.chatMessages.appendChild(el);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        
        el.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    copyMessage(btn) {
        const msg = btn.closest('.message').querySelector('.message-text').textContent;
        navigator.clipboard.writeText(msg);
        this.showToast('Copied to clipboard', 'success');
    }

    regenerateResponse() {
        const messages = this.chatMessages?.querySelectorAll('.message');
        if (messages && messages.length >= 2) {
            const userMsg = messages[messages.length - 2];
            const text = userMsg.querySelector('.message-text').textContent;
            this.chatMessages.removeChild(messages[messages.length - 1]);
            this.sendChatMessage(text);
        }
    }

    clearChat() {
        this.chatMessages.innerHTML = `
            <div class="message jarvis-message">
                <div class="message-avatar">J</div>
                <div class="message-content">
                    <div class="message-text"><p>Greetings, sir. All systems operational. How may I assist you today?</p></div>
                    <div class="message-meta"><span class="message-time">Just now</span></div>
                </div>
            </div>
        `;
        this.showToast('Chat cleared', 'info');
    }

    exportChat() {
        const messages = [];
        this.chatMessages?.querySelectorAll('.message').forEach(msg => {
            const role = msg.classList.contains('user-message') ? 'User' : 'JARVIS';
            const text = msg.querySelector('.message-text').textContent;
            messages.push(`${role}: ${text}`);
        });
        
        const blob = new Blob([messages.join('\n\n')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'jarvis-chat.txt';
        a.click();
        URL.revokeObjectURL(url);
        this.showToast('Chat exported', 'success');
    }

    showTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.remove('hidden');
        }
    }

    hideTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.add('hidden');
        }
    }

    async fetchSystemStatus() {
        try {
            const response = await fetch('/api/system/status');
            const data = await response.json();
            
            if (data.success && data.system) {
                const sys = data.system;
                const cpuVal = sys.cpu.usage;
                const memVal = sys.memory.percent;
                
                this.cpuValue.textContent = `${cpuVal}%`;
                if (this.cpuBar) this.cpuBar.style.width = `${cpuVal}%`;
                this.miniCpu.textContent = `${cpuVal}%`;
                if (this.miniCpuBar) this.miniCpuBar.style.width = `${cpuVal}%`;
                
                this.ramValue.textContent = `${memVal}%`;
                if (this.ramBar) this.ramBar.style.width = `${memVal}%`;
                this.miniMem.textContent = `${memVal}%`;
                if (this.miniMemBar) this.miniMemBar.style.width = `${memVal}%`;
                
                if (this.diskValue) this.diskValue.textContent = `${sys.disk.percent}%`;
                
                this.updateHeroStats();
            }
        } catch (err) {
            console.error('System status failed');
        }
    }

    updateHeroStats() {
        this.uptime += 3;
        
        const uptimeEl = document.getElementById('heroUptime');
        if (uptimeEl) {
            const hours = Math.floor(this.uptime / 3600);
            const minutes = Math.floor((this.uptime % 3600) / 60);
            const seconds = this.uptime % 60;
            uptimeEl.textContent = `${hours}h ${minutes}m ${seconds}s`;
        }
        
        const reqEl = document.getElementById('heroRequests');
        if (reqEl) reqEl.textContent = this.requestCount;
        
        const memEl = document.getElementById('heroMemory');
        if (memEl && this.miniMem) memEl.textContent = this.miniMem.textContent;
    }

    startSystemMonitoring() {
        this.fetchSystemStatus();
        this.intervalId = setInterval(() => this.fetchSystemStatus(), 3000);
    }

    updateClock() {
        const update = () => {
            const timeEl = document.getElementById('systemTime');
            const dateEl = document.getElementById('systemDate');
            const now = new Date();
            
            if (timeEl) timeEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
            if (dateEl) dateEl.textContent = now.toLocaleDateString('en-US');
        };
        update();
        setInterval(update, 1000);
    }

    initHeroCanvas() {
        const canvas = document.getElementById('heroCanvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = canvas.offsetHeight;
        
        let angle = 0;
        const animate = () => {
            ctx.fillStyle = 'rgba(3, 5, 8, 0.1)';
            ctx.fillRect(0, 0, w, h);
            
            const cx = w / 2;
            const cy = h / 2;
            
            for (let i = 0; i < 8; i++) {
                const radius = 30 + i * 15;
                const rotation = angle + (i * Math.PI / 4);
                const x = cx + Math.cos(rotation) * radius * 0.3;
                const y = cy + Math.sin(rotation) * radius * 0.3;
                
                ctx.beginPath();
                ctx.arc(x, y, 4 - i * 0.3, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(0, 240, 255, ${0.8 - i * 0.1})`;
                ctx.fill();
            }
            
            angle += 0.02;
            requestAnimationFrame(animate);
        };
        
        animate();
    }

    initAmbientBg() {
        const bg = document.querySelector('.ambient-bg');
        if (!bg) return;
        
        const orbs = bg.querySelectorAll('.gradient-orb');
        let mouseX = 0, mouseY = 0;
        
        document.addEventListener('mousemove', (e) => {
            mouseX = e.clientX / window.innerWidth;
            mouseY = e.clientY / window.innerHeight;
        });
        
        orbs.forEach((orb, i) => {
            const speed = 0.001 + i * 0.0005;
            let pos = i * 120;
            
            const animate = () => {
                pos += speed * 1000;
                const x = 20 + Math.sin(pos * 0.01) * 30 + mouseX * 10;
                const y = 20 + Math.cos(pos * 0.015) * 30 + mouseY * 10;
                orb.style.left = `${x}%`;
                orb.style.top = `${y}%`;
                requestAnimationFrame(animate);
            };
            
            animate();
        });
    }

    async loadProcesses() {
        try {
            const response = await fetch('/api/system/processes?limit=20');
            const data = await response.json();
            
            const container = document.getElementById('processItems');
            if (data.success && data.processes) {
                container.innerHTML = data.processes.map(p => `
                    <div class="process-item" data-pid="${p.pid}">
                        <span>${p.pid}</span>
                        <span>${this.escapeHtml(p.name)}</span>
                        <span>${p.cpu}%</span>
                        <span>${p.memory}%</span>
                        <button class="kill-btn" onclick="event.stopPropagation(); jarvis.killProcess('${p.pid}')">✕</button>
                    </div>
                `).join('');
                
                container.querySelectorAll('.process-item').forEach(item => {
                    item.addEventListener('click', () => {
                        container.querySelectorAll('.process-item').forEach(i => i.classList.remove('selected'));
                        item.classList.add('selected');
                        this.selectedProcess = item.dataset.pid;
                    });
                });
            }
        } catch (err) {
            document.getElementById('processItems').innerHTML = '<div class="loading">Failed to load</div>';
        }
    }

    filterProcesses(query) {
        document.querySelectorAll('.process-item').forEach(item => {
            const name = item.querySelector('span:nth-child(2)').textContent.toLowerCase();
            item.style.display = name.includes(query.toLowerCase()) ? '' : 'none';
        });
    }

    async killProcess(pid) {
        pid = pid || this.selectedProcess;
        if (!pid) {
            this.addLog('No process selected', 'error');
            return;
        }
        try {
            await fetch('/api/system/process/kill', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pid: parseInt(pid) })
            });
            this.addLog(`Process ${pid} terminated`, 'success');
            this.showToast(`Process ${pid} terminated`, 'success');
            this.loadProcesses();
        } catch (err) {
            this.addLog('Failed to kill process', 'error');
        }
    }

    async loadFiles(path) {
        try {
            const response = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
            const data = await response.json();
            
            document.getElementById('currentPath').value = data.path || path;
            const container = document.getElementById('fileItems');
            
            if (data.success && data.files) {
                container.innerHTML = data.files.map(f => `
                    <div class="file-item ${f.is_dir ? 'directory' : ''}" data-path="${f.name}">
                        <span>${f.is_dir ? '📁 ' : '📄 '}${this.escapeHtml(f.name)}</span>
                        <span>${this.formatSize(f.size)}</span>
                        <span>${this.formatDate(f.modified)}</span>
                    </div>
                `).join('');
                
                container.querySelectorAll('.file-item').forEach(item => {
                    item.addEventListener('click', () => {
                        if (item.classList.contains('directory')) {
                            this.loadFiles(item.dataset.path);
                        }
                    });
                });
            }
        } catch (err) {
            document.getElementById('fileItems').innerHTML = '<div class="loading">Failed to load</div>';
        }
    }

    navigateUp() {
        const parts = this.currentPath.split(/[/\\]/);
        parts.pop();
        this.loadFiles(parts.join('/') || '.');
    }

    navigateToPath() {
        this.loadFiles(document.getElementById('currentPath').value);
    }

    formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
        if (bytes < 1024*1024*1024) return (bytes/1024/1024).toFixed(1) + ' MB';
        return (bytes/1024/1024/1024).toFixed(1) + ' GB';
    }

    formatDate(isoDate) {
        try { return new Date(isoDate).toLocaleString(); } catch { return '-'; }
    }

    async loadObservation() {
        try {
            const response = await fetch('/api/observation/status');
            const data = await response.json();
            
            if (data.cpu !== undefined) {
                document.getElementById('obsCpu').textContent = `${data.cpu}%`;
                this.cpuHistory.push(data.cpu);
                if (this.cpuHistory.length > 20) this.cpuHistory.shift();
            }
            if (data.memory !== undefined) {
                document.getElementById('obsMem').textContent = `${data.memory}%`;
                this.memHistory.push(data.memory);
                if (this.memHistory.length > 20) this.memHistory.shift();
            }
            this.drawCharts();
        } catch (err) {}

        this.loadEvents();
    }

    async loadEvents() {
        try {
            const response = await fetch('/api/observation/events?limit=15');
            const data = await response.json();
            
            const container = document.getElementById('eventsList');
            if (data.events && data.events.length > 0) {
                container.innerHTML = data.events.map(e => `
                    <div class="event-item">${this.escapeHtml(e.event || e.type || 'Event')}</div>
                `).join('');
            } else {
                container.innerHTML = '<div class="loading">No events</div>';
            }
        } catch (err) {
            document.getElementById('eventsList').innerHTML = '<div class="loading">Unavailable</div>';
        }
    }

    initCharts() {
        this.cpuCanvas = document.getElementById('cpuCanvas');
        this.memCanvas = document.getElementById('memCanvas');
        this.netCanvas = document.getElementById('netCanvas');
    }

    drawCharts() {
        const draw = (canvas, data, color1, color2) => {
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const w = canvas.width = canvas.offsetWidth;
            const h = canvas.height = canvas.offsetHeight;
            ctx.clearRect(0, 0, w, h);
            if (data.length < 2) return;
            
            const gradient = ctx.createLinearGradient(0, 0, 0, h);
            gradient.addColorStop(0, color1);
            gradient.addColorStop(1, 'transparent');
            
            const step = w / (data.length - 1);
            ctx.beginPath();
            ctx.moveTo(0, h);
            data.forEach((val, i) => ctx.lineTo(i * step, h - (val/100)*h));
            ctx.lineTo(w, h);
            ctx.closePath();
            ctx.fillStyle = gradient;
            ctx.fill();
            
            ctx.beginPath();
            data.forEach((val, i) => {
                if (i === 0) ctx.moveTo(i * step, h - (val/100)*h);
                else ctx.lineTo(i * step, h - (val/100)*h);
            });
            ctx.strokeStyle = color2;
            ctx.lineWidth = 2;
            ctx.stroke();
        };
        draw(this.cpuCanvas, this.cpuHistory, 'rgba(0, 240, 255, 0.3)', '#00f0ff');
        draw(this.memCanvas, this.memHistory, 'rgba(0, 255, 136, 0.3)', '#00ff88');
    }

    async loadKnowledge() {
        try {
            const response = await fetch('/api/knowledge');
            const data = await response.json();
            
            if (data.success) {
                document.getElementById('totalKnowledge').textContent = data.stats?.total_entries || 0;
                document.getElementById('totalPatterns').textContent = data.stats?.total_patterns || 0;
                document.getElementById('totalTraining').textContent = data.entries?.length || 0;
                
                const list = document.getElementById('knowledgeList');
                if (data.entries && data.entries.length > 0) {
                    list.innerHTML = data.entries.slice(0, 10).map(e => `
                        <div class="event-item"><strong>${this.escapeHtml(e.key)}</strong>: ${this.escapeHtml(e.value)}</div>
                    `).join('');
                } else {
                    list.innerHTML = '<div class="loading">No knowledge entries</div>';
                }
            }
        } catch (err) {}
    }

    async addKnowledge() {
        const key = document.getElementById('knowledgeKey').value.trim();
        const value = document.getElementById('knowledgeValue').value.trim();
        const category = document.getElementById('knowledgeCategory').value;
        
        if (!key || !value) {
            this.addLog('Key and value required', 'error');
            return;
        }

        try {
            await fetch('/api/knowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value, category })
            });
            this.addLog(`Knowledge added: ${key}`, 'success');
            this.showToast('Knowledge added', 'success');
            document.getElementById('knowledgeKey').value = '';
            document.getElementById('knowledgeValue').value = '';
            this.loadKnowledge();
        } catch (err) {
            this.addLog('Failed to add knowledge', 'error');
        }
    }

    async loadTraining() {
        try {
            const response = await fetch('/api/training');
            const data = await response.json();
            
            if (data.success) {
                const stats = data.stats;
                document.getElementById('vocabSize').textContent = stats?.model_stats?.vocabulary_size || 0;
                document.getElementById('totalSamples').textContent = stats?.total_samples || 0;
                document.getElementById('avgRating').textContent = stats?.avg_rating || 'N/A';
                
                const container = document.getElementById('trainingSamples');
                if (data.recent_samples && data.recent_samples.length > 0) {
                    container.innerHTML = data.recent_samples.slice(0, 5).map(s => `
                        <div class="event-item">${this.escapeHtml(s.input_text)} → ${this.escapeHtml(s.output_text)}</div>
                    `).join('');
                } else {
                    container.innerHTML = '<div class="loading">No training samples</div>';
                }
            }
        } catch (err) {}
    }

    async addTrainingSample() {
        const input = document.getElementById('trainInput').value.trim();
        const output = document.getElementById('trainOutput').value.trim();
        const validated = document.getElementById('trainValidated').checked;
        
        if (!input || !output) {
            this.addLog('Input and output required', 'error');
            return;
        }

        try {
            await fetch('/api/training', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input, output, validated })
            });
            this.addLog('Training sample added', 'success');
            this.showToast('Training sample added', 'success');
            document.getElementById('trainInput').value = '';
            document.getElementById('trainOutput').value = '';
            this.loadTraining();
        } catch (err) {
            this.addLog('Training failed', 'error');
        }
    }

    async loadAIStatus() {
        try {
            const response = await fetch('/api/ai/status');
            const data = await response.json();
            
            const container = document.getElementById('aiStatus');
            if (data.success) {
                const s = data.status;
                container.innerHTML = `
                    <div class="status-grid-item">
                        <span class="sgi-label">Ollama</span>
                        <span class="sgi-value ${s.ollama_available ? 'online' : 'offline'}">${s.ollama_available ? '✓ Online' : '✗ Offline'}</span>
                    </div>
                    <div class="status-grid-item">
                        <span class="sgi-label">Models</span>
                        <span class="sgi-value">${s.ollama_models?.join(', ') || 'None'}</span>
                    </div>
                    <div class="status-grid-item">
                        <span class="sgi-label">Embeddings</span>
                        <span class="sgi-value ${s.embedding_model ? 'online' : 'offline'}">${s.embedding_model ? '✓ Enabled' : '✗ Disabled'}</span>
                    </div>
                    <div class="status-grid-item">
                        <span class="sgi-label">Vector Store</span>
                        <span class="sgi-value ${s.vector_store ? 'online' : 'offline'}">${s.vector_store ? '✓ Active' : '✗ Inactive'}</span>
                    </div>
                `;
            }
        } catch (err) {}
    }

    async doWebSearch() {
        const query = document.getElementById('searchQuery').value.trim();
        if (!query) return;
        
        try {
            const response = await fetch(`/api/web/search?q=${encodeURIComponent(query)}&num=5`);
            const data = await response.json();
            
            const container = document.getElementById('searchResults');
            if (data.success && data.results) {
                container.innerHTML = data.results.map(r => `
                    <div class="search-result">
                        <a href="${r.url}" target="_blank">${this.escapeHtml(r.title)}</a>
                        <p>${this.escapeHtml(r.snippet)}</p>
                    </div>
                `).join('');
                this.addLog(`Search: ${query}`, 'info');
            }
        } catch (err) {
            this.addLog('Search failed', 'error');
        }
    }

    async getWeather() {
        try {
            const response = await fetch('/api/web/weather');
            const data = await response.json();
            
            if (data.success) {
                document.getElementById('weatherTemp').textContent = `${data.temperature}°C`;
                document.getElementById('weatherCondition').textContent = data.description || 'Clear';
                document.getElementById('weatherHumidity').textContent = `${data.humidity || '--'}%`;
                document.getElementById('weatherWind').textContent = `${data.wind_speed || '--'} km/h`;
            }
        } catch (err) {}
    }

    async getNews() {
        const category = document.getElementById('newsCategory')?.value || 'tech';
        try {
            const response = await fetch(`/api/web/news?category=${category}&limit=5`);
            const data = await response.json();
            
            const container = document.getElementById('newsList');
            if (data.success && data.articles) {
                container.innerHTML = data.articles.map(a => `
                    <div class="news-item"><a href="${a.link}" target="_blank">${this.escapeHtml(a.title)}</a></div>
                `).join('');
            }
        } catch (err) {}
    }

    async getWikiSummary() {
        const query = document.getElementById('wikiQuery').value.trim();
        if (!query) return;
        
        try {
            const response = await fetch(`/api/web/wikipedia?q=${encodeURIComponent(query)}&action=summary`);
            const data = await response.json();
            
            const container = document.getElementById('wikiResult');
            if (data.success) {
                container.innerHTML = `<p>${this.escapeHtml(data.extract)}</p>`;
            }
        } catch (err) {}
    }

    async copyToClipboard() {
        const text = document.getElementById('clipboardText').value;
        try {
            await fetch('/api/system/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            this.addLog('Copied to clipboard', 'success');
            this.showToast('Copied to clipboard', 'success');
        } catch (err) {}
    }

    async takeScreenshot() {
        try {
            const response = await fetch('/api/system/screenshot', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                this.addLog(`Screenshot saved: ${data.filepath}`, 'success');
                this.showToast('Screenshot captured', 'success');
            }
        } catch (err) {}
    }

    async launchApp() {
        const app = document.getElementById('appSelect').value;
        try {
            await fetch('/api/system/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ app })
            });
            this.addLog(`Launched: ${app}`, 'success');
            this.showToast(`Launched: ${app}`, 'success');
        } catch (err) {}
    }

    async lockScreen() {
        try {
            await fetch('/api/system/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'lock' })
            });
            this.addLog('Screen locked', 'info');
        } catch (err) {}
    }

    async sleepSystem() {
        try {
            await fetch('/api/system/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'sleep' })
            });
        } catch (err) {}
    }

    speakText() {
        const text = this.transcript?.textContent || 'Hello, I am Jarvis.';
        fetch('/api/speech/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
    }

    addLog(message, type = 'info') {
        const now = new Date();
        const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.innerHTML = `<span class="log-time">${time}</span><span class="log-message">${this.escapeHtml(message)}</span>`;
        
        this.logsContainer.appendChild(entry);
        this.logsContainer.scrollTop = this.logsContainer.scrollHeight;
        
        if (this.logsContainer.children.length > 50) {
            this.logsContainer.removeChild(this.logsContainer.firstChild);
        }
    }

    clearLogs() {
        this.logsContainer.innerHTML = '';
        this.addLog('Logs cleared', 'info');
    }

    setStatus(status, text) {
        if (this.statusBadge) {
            this.statusBadge.className = `status-badge ${status}`;
        }
        if (this.statusText) this.statusText.textContent = text;
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
            <span class="toast-message">${this.escapeHtml(message)}</span>
        `;
        
        this.toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100px)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('JARVIS: Initializing...');
    updateLoadingStatus('Loading dependencies...');
    
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js';
    script.onload = () => {
        console.log('JARVIS: Socket.IO loaded');
        updateLoadingStatus('Starting dashboard...');
        window.jarvis = new JarvisDashboard();
        window.jarvis.addLog('Dashboard initialized', 'success');
        window.jarvis.showToast('JARVIS ready', 'success');
        
        // Remove loading overlay
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.transition = 'opacity 0.5s';
            overlay.style.opacity = '0';
            setTimeout(() => overlay.remove(), 500);
        }
    };
    script.onerror = (err) => {
        console.error('JARVIS: Failed to load Socket.IO', err);
        updateLoadingStatus('Error loading dependencies', true);
    };
    document.head.appendChild(script);
});

function updateLoadingStatus(text, isError = false) {
    const el = document.getElementById('loadingStatus');
    if (el) el.textContent = text;
    if (isError) el.style.color = '#ff4757';
}

window.speechSynthesis?.addEventListener('voiceschanged', () => {
    console.log('TTS voices loaded');
});