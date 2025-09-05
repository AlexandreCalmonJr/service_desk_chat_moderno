/**
 * Service Desk Chat Application
 * Enhanced JavaScript with improved UX and accessibility
 */

class ServiceDeskChat {
    constructor() {
        this.chatBox = null;
        this.chatInput = null;
        this.sendButton = null;
        this.typingIndicator = null;
        this.messageCount = 0;
        this.isTyping = false;
        this.messageHistory = [];
        this.currentMessageIndex = -1;
        
        // Configuration
        this.config = {
            maxMessageLength: 1000,
            typingDelay: 1000,
            autoScrollDelay: 100,
            retryAttempts: 3,
            retryDelay: 1000
        };
        
        this.init();
    }
    
    /**
     * Initialize the chat application
     */
    init() {
        this.bindElements();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.loadChatHistory();
        this.focusInput();
        
        // Add initial welcome message if chat is empty
        if (this.chatBox && this.chatBox.children.length <= 1) {
            this.addWelcomeMessage();
        }
        
        console.log('Service Desk Chat initialized successfully');
    }
    
    /**
     * Bind DOM elements
     */
    bindElements() {
        this.chatBox = document.getElementById('chatBox');
        this.chatInput = document.getElementById('chatInput');
        this.sendButton = document.getElementById('sendButton');
        this.typingIndicator = document.getElementById('typingIndicator');
        
        if (!this.chatBox || !this.chatInput || !this.sendButton) {
            console.error('Required chat elements not found');
            return;
        }
    }
    
    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Send button click
        this.sendButton?.addEventListener('click', (e) => {
            e.preventDefault();
            this.handleSendMessage();
        });
        
        // Input events
        this.chatInput?.addEventListener('keydown', (e) => this.handleKeyDown(e));
        this.chatInput?.addEventListener('input', () => this.handleInputChange());
        this.chatInput?.addEventListener('paste', (e) => this.handlePaste(e));
        
