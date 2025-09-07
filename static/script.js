/**
 * Service Desk Chat Application - Modern UI/UX (Versão Completa e Corrigida)
 */
document.addEventListener('DOMContentLoaded', function() {
    
    // --- Referências aos elementos do DOM ---
    const chatBox = document.getElementById('chatBox');
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const typingIndicator = document.getElementById('typingIndicator');
    const chatForm = document.getElementById('chat-form');

    if (!chatBox || !chatInput || !sendButton || !chatForm) {
        console.error('Um ou mais elementos essenciais do chat não foram encontrados. O chat não pode ser inicializado.');
        return;
    }

    let isBotTyping = false;
    let messageCount = 0;
    let messageHistory = [];
    let currentMessageIndex = -1;

    // --- Funções de Lógica do Chat ---

    const handleSendMessage = async (event) => {
        if (event) event.preventDefault();
        
        const message = chatInput.value.trim();
        if (!message || isBotTyping) return;

        addToHistory(message);
        addMessageToUI(message, 'user');
        chatInput.value = '';
        autoResizeInput();
        updateSendButtonState();

        showTypingIndicator(true);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mensagem: message })
            });

            if (!response.ok) throw new Error(`Erro na resposta do servidor: ${response.status}`);
            
            const data = await response.json();
            addMessageToUI(data.text, 'bot', data.html, data.options);

        } catch (error) {
            console.error('Falha ao enviar mensagem:', error);
            addMessageToUI('Desculpe, não consegui me conectar. Verifique sua conexão e tente novamente.', 'bot');
        } finally {
            showTypingIndicator(false);
        }
    };

    const addMessageToUI = (text, type, isHtml = false, options = []) => {
        messageCount++;
        const messageId = messageCount;

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message-modern ${type}`;
        messageDiv.setAttribute('data-message-id', messageId);

        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = `message-bubble-modern ${type}`;

        if (isHtml) {
            bubbleDiv.innerHTML = text;
        } else {
            const formattedText = text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/`(.*?)`/g, '<code>$1</code>')
                .replace(/\n/g, '<br>');
            bubbleDiv.innerHTML = formattedText;
        }

        const avatarDiv = document.createElement('div');
        avatarDiv.className = `avatar-modern ${type}-avatar`;
        avatarDiv.innerHTML = type === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        messageDiv.appendChild(type === 'user' ? bubbleDiv : avatarDiv);
        messageDiv.appendChild(type === 'user' ? avatarDiv : bubbleDiv);

        if (options && options.length > 0) {
            bubbleDiv.appendChild(createFAQOptions(options));
        }
        
        if (type === 'bot') {
            bubbleDiv.appendChild(createMessageActions(messageId));
        }

        chatBox.appendChild(messageDiv);
        scrollToBottom();
    };
    
    const createFAQOptions = (options) => {
        const optionsDiv = document.createElement('div');
        optionsDiv.className = 'faq-options-modern mt-3 space-y-2';
        options.forEach(option => {
            const button = document.createElement('button');
            button.className = 'w-full text-left p-3 bg-blue-100 dark:bg-blue-900/50 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900 transition';
            button.textContent = option.question;
            button.onclick = () => {
                chatInput.value = `faq_${option.id}`;
                handleSendMessage(new Event('submit'));
            };
            optionsDiv.appendChild(button);
        });
        return optionsDiv;
    };
    
    const createMessageActions = (messageId) => {
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'message-actions-modern';

        const copyButton = document.createElement('button');
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copiar mensagem';
        copyButton.onclick = () => copyMessage(messageId);

        const thumbsUpButton = document.createElement('button');
        thumbsUpButton.innerHTML = '<i class="fas fa-thumbs-up"></i>';
        thumbsUpButton.title = 'Resposta útil';
        thumbsUpButton.onclick = (e) => sendFeedback(messageId, 'helpful', e.currentTarget);
        
        const thumbsDownButton = document.createElement('button');
        thumbsDownButton.innerHTML = '<i class="fas fa-thumbs-down"></i>';
        thumbsDownButton.title = 'Resposta não útil';
        thumbsDownButton.onclick = (e) => sendFeedback(messageId, 'unhelpful', e.currentTarget);

        actionsDiv.appendChild(copyButton);
        actionsDiv.appendChild(thumbsUpButton);
        actionsDiv.appendChild(thumbsDownButton);
        return actionsDiv;
    };

    const showTypingIndicator = (show) => {
        isBotTyping = show;
        typingIndicator.style.display = show ? 'flex' : 'none';
        updateSendButtonState();
        if (show) scrollToBottom();
    };

    const updateSendButtonState = () => {
        sendButton.disabled = chatInput.value.trim().length === 0 || isBotTyping;
    };
    
    const autoResizeInput = () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = `${Math.min(chatInput.scrollHeight, 120)}px`;
    };

    const scrollToBottom = () => {
        chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
    };

    const addToHistory = (message) => {
        messageHistory.unshift(message);
        if (messageHistory.length > 50) messageHistory.pop();
        currentMessageIndex = -1;
    };

    const navigateHistory = (direction) => {
        if (direction === 'up' && currentMessageIndex < messageHistory.length - 1) {
            currentMessageIndex++;
        } else if (direction === 'down' && currentMessageIndex > -1) {
            currentMessageIndex--;
        }
        chatInput.value = currentMessageIndex > -1 ? messageHistory[currentMessageIndex] : '';
        autoResizeInput();
    };

    const copyMessage = async (messageId) => {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"] .message-bubble-modern`);
        if (messageElement) await navigator.clipboard.writeText(messageElement.innerText);
    };
    
    const sendFeedback = async (messageId, feedbackType, buttonElement) => {
        try {
            await fetch('/chat/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, feedback: feedbackType })
            });
            const parent = buttonElement.parentElement;
            parent.querySelectorAll('button').forEach(btn => btn.disabled = true);
            buttonElement.style.color = '#10b981';
        } catch (err) {
            console.error('Erro ao enviar feedback:', err);
        }
    };

    // --- Inicialização e Event Listeners ---

    if (chatBox.children.length === 0) {
        addMessageToUI("Olá! Sou seu assistente de Service Desk. Como posso te ajudar hoje?", 'bot');
    }

    chatForm.addEventListener('submit', handleSendMessage);
    
    chatInput.addEventListener('input', () => {
        autoResizeInput();
        updateSendButtonState();
    });

    chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSendMessage(event);
        } else if (event.key === 'ArrowUp' && event.ctrlKey) {
            event.preventDefault();
            navigateHistory('up');
        } else if (event.key === 'ArrowDown' && event.ctrlKey) {
            event.preventDefault();
            navigateHistory('down');
        }
    });
    
    updateSendButtonState();
    console.log('Service Desk Chat (Moderno e Completo) foi inicializado.');
});