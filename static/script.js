document.addEventListener('DOMContentLoaded', function () {
    const chatBox = document.getElementById('chatBox');
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const loadingSpinner = document.getElementById('loadingSpinner');

    // Função para adicionar mensagem ao chat
    function addMessage(message, isUser = false, isHtml = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message';
        messageDiv.classList.add(isUser ? 'user-message' : 'bot-message');
        if (isHtml) {
            messageDiv.innerHTML = message;
        } else {
            messageDiv.textContent = message;
        }
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Função para exibir opções de FAQ
    function displayOptions(options) {
        options.forEach(option => {
            const optionButton = document.createElement('button');
            optionButton.className = 'btn btn-outline-primary btn-sm m-1';
            optionButton.textContent = option.question;
            optionButton.onclick = () => sendMessage(`faq_${option.id}`);
            chatBox.appendChild(optionButton);
        });
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Função para enviar mensagem
    async function sendMessage(message) {
        if (!message) return;

        addMessage(message, true);
        chatInput.value = '';
        loadingSpinner.style.display = 'block';

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mensagem: message })
            });

            const data = await response.json();
            loadingSpinner.style.display = 'none';

            addMessage(data.text, false, data.html);
            if (data.state === 'faq_selection' && data.options.length > 0) {
                displayOptions(data.options);
            }
        } catch (error) {
            loadingSpinner.style.display = 'none';
            addMessage('Erro ao enviar mensagem. Tente novamente.', false);
            console.error('Erro:', error);
        }
    }

    // Evento de clique no botão Enviar
    sendButton.addEventListener('click', () => {
        const message = chatInput.value.trim();
        if (message) sendMessage(message);
    });

    // Evento de pressionar Enter
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const message = chatInput.value.trim();
            if (message) sendMessage(message);
        }
    });

    // Mensagem inicial do bot
    addMessage('Olá! Como posso ajudar você hoje? Tente "Encerrar chamado <ID>", "Sugerir solução para <problema>", ou faça uma pergunta!', false);
});