        // Form submission prevention
        const chatForm = document.querySelector('.chat-form');
        chatForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSendMessage();
        });
        
        // Window events
        window.addEventListener('beforeunload', () => this.saveChatHistory());
        window.addEventListener('online', () => this.handleConnectionChange(true));
        window.addEventListener('offline', () => this.handleConnectionChange(false));
        
        // Visibility change for better UX
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.chatInput) {
                this.chatInput.focus();
            }
        });
    }
    
    /**
     * Setup keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Enter to send message
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.handleSendMessage();
            }
            
            // Escape to clear input
            if (e.key === 'Escape' && this.chatInput === document.activeElement) {
                this.chatInput.value = '';
                this.autoResize();
            }
            
            // Arrow keys for message history
            if (this.chatInput === document.activeElement) {
                if (e.key === 'ArrowUp' && e.ctrlKey) {
                    e.preventDefault();
                    this.navigateHistory('up');
                } else if (e.key === 'ArrowDown' && e.ctrlKey) {
                    e.preventDefault();
                    this.navigateHistory('down');
                }
            }
        });
    }
    
    /**
     * Handle input keydown events
     */
    handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.handleSendMessage();
        } else if (e.key === 'Tab') {
            // Allow tab for accessibility
            return;
        }
    }
    
    /**
     * Handle input change events
     */
    handleInputChange() {
        this.autoResize();
        this.updateCharacterCount();
        this.updateSendButtonState();
    }
    
    /**
     * Handle paste events
     */
    handlePaste(e) {
        setTimeout(() => {
            this.autoResize();
            this.updateCharacterCount();
        }, 0);
    }
    
    /**
     * Auto-resize textarea based on content
     */
    autoResize() {
        if (!this.chatInput) return;
        
        this.chatInput.style.height = 'auto';
        const newHeight = Math.min(this.chatInput.scrollHeight, 120);
        this.chatInput.style.height = newHeight + 'px';
    }
    
    /**
     * Update character count display
     */
    updateCharacterCount() {
        if (!this.chatInput) return;
        
        const currentLength = this.chatInput.value.length;
        const maxLength = this.config.maxMessageLength;
        
        // Add visual feedback for character limit
        if (currentLength > maxLength * 0.9) {
            this.chatInput.classList.add('near-limit');
        } else {
            this.chatInput.classList.remove('near-limit');
        }
        
        if (currentLength > maxLength) {
            this.chatInput.classList.add('over-limit');
        } else {
            this.chatInput.classList.remove('over-limit');
        }
    }
    
    /**
     * Update send button state
     */
    updateSendButtonState() {
        if (!this.sendButton || !this.chatInput) return;
        
        const hasContent = this.chatInput.value.trim().length > 0;
        const isUnderLimit = this.chatInput.value.length <= this.config.maxMessageLength;
        
        this.sendButton.disabled = !hasContent || !isUnderLimit || this.isTyping;
    }
    
    /**
     * Navigate through message history
     */
    navigateHistory(direction) {
        if (this.messageHistory.length === 0) return;
        
        if (direction === 'up') {
            if (this.currentMessageIndex < this.messageHistory.length - 1) {
                this.currentMessageIndex++;
            }
        } else if (direction === 'down') {
            if (this.currentMessageIndex > -1) {
                this.currentMessageIndex--;
            }
        }
        
        if (this.currentMessageIndex >= 0) {
            this.chatInput.value = this.messageHistory[this.messageHistory.length - 1 - this.currentMessageIndex];
        } else {
            this.chatInput.value = '';
        }
        
        this.autoResize();
        this.updateSendButtonState();
    }
    
    /**
     * Handle connection change
     */
    handleConnectionChange(isOnline) {
        const statusMessage = isOnline ? 
            'Conexão restaurada. Você pode continuar conversando.' : 
            'Conexão perdida. Verifique sua internet.';
            
        this.showSystemMessage(statusMessage, isOnline ? 'success' : 'warning');
    }
    
    /**
     * Show system message
     */
    showSystemMessage(message, type = 'info') {
        const systemMessage = document.createElement('div');
        systemMessage.className = `system-message system-${type}`;
        systemMessage.textContent = message;
        systemMessage.setAttribute('role', 'status');
        systemMessage.setAttribute('aria-live', 'polite');
        
        this.chatBox?.appendChild(systemMessage);
        this.scrollToBottom();
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (systemMessage.parentNode) {
                systemMessage.remove();
            }
        }, 5000);
    }
    
    /**
     * Add welcome message
     */
    addWelcomeMessage() {
        const welcomeText = `Olá! Sou seu assistente de Service Desk. Como posso ajudar você hoje?
        
Você pode:
• Encerrar chamados: "Encerrar chamado 12345"
• Solicitar soluções: "Sugerir solução para computador não liga"
• Fazer perguntas sobre TI
• Buscar informações em nossa base de conhecimento

Digite sua mensagem abaixo para começar!`;

        this.addMessage(welcomeText, false, false, [], true);
    }
    
    /**
     * Handle send message
     */
    async handleSendMessage() {
        const message = this.chatInput?.value?.trim();
        if (!message || this.isTyping) return;
        
        // Validate message length
        if (message.length > this.config.maxMessageLength) {
            this.showSystemMessage(`Mensagem muito longa. Máximo ${this.config.maxMessageLength} caracteres.`, 'error');
            return;
        }
        
        // Add to history
        this.addToHistory(message);
        
        // Add user message
        this.addMessage(message, true);
        
        // Clear input
        this.chatInput.value = '';
        this.autoResize();
        this.updateSendButtonState();
        
        // Send to server
        await this.sendMessageToServer(message);
    }
    
    /**
     * Add message to history
     */
    addToHistory(message) {
        this.messageHistory.unshift(message);
        if (this.messageHistory.length > 50) {
            this.messageHistory.pop();
        }
        this.currentMessageIndex = -1;
    }
    
    /**
     * Send message to server with retry logic
     */
    async sendMessageToServer(message, attempt = 1) {
        this.showTypingIndicator();
        this.setButtonLoading(true);
        
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ mensagem: message }),
                signal: AbortSignal.timeout(30000) // 30 second timeout
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Validate response
            if (!data || typeof data.text !== 'string') {
                throw new Error('Resposta inválida do servidor');
            }
            
            this.addMessage(data.text, false, data.html, data.options);
            
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
            
            // Retry logic
            if (attempt < this.config.retryAttempts && !error.name === 'AbortError') {
                console.log(`Tentativa ${attempt + 1} de ${this.config.retryAttempts}`);
                setTimeout(() => {
                    this.sendMessageToServer(message, attempt + 1);
                }, this.config.retryDelay * attempt);
                return;
            }
            
            // Show error message
            let errorMessage = 'Desculpe, ocorreu um erro ao processar sua mensagem.';
            
            if (error.name === 'AbortError') {
                errorMessage = 'A solicitação expirou. Tente novamente.';
            } else if (!navigator.onLine) {
                errorMessage = 'Sem conexão com a internet. Verifique sua conexão.';
            } else if (error.message.includes('500')) {
                errorMessage = 'Erro interno do servidor. Tente novamente em alguns instantes.';
            }
            
            this.addMessage(errorMessage, false);
            
        } finally {
            this.hideTypingIndicator();
            this.setButtonLoading(false);
            this.focusInput();
        }
    }
    
    /**
     * Add message to chat
     */
    addMessage(message, isUser = false, isHtml = false, options = [], isWelcome = false) {
        if (!this.chatBox) return;
        
        this.messageCount++;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'bot'}${isWelcome ? ' welcome-message' : ''}`;
        messageDiv.setAttribute('role', 'article');
        messageDiv.setAttribute('aria-label', `${isUser ? 'Sua mensagem' : 'Resposta do assistente'} ${this.messageCount}`);
        messageDiv.setAttribute('data-message-id', this.messageCount);
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'avatar';
        avatarDiv.setAttribute('aria-hidden', 'true');
        avatarDiv.innerHTML = isUser ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'message-bubble';
        
        // Add timestamp
        const timestamp = document.createElement('div');
        timestamp.className = 'message-timestamp';
        timestamp.textContent = new Date().toLocaleTimeString('pt-BR', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
        timestamp.setAttribute('title', new Date().toLocaleString('pt-BR'));
        
        if (isHtml) {
            bubbleDiv.innerHTML = message;
            this.processCodeBlocks(bubbleDiv);
        } else {
            // Process line breaks and format text
            const formattedMessage = this.formatMessage(message);
            bubbleDiv.innerHTML = formattedMessage;
        }
        
        // Add FAQ options if available
        if (options && options.length > 0) {
            const optionsDiv = this.createFAQOptions(options);
            bubbleDiv.appendChild(optionsDiv);
        }
        
        // Add message actions for bot messages
        if (!isUser && !isWelcome) {
            const actionsDiv = this.createMessageActions(this.messageCount);
            bubbleDiv.appendChild(actionsDiv);
        }
        
        bubbleDiv.appendChild(timestamp);
        
        // Arrange elements based on user type
        if (isUser) {
            messageDiv.appendChild(bubbleDiv);
            messageDiv.appendChild(avatarDiv);
        } else {
            messageDiv.appendChild(avatarDiv);
            messageDiv.appendChild(bubbleDiv);
        }
        
        this.chatBox.appendChild(messageDiv);
        
        // Animate message appearance
        requestAnimationFrame(() => {
            messageDiv.classList.add('message-visible');
        });
        
        this.scrollToBottom();
        
        // Announce new messages to screen readers
        if (!isUser) {
            this.announceMessage('Nova resposta do assistente recebida');
        }
        
        // Save to local storage
        this.saveChatHistory();
    }
    
    /**
     * Format message text
     */
    formatMessage(text) {
        return text
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    }
    
    /**
     * Process code blocks
     */
    processCodeBlocks(container) {
        const codeBlocks = container.querySelectorAll('pre code');
        codeBlocks.forEach(block => {
            this.addCopyButton(block);
            // Add syntax highlighting if available
            if (window.hljs) {
                window.hljs.highlightElement(block);
            }
        });
    }
    
    /**
     * Add copy button to code blocks
     */
    addCopyButton(codeBlock) {
        const pre = codeBlock.parentElement;
        if (pre.tagName.toLowerCase() !== 'pre') return;
        
        const button = document.createElement('button');
        button.className = 'copy-code-button';
        button.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i> Copiar';
        button.setAttribute('aria-label', 'Copiar código');
        button.setAttribute('title', 'Copiar código para área de transferência');
        
        pre.style.position = 'relative';
        pre.appendChild(button);
        
        button.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(codeBlock.textContent);
                button.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> Copiado!';
                button.setAttribute('aria-label', 'Código copiado');
                
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i> Copiar';
                    button.setAttribute('aria-label', 'Copiar código');
                }, 2000);
                
            } catch (err) {
                console.error('Erro ao copiar:', err);
                button.innerHTML = '<i class="fas fa-exclamation-triangle" aria-hidden="true"></i> Erro';
                
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i> Copiar';
                }, 2000);
            }
        });
    }
    
    /**
     * Create FAQ options
     */
    createFAQOptions(options) {
        const optionsDiv = document.createElement('div');
        optionsDiv.className = 'faq-options';
        optionsDiv.setAttribute('role', 'group');
        optionsDiv.setAttribute('aria-label', 'Opções de FAQ relacionadas');
        
        options.forEach((option, index) => {
            const button = document.createElement('button');
            button.className = 'faq-option-button';
            button.textContent = option.question;
            button.setAttribute('aria-label', `FAQ opção ${index + 1}: ${option.question}`);
            button.addEventListener('click', () => {
                this.chatInput.value = `faq_${option.id}`;
                this.handleSendMessage();
            });
            optionsDiv.appendChild(button);
        });
        
        return optionsDiv;
    }
    
    /**
     * Create message actions
     */
    createMessageActions(messageId) {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions';
        
        // Copy message button
        const copyButton = document.createElement('button');
        copyButton.className = 'message-action-button';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.setAttribute('aria-label', 'Copiar mensagem');
        copyButton.setAttribute('title', 'Copiar mensagem');
        copyButton.addEventListener('click', () => this.copyMessage(messageId));
        
        // Feedback buttons
        const thumbsUpButton = document.createElement('button');
        thumbsUpButton.className = 'message-action-button feedback-button';
        thumbsUpButton.innerHTML = '<i class="fas fa-thumbs-up"></i>';
        thumbsUpButton.setAttribute('aria-label', 'Resposta útil');
        thumbsUpButton.setAttribute('title', 'Marcar como útil');
        thumbsUpButton.addEventListener('click', () => this.sendFeedback(messageId, 'helpful'));
        
        const thumbsDownButton = document.createElement('button');
        thumbsDownButton.className = 'message-action-button feedback-button';
        thumbsDownButton.innerHTML = '<i class="fas fa-thumbs-down"></i>';
        thumbsDownButton.setAttribute('aria-label', 'Resposta não útil');
        thumbsDownButton.setAttribute('title', 'Marcar como não útil');
        thumbsDownButton.addEventListener('click', () => this.sendFeedback(messageId, 'unhelpful'));
        
        actionsDiv.appendChild(copyButton);
        actionsDiv.appendChild(thumbsUpButton);
        actionsDiv.appendChild(thumbsDownButton);
        
        return actionsDiv;
    }
    
    /**
     * Copy message content
     */
    async copyMessage(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"] .message-bubble`);
        if (!messageElement) return;
        
        const text = messageElement.textContent || messageElement.innerText;
        
        try {
            await navigator.clipboard.writeText(text);
            this.showSystemMessage('Mensagem copiada!', 'success');
        } catch (err) {
            console.error('Erro ao copiar mensagem:', err);
            this.showSystemMessage('Erro ao copiar mensagem', 'error');
        }
    }
    
    /**
     * Send feedback
     */
    async sendFeedback(messageId, feedback) {
        try {
            const response = await fetch('/chat/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message_id: messageId,
                    feedback: feedback
                })
            });
            
            if (response.ok) {
                this.showSystemMessage('Obrigado pelo feedback!', 'success');
                
                // Disable feedback buttons for this message
                const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                const feedbackButtons = messageElement?.querySelectorAll('.feedback-button');
                feedbackButtons?.forEach(button => {
                    button.disabled = true;
                    button.classList.add('feedback-sent');
                });
            }
        } catch (err) {
            console.error('Erro ao enviar feedback:', err);
        }
    }
    
    /**
     * Show typing indicator
     */
    showTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.style.display = 'flex';
            this.isTyping = true;
            this.scrollToBottom();
        }
    }
    
    /**
     * Hide typing indicator
     */
    hideTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.style.display = 'none';
            this.isTyping = false;
        }
    }
    
    /**
     * Set button loading state
     */
    setButtonLoading(loading) {
        if (!this.sendButton) return;
        
        if (loading) {
            this.sendButton.disabled = true;
            this.sendButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
            this.sendButton.setAttribute('aria-label', 'Enviando mensagem...');
        } else {
            this.sendButton.disabled = false;
            this.sendButton.innerHTML = '<i class="fas fa-paper-plane" aria-hidden="true"></i>';
            this.sendButton.setAttribute('aria-label', 'Enviar mensagem');
            this.updateSendButtonState();
        }
    }
    
    /**
     * Scroll to bottom of chat
     */
    scrollToBottom() {
        if (!this.chatBox) return;
        
        setTimeout(() => {
            this.chatBox.scrollTo({
                top: this.chatBox.scrollHeight,
                behavior: 'smooth'
            });
        }, this.config.autoScrollDelay);
    }
    
    /**
     * Focus input
     */
    focusInput() {
        if (this.chatInput && !this.isTyping) {
            setTimeout(() => {
                this.chatInput.focus();
            }, 100);
        }
    }
    
    /**
     * Announce message to screen readers
     */
    announceMessage(message) {
        const announcement = document.createElement('div');
        announcement.setAttribute('aria-live', 'assertive');
        announcement.setAttribute('aria-atomic', 'true');
        announcement.className = 'sr-only';
        announcement.textContent = message;
        
        document.body.appendChild(announcement);
        
        setTimeout(() => {
            if (announcement.parentNode) {
                document.body.removeChild(announcement);
            }
        }, 1000);
    }
    
    /**
     * Clear chat
     */
    clearChat() {
        if (!confirm('Tem certeza que deseja limpar toda a conversa?')) {
            return;
        }
        
        if (this.chatBox) {
            // Keep only the first message (welcome message)
            const messages = this.chatBox.querySelectorAll('.chat-message:not(.welcome-message)');
            messages.forEach(msg => msg.remove());
        }
        
        this.messageCount = 0;
        this.messageHistory = [];
        this.currentMessageIndex = -1;
        
        // Clear local storage
        localStorage.removeItem('chat-history');
        
        this.focusInput();
        this.showSystemMessage('Conversa limpa', 'info');
    }
    
    /**
     * Export chat
     */
    exportChat() {
        if (!this.chatBox) return;
        
        const messages = Array.from(this.chatBox.querySelectorAll('.chat-message')).map(msg => {
            const isUser = msg.classList.contains('user');
            const bubble = msg.querySelector('.message-bubble');
            const timestamp = msg.querySelector('.message-timestamp')?.textContent || '';
            const text = bubble ? bubble.textContent.replace(timestamp, '').trim() : '';
            
            return `[${timestamp}] ${isUser ? 'Você' : 'Assistente'}: ${text}`;
        }).join('\n\n');
        
        const blob = new Blob([messages], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-service-desk-${new Date().toISOString().split('T')[0]}.txt`;
        
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showSystemMessage('Chat exportado com sucesso!', 'success');
    }
    
    /**
     * Save chat history to localStorage
     */
    saveChatHistory() {
        if (!this.chatBox) return;
        
        try {
            const messages = Array.from(this.chatBox.querySelectorAll('.chat-message')).map(msg => {
                const isUser = msg.classList.contains('user');
                const bubble = msg.querySelector('.message-bubble');
                const text = bubble ? bubble.innerHTML : '';
                
                return {
                    isUser,
                    text,
                    timestamp: Date.now()
                };
            });
            
            localStorage.setItem('chat-history', JSON.stringify(messages.slice(-20))); // Keep last 20 messages
        } catch (err) {
            console.error('Erro ao salvar histórico:', err);
        }
    }
    
    /**
     * Load chat history from localStorage
     */
    loadChatHistory() {
        try {
            const history = localStorage.getItem('chat-history');
            if (!history) return;
            
            const messages = JSON.parse(history);
            const oneHourAgo = Date.now() - (60 * 60 * 1000);
            
            // Only load recent messages (within last hour)
            const recentMessages = messages.filter(msg => msg.timestamp > oneHourAgo);
            
            if (recentMessages.length > 0 && this.chatBox) {
                // Clear existing messages except welcome
                const existingMessages = this.chatBox.querySelectorAll('.chat-message:not(.welcome-message)');
                existingMessages.forEach(msg => msg.remove());
                
                // Add historical messages
                recentMessages.forEach(msg => {
                    this.addMessage(msg.text, msg.isUser, true);
                });
            }
        } catch (err) {
            console.error('Erro ao carregar histórico:', err);
        }
    }
}

// Global functions for backward compatibility and external access
let chatInstance = null;

function clearChat() {
    chatInstance?.clearChat();
}

function exportChat() {
    chatInstance?.exportChat();
}

function sendMessage(message) {
    if (chatInstance && chatInstance.chatInput) {
        chatInstance.chatInput.value = message;
        chatInstance.handleSendMessage();
    }
}

// Initialize chat when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    chatInstance = new ServiceDeskChat();
    
    // Make functions globally available
    window.clearChat = clearChat;
    window.exportChat = exportChat;
    window.sendMessage = sendMessage;
    window.chatInstance = chatInstance;
});

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (!document.hidden && chatInstance) {
        chatInstance.focusInput();
    }
});

