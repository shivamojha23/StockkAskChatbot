/**
 * chatbot-widget.js — StockkBot Embeddable Chat Widget
 * ======================================================
 * Deliverable C: A self-contained, embeddable Web Component.
 *
 * HOW TO EMBED (in any HTML page):
 *   <script
 *     src="https://your-cdn.com/chatbot-widget.js"
 *     data-api-url="https://your-api.com"
 *     data-theme="dark"
 *     defer
 *   ></script>
 *
 * OR instantiate programmatically:
 *   StockkBotWidget.init({
 *     apiUrl: 'https://your-api.com',
 *     theme: 'dark'
 *   });
 *
 * Architecture:
 *   - Zero dependencies (pure Vanilla JS)
 *   - Encapsulated in a Web Component (Shadow DOM)
 *   - Session UUID stored in sessionStorage
 *   - Real-time SSE streaming
 *   - Fully responsive, accessible (ARIA labels)
 *   - SEBI compliance disclaimer shown on first open
 */

(function (global) {
  'use strict';

  // ─────────────────────────────────────────────────────────────────────────
  // Configuration
  // ─────────────────────────────────────────────────────────────────────────

  const DEFAULT_CONFIG = {
    apiUrl: 'http://localhost:8000',
    theme: 'dark',           // 'dark' | 'light'
    position: 'bottom-right', // 'bottom-right' | 'bottom-left'
    primaryColor: '#00C896',  // StockkAsk brand green
    maxHistoryLength: 20,     // Max messages to send as context
    botName: 'StockkBot',
    botSubtitle: 'Platform Guide · Powered by Indira Securities',
    welcomeMessage:
      "Hi! I'm StockkBot, your guide to the StockkAsk platform. I can help you understand features like the Smart Screener, Live News, and financial terms. Ask me anything! 🚀",
    disclaimerText:
      '⚠️ StockkBot is a platform guide only. It does NOT provide financial advice, stock tips, or investment recommendations. Always do your own research.',
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Session Management
  // ─────────────────────────────────────────────────────────────────────────

  const SessionManager = {
    KEY: 'stockkbot_session_id',
    HISTORY_KEY: 'stockkbot_history',

    getOrCreate() {
      let sessionId = sessionStorage.getItem(this.KEY);
      if (!sessionId) {
        sessionId = this._generateUUID();
        sessionStorage.setItem(this.KEY, sessionId);
      }
      return sessionId;
    },

    _generateUUID() {
      // RFC 4122 UUID v4
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    },

    saveHistory(messages) {
      try {
        // Store last 20 messages only
        const trimmed = messages.slice(-DEFAULT_CONFIG.maxHistoryLength);
        sessionStorage.setItem(this.HISTORY_KEY, JSON.stringify(trimmed));
      } catch (e) {
        console.warn('[StockkBot] Could not save history to sessionStorage.', e);
      }
    },

    loadHistory() {
      try {
        const raw = sessionStorage.getItem(this.HISTORY_KEY);
        return raw ? JSON.parse(raw) : [];
      } catch {
        return [];
      }
    },

    clear() {
      sessionStorage.removeItem(this.KEY);
      sessionStorage.removeItem(this.HISTORY_KEY);
    },
  };

  // ─────────────────────────────────────────────────────────────────────────
  // API Client
  // ─────────────────────────────────────────────────────────────────────────

  const ApiClient = {
    /**
     * Send a chat message and return an SSE ReadableStream.
     * @param {string} apiUrl
     * @param {string} sessionId
     * @param {string} message
     * @param {Array}  history
     * @returns {Promise<Response>}
     */
    async sendMessage(apiUrl, sessionId, message, history) {
      const response = await fetch(`${apiUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message,
          history: history.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!response.ok) {
        const errText = await response.text().catch(() => 'Unknown error');
        throw new Error(`API error ${response.status}: ${errText}`);
      }

      return response;
    },

    /**
     * Parse an SSE stream and call onToken for each text chunk.
     * @param {Response} response
     * @param {function} onToken      Called with each text token string
     * @param {function} onComplete   Called when stream ends
     * @param {function} onError      Called on error
     * @returns {Promise<void>}
     */
    async readStream(response, onToken, onComplete, onError) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop(); // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6).trim();
            if (data === '[DONE]') {
              onComplete();
              return;
            }
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) {
                onError(new Error(parsed.error));
                return;
              }
              if (parsed.token) {
                onToken(parsed.token);
              }
            } catch {
              // Skip malformed SSE lines
            }
          }
        }
        onComplete();
      } catch (err) {
        onError(err);
      } finally {
        reader.releaseLock();
      }
    },
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Styles
  // ─────────────────────────────────────────────────────────────────────────

  function buildStyles(config) {
    const isDark = config.theme === 'dark';
    const primary = config.primaryColor;
    const pos = config.position === 'bottom-left'
      ? 'left: 24px; right: auto;'
      : 'right: 24px; left: auto;';

    return `
      :host { all: initial; }

      /* ── Launcher bubble ── */
      .launcher {
        position: fixed;
        bottom: 24px;
        ${pos}
        z-index: 999999;
        width: 58px;
        height: 58px;
        border-radius: 50%;
        background: ${primary};
        border: none;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(0,0,0,0.35), 0 0 0 0 ${primary}40;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        animation: pulse-ring 2.5s ease-out infinite;
        outline: none;
      }
      .launcher:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(0,0,0,0.45); }
      .launcher:active { transform: scale(0.96); }
      .launcher svg { width: 28px; height: 28px; fill: #fff; transition: opacity 0.2s; }
      .launcher .icon-close { display: none; }
      .launcher.open .icon-chat { display: none; }
      .launcher.open .icon-close { display: block; }

      @keyframes pulse-ring {
        0%   { box-shadow: 0 4px 20px rgba(0,0,0,0.35), 0 0 0 0 ${primary}50; }
        70%  { box-shadow: 0 4px 20px rgba(0,0,0,0.35), 0 0 0 14px ${primary}00; }
        100% { box-shadow: 0 4px 20px rgba(0,0,0,0.35), 0 0 0 0 ${primary}00; }
      }

      /* ── Chat window ── */
      .chat-window {
        position: fixed;
        bottom: 96px;
        ${pos}
        z-index: 999998;
        width: 375px;
        max-width: calc(100vw - 32px);
        height: 560px;
        max-height: calc(100vh - 120px);
        border-radius: 20px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        background: ${isDark ? '#0F1923' : '#FFFFFF'};
        box-shadow: 0 12px 48px rgba(0,0,0,0.4), 0 2px 8px rgba(0,0,0,0.2);
        transform: scale(0.85) translateY(20px);
        opacity: 0;
        pointer-events: none;
        transition: transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1),
                    opacity 0.22s ease;
        font-family: 'Segoe UI', 'Inter', system-ui, sans-serif;
      }
      .chat-window.visible {
        transform: scale(1) translateY(0);
        opacity: 1;
        pointer-events: all;
      }

      /* ── Header ── */
      .header {
        background: linear-gradient(135deg, #0A1628 0%, #0D2137 100%);
        padding: 16px 18px;
        display: flex;
        align-items: center;
        gap: 12px;
        border-bottom: 1px solid rgba(255,255,255,0.07);
        flex-shrink: 0;
      }
      .header-avatar {
        width: 40px; height: 40px;
        border-radius: 50%;
        background: ${primary};
        display: flex; align-items: center; justify-content: center;
        font-size: 18px;
        flex-shrink: 0;
      }
      .header-text { flex: 1; min-width: 0; }
      .header-name {
        font-size: 15px; font-weight: 700;
        color: #FFFFFF; letter-spacing: 0.2px;
      }
      .header-sub {
        font-size: 11px; color: rgba(255,255,255,0.55);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .status-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: ${primary};
        box-shadow: 0 0 0 3px ${primary}30;
        animation: blink 2s ease-in-out infinite;
      }
      @keyframes blink {
        0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
      }
      .btn-clear {
        background: none; border: none; cursor: pointer;
        color: rgba(255,255,255,0.4); font-size: 12px;
        padding: 4px 8px; border-radius: 6px;
        transition: color 0.15s, background 0.15s;
      }
      .btn-clear:hover { color: #fff; background: rgba(255,255,255,0.08); }

      /* ── Disclaimer banner ── */
      .disclaimer {
        background: ${isDark ? 'rgba(255,200,0,0.08)' : '#FFFBEB'};
        border-bottom: 1px solid ${isDark ? 'rgba(255,200,0,0.15)' : '#FDE68A'};
        padding: 9px 14px;
        font-size: 11px;
        color: ${isDark ? '#F0C040' : '#92400E'};
        line-height: 1.5;
        flex-shrink: 0;
      }

      /* ── Messages area ── */
      .messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px 14px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        scroll-behavior: smooth;
      }
      .messages::-webkit-scrollbar { width: 4px; }
      .messages::-webkit-scrollbar-track { background: transparent; }
      .messages::-webkit-scrollbar-thumb {
        background: ${isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)'};
        border-radius: 4px;
      }

      /* ── Bubble ── */
      .bubble-row {
        display: flex;
        gap: 8px;
        max-width: 100%;
      }
      .bubble-row.user { justify-content: flex-end; }
      .bubble-row.assistant { justify-content: flex-start; }

      .bubble {
        max-width: 82%;
        padding: 10px 14px;
        border-radius: 16px;
        font-size: 13.5px;
        line-height: 1.55;
        word-break: break-word;
        position: relative;
      }
      .bubble-row.user .bubble {
        background: ${primary};
        color: #fff;
        border-bottom-right-radius: 4px;
      }
      .bubble-row.assistant .bubble {
        background: ${isDark ? '#1A2535' : '#F3F4F6'};
        color: ${isDark ? '#E8EDF5' : '#1F2937'};
        border-bottom-left-radius: 4px;
      }
      .bubble-row.assistant .bubble.streaming::after {
        content: '▍';
        display: inline-block;
        animation: cursor-blink 0.7s step-end infinite;
        color: ${primary};
        margin-left: 2px;
        font-size: 14px;
      }
      @keyframes cursor-blink {
        0%, 100% { opacity: 1; } 50% { opacity: 0; }
      }

      /* ── Typing indicator ── */
      .typing-indicator {
        display: flex; align-items: center; gap: 5px;
        padding: 10px 14px;
        background: ${isDark ? '#1A2535' : '#F3F4F6'};
        border-radius: 16px;
        border-bottom-left-radius: 4px;
        width: fit-content;
      }
      .typing-dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: ${primary}; opacity: 0.6;
      }
      .typing-dot:nth-child(1) { animation: bounce 1.2s ease-in-out 0s infinite; }
      .typing-dot:nth-child(2) { animation: bounce 1.2s ease-in-out 0.2s infinite; }
      .typing-dot:nth-child(3) { animation: bounce 1.2s ease-in-out 0.4s infinite; }
      @keyframes bounce {
        0%, 60%, 100% { transform: translateY(0); }
        30% { transform: translateY(-6px); }
      }

      /* ── Quick suggestion chips ── */
      .suggestions {
        padding: 0 14px 10px;
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        flex-shrink: 0;
      }
      .chip {
        background: ${isDark ? 'rgba(0,200,150,0.1)' : 'rgba(0,200,150,0.08)'};
        color: ${primary};
        border: 1px solid ${isDark ? 'rgba(0,200,150,0.25)' : 'rgba(0,200,150,0.3)'};
        border-radius: 20px;
        padding: 5px 11px;
        font-size: 11.5px;
        cursor: pointer;
        transition: all 0.15s;
        white-space: nowrap;
      }
      .chip:hover {
        background: ${primary};
        color: #fff;
        border-color: ${primary};
      }

      /* ── Input area ── */
      .input-area {
        padding: 12px 14px 14px;
        border-top: 1px solid ${isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.07)'};
        display: flex;
        gap: 8px;
        align-items: flex-end;
        flex-shrink: 0;
        background: ${isDark ? '#0F1923' : '#FFFFFF'};
      }
      .input-box {
        flex: 1;
        min-height: 40px;
        max-height: 100px;
        resize: none;
        background: ${isDark ? '#1A2535' : '#F9FAFB'};
        color: ${isDark ? '#E8EDF5' : '#111827'};
        border: 1.5px solid ${isDark ? 'rgba(255,255,255,0.1)' : '#E5E7EB'};
        border-radius: 12px;
        padding: 10px 13px;
        font-size: 13.5px;
        font-family: inherit;
        line-height: 1.4;
        outline: none;
        transition: border-color 0.15s;
        overflow-y: auto;
      }
      .input-box::placeholder { color: ${isDark ? 'rgba(255,255,255,0.3)' : '#9CA3AF'}; }
      .input-box:focus { border-color: ${primary}; }

      .btn-send {
        width: 40px; height: 40px; min-width: 40px;
        border-radius: 12px;
        background: ${primary};
        border: none;
        cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s, transform 0.1s, opacity 0.15s;
        flex-shrink: 0;
      }
      .btn-send:hover { background: #00a87e; }
      .btn-send:active { transform: scale(0.93); }
      .btn-send:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
      .btn-send svg { width: 18px; height: 18px; fill: #fff; }

      /* ── Footer branding ── */
      .footer-brand {
        text-align: center;
        font-size: 10.5px;
        color: ${isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.25)'};
        padding: 0 14px 10px;
        flex-shrink: 0;
      }
      .footer-brand a { color: inherit; text-decoration: none; }
      .footer-brand a:hover { text-decoration: underline; }

      /* ── Mobile ── */
      @media (max-width: 420px) {
        .chat-window {
          width: calc(100vw - 16px);
          height: calc(100vh - 88px);
          bottom: 80px;
          right: 8px;
          left: 8px;
          border-radius: 16px;
        }
        .launcher { bottom: 16px; right: 16px; }
      }
    `;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Web Component
  // ─────────────────────────────────────────────────────────────────────────

  class StockkBotWidget extends HTMLElement {
    constructor() {
      super();
      this._config = { ...DEFAULT_CONFIG };
      this._isOpen = false;
      this._isStreaming = false;
      this._sessionId = null;
      this._messages = []; // { role: 'user'|'assistant', content: string }
      this._abortController = null;

      // Attach Shadow DOM for full style encapsulation
      this.attachShadow({ mode: 'open' });
    }

    connectedCallback() {
      // Read config from dataset attributes
      const ds = this.dataset;
      if (ds.apiUrl)       this._config.apiUrl       = ds.apiUrl;
      if (ds.theme)        this._config.theme         = ds.theme;
      if (ds.position)     this._config.position      = ds.position;
      if (ds.primaryColor) this._config.primaryColor  = ds.primaryColor;

      this._sessionId = SessionManager.getOrCreate();
      this._messages  = SessionManager.loadHistory();

      this._render();
      this._bindEvents();

      // If no history, show the welcome message
      if (this._messages.length === 0) {
        this._addBotMessage(this._config.welcomeMessage);
      } else {
        this._renderMessages();
      }
    }

    // ── Render ──────────────────────────────────────────────────────────

    _render() {
      const shadow = this.shadowRoot;
      shadow.innerHTML = `
        <style>${buildStyles(this._config)}</style>

        <!-- Launcher Bubble -->
        <button class="launcher" aria-label="Open StockkBot chat" title="Chat with StockkBot">
          <svg class="icon-chat" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.477 2 2 6.038 2 11c0 2.56 1.07 4.87 2.793 6.55L4 22l4.59-1.53C9.66 20.81 10.8 21 12 21c5.523 0 10-4.038 10-9s-4.477-9-10-9z"/>
          </svg>
          <svg class="icon-close" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 6L6 18M6 6l12 12" stroke="#fff" stroke-width="2.5" stroke-linecap="round" fill="none"/>
          </svg>
        </button>

        <!-- Chat Window -->
        <div class="chat-window" role="dialog" aria-label="StockkBot chat" aria-modal="true">

          <!-- Header -->
          <div class="header">
            <div class="header-avatar">🤖</div>
            <div class="header-text">
              <div class="header-name">${this._config.botName}</div>
              <div class="header-sub">${this._config.botSubtitle}</div>
            </div>
            <div class="status-dot" title="Online"></div>
            <button class="btn-clear" title="Clear conversation" aria-label="Clear conversation">Clear</button>
          </div>

          <!-- Disclaimer -->
          <div class="disclaimer" role="note">
            ${this._config.disclaimerText}
          </div>

          <!-- Messages -->
          <div class="messages" id="messages" role="log" aria-live="polite" aria-label="Chat messages"></div>

          <!-- Quick Suggestions -->
          <div class="suggestions" id="suggestions">
            <button class="chip" data-msg="What is StockkAsk?">What is StockkAsk?</button>
            <button class="chip" data-msg="What is the Smart Screener?">Smart Screener</button>
            <button class="chip" data-msg="What does 'Moat' mean?">What's a Moat?</button>
            <button class="chip" data-msg="How do I see live prices?">Live Prices</button>
          </div>

          <!-- Input -->
          <div class="input-area">
            <textarea
              class="input-box"
              id="input-box"
              placeholder="Ask about StockkAsk features..."
              rows="1"
              maxlength="2000"
              aria-label="Type your message"
            ></textarea>
            <button class="btn-send" id="btn-send" aria-label="Send message" disabled>
              <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/>
              </svg>
            </button>
          </div>

          <!-- Footer -->
          <div class="footer-brand">
            Powered by <a href="https://stockk.trade/stockkask/" target="_blank" rel="noopener">StockkAsk</a>
            &nbsp;·&nbsp; Indira Securities Pvt. Ltd.
          </div>

        </div>
      `;
    }

    // ── Event Binding ────────────────────────────────────────────────────

    _bindEvents() {
      const shadow = this.shadowRoot;
      const launcher   = shadow.querySelector('.launcher');
      const inputBox   = shadow.querySelector('#input-box');
      const sendBtn    = shadow.querySelector('#btn-send');
      const clearBtn   = shadow.querySelector('.btn-clear');
      const suggestions = shadow.querySelector('#suggestions');

      launcher.addEventListener('click', () => this._toggleChat());

      inputBox.addEventListener('input', () => {
        this._autoResize(inputBox);
        sendBtn.disabled = !inputBox.value.trim() || this._isStreaming;
      });

      inputBox.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (!sendBtn.disabled) this._handleSend();
        }
      });

      sendBtn.addEventListener('click', () => this._handleSend());

      clearBtn.addEventListener('click', () => this._clearConversation());

      suggestions.addEventListener('click', (e) => {
        const chip = e.target.closest('.chip');
        if (chip) {
          const msg = chip.dataset.msg;
          if (msg) this._sendMessage(msg);
        }
      });
    }

    // ── Chat Toggle ──────────────────────────────────────────────────────

    _toggleChat() {
      this._isOpen = !this._isOpen;
      const shadow = this.shadowRoot;
      const window = shadow.querySelector('.chat-window');
      const launcher = shadow.querySelector('.launcher');

      window.classList.toggle('visible', this._isOpen);
      launcher.classList.toggle('open', this._isOpen);
      launcher.setAttribute('aria-expanded', String(this._isOpen));

      if (this._isOpen) {
        this._scrollToBottom();
        // Focus input after animation
        setTimeout(() => {
          shadow.querySelector('#input-box')?.focus();
        }, 300);
      }
    }

    // ── Message Handling ─────────────────────────────────────────────────

    _handleSend() {
      const inputBox = this.shadowRoot.querySelector('#input-box');
      const text = inputBox.value.trim();
      if (!text || this._isStreaming) return;
      inputBox.value = '';
      this._autoResize(inputBox);
      this._sendMessage(text);
    }

    async _sendMessage(text) {
      // Add user message to UI and history
      this._messages.push({ role: 'user', content: text });
      this._renderMessages();
      this._scrollToBottom();
      this._hideSuggestions();

      // Lock UI
      this._setStreaming(true);

      // Show typing indicator
      const typingId = this._showTyping();

      try {
        // Build history for API (exclude the current message we just pushed)
        const historyForApi = this._messages.slice(0, -1);

        const response = await ApiClient.sendMessage(
          this._config.apiUrl,
          this._sessionId,
          text,
          historyForApi
        );

        // Remove typing indicator, add empty assistant bubble
        this._removeTyping(typingId);
        const bubbleEl = this._addStreamingBubble();

        let fullText = '';

        await ApiClient.readStream(
          response,
          (token) => {
            fullText += token;
            bubbleEl.innerHTML = this._parseSafeHtml(fullText);
            this._scrollToBottom();
          },
          () => {
            // Stream complete
            bubbleEl.classList.remove('streaming');
            this._messages.push({ role: 'assistant', content: fullText });
            SessionManager.saveHistory(this._messages);
            this._setStreaming(false);
            this._showSuggestions();
          },
          (err) => {
            console.error('[StockkBot] Stream error:', err);
            bubbleEl.classList.remove('streaming');
            bubbleEl.textContent =
              '⚠️ Sorry, I encountered an error. Please try again.';
            this._setStreaming(false);
            this._showSuggestions();
          }
        );
      } catch (err) {
        console.error('[StockkBot] Request error:', err);
        this._removeTyping(typingId);
        this._addBotMessage(
          '⚠️ Unable to reach StockkBot. Please check your connection and try again.'
        );
        this._setStreaming(false);
        this._showSuggestions();
      }
    }

    // ── DOM Helpers ──────────────────────────────────────────────────────

    _getMessagesContainer() {
      return this.shadowRoot.querySelector('#messages');
    }

    _renderMessages() {
      const container = this._getMessagesContainer();
      container.innerHTML = '';
      for (const msg of this._messages) {
        const row = this._createBubbleEl(msg.role, msg.content);
        container.appendChild(row);
      }
    }

    _createBubbleEl(role, content, isStreaming = false) {
      const row = document.createElement('div');
      row.className = `bubble-row ${role}`;

      const bubble = document.createElement('div');
      bubble.className = `bubble${isStreaming ? ' streaming' : ''}`;
      
      if (role === 'assistant') {
        bubble.innerHTML = this._parseSafeHtml(content);
      } else {
        bubble.textContent = content;
      }

      row.appendChild(bubble);
      return row;
    }

    _parseSafeHtml(text) {
      if (!text) return '';
      // 1. Escape HTML special characters to prevent XSS
      const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');

      // 2. Parse valid HTTP/HTTPS URLs and format them as safe clickable links
      const urlRegex = /(https?:\/\/[^\s\)]+)/g;
      return escaped.replace(urlRegex, (url) => {
        return `<a href="${url}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: underline;">${url}</a>`;
      });
    }

    _addBotMessage(content) {
      const container = this._getMessagesContainer();
      const row = this._createBubbleEl('assistant', content);
      container.appendChild(row);
      this._scrollToBottom();
    }

    _addStreamingBubble() {
      const container = this._getMessagesContainer();
      const row = this._createBubbleEl('assistant', '', true);
      const bubble = row.querySelector('.bubble');
      container.appendChild(row);
      this._scrollToBottom();
      return bubble;
    }

    _showTyping() {
      const container = this._getMessagesContainer();
      const id = 'typing-' + Date.now();
      const row = document.createElement('div');
      row.className = 'bubble-row assistant';
      row.id = id;
      row.innerHTML = `
        <div class="typing-indicator" aria-label="StockkBot is thinking">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      `;
      container.appendChild(row);
      this._scrollToBottom();
      return id;
    }

    _removeTyping(id) {
      this.shadowRoot.getElementById(id)?.remove();
    }

    _scrollToBottom() {
      const container = this._getMessagesContainer();
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    }

    _setStreaming(value) {
      this._isStreaming = value;
      const sendBtn = this.shadowRoot.querySelector('#btn-send');
      const inputBox = this.shadowRoot.querySelector('#input-box');
      if (sendBtn) sendBtn.disabled = value || !inputBox?.value.trim();
    }

    _autoResize(textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 100) + 'px';
    }

    _hideSuggestions() {
      const sug = this.shadowRoot.querySelector('#suggestions');
      if (sug) sug.style.display = 'none';
    }

    _showSuggestions() {
      const sug = this.shadowRoot.querySelector('#suggestions');
      if (sug) sug.style.display = 'flex';
    }

    _clearConversation() {
      this._messages = [];
      SessionManager.clear();
      this._sessionId = SessionManager.getOrCreate();
      this._renderMessages();
      this._addBotMessage(this._config.welcomeMessage);
      this._showSuggestions();
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Register & Auto-Init
  // ─────────────────────────────────────────────────────────────────────────

  if (!customElements.get('stockkbot-widget')) {
    customElements.define('stockkbot-widget', StockkBotWidget);
  }

  /**
   * Public API for programmatic initialisation.
   *
   * Usage:
   *   StockkBotWidget.init({ apiUrl: 'https://...', theme: 'dark' });
   */
  const publicApi = {
    init(config = {}) {
      const el = document.createElement('stockkbot-widget');
      // Pass config as dataset attributes
      if (config.apiUrl)       el.dataset.apiUrl       = config.apiUrl;
      if (config.theme)        el.dataset.theme         = config.theme;
      if (config.position)     el.dataset.position      = config.position;
      if (config.primaryColor) el.dataset.primaryColor  = config.primaryColor;
      document.body.appendChild(el);
      return el;
    },
    DEFAULT_CONFIG,
  };

  // Auto-init from script tag attributes
  function autoInit() {
    const scriptEl =
      document.currentScript ||
      document.querySelector('script[src*="chatbot-widget"]');

    if (scriptEl) {
      const apiUrl = scriptEl.getAttribute('data-api-url');
      const theme  = scriptEl.getAttribute('data-theme') || 'dark';
      const pos    = scriptEl.getAttribute('data-position') || 'bottom-right';
      const color  = scriptEl.getAttribute('data-primary-color');

      // Only auto-init if not already in the DOM
      if (!document.querySelector('stockkbot-widget')) {
        publicApi.init({ apiUrl, theme, position: pos, primaryColor: color });
      }
    }
  }

  // Expose to global scope
  global.StockkBotWidget = publicApi;

  // Run auto-init after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

})(window);
