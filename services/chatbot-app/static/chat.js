const chatHistoryElement = document.getElementById('chat-history');
const chatFormElement = document.getElementById('chat-form');
const chatMessageElement = document.getElementById('chat-message');
const chatSendButtonElement = document.getElementById('chat-send-button');
const chatStatusElement = document.getElementById('chat-status');

function setStatus(message, type = '') {
    chatStatusElement.textContent = message;
    chatStatusElement.className = 'chat-status';

    if (type) {
        chatStatusElement.classList.add(`chat-status-${type}`);
    }
}

function clearStatus() {
    setStatus('');
}

function createMessageElement(message) {
    const messageElement = document.createElement('article');
    messageElement.className = `chat-message chat-message-${message.role}`;

    const roleElement = document.createElement('span');
    roleElement.className = 'chat-message-role';
    roleElement.textContent = message.role;

    const contentElement = document.createElement('div');
    contentElement.className = 'chat-message-content';
    contentElement.textContent = message.content ?? '';

    messageElement.appendChild(roleElement);
    messageElement.appendChild(contentElement);

    return messageElement;
}

function createEmptyStateElement() {
    const emptyStateElement = document.createElement('div');
    emptyStateElement.className = 'chat-empty-state';
    emptyStateElement.textContent = 'No messages yet. Start the conversation.';

    return emptyStateElement;
}

function renderMessages(messages) {
    chatHistoryElement.innerHTML = '';

    if (!Array.isArray(messages) || messages.length === 0) {
        chatHistoryElement.appendChild(createEmptyStateElement());

        return;
    }

    for (const message of messages) {
        chatHistoryElement.appendChild(createMessageElement(message));
    }

    chatHistoryElement.scrollTop = chatHistoryElement.scrollHeight;
}

async function loadHistory() {
    setStatus('Loading conversation...', 'success');

    const response = await fetch('/chat/history', {
        method: 'GET',
        headers: {
            Accept: 'application/json',
        },
    });

    if (!response.ok) {
        throw new Error('Unable to load chat history.');
    }

    const payload = await response.json();
    renderMessages(payload.messages ?? []);
    setStatus('Conversation loaded.', 'success');
}

async function sendMessage(message) {
    const response = await fetch('/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify({ message }),
    });

    const payload = await response.json();

    if (!response.ok) {
        throw new Error(payload.error ?? 'Unable to send message.');
    }

    return payload;
}

async function handleChatFormSubmit(event) {
    event.preventDefault();

    const message = chatMessageElement.value.trim();
    if (!message) {
        setStatus('Write a message before sending.', 'error');

        return;
    }

    chatSendButtonElement.disabled = true;
    chatMessageElement.disabled = true;
    setStatus('Sending message...', 'success');

    try {
        await sendMessage(message);
        chatMessageElement.value = '';
        await loadHistory();
        setStatus('Message sent successfully.', 'success');
        chatMessageElement.focus();
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        chatSendButtonElement.disabled = false;
        chatMessageElement.disabled = false;
    }
}

async function initializeChat() {
    await loadHistory();
}

chatFormElement.addEventListener('submit', handleChatFormSubmit);

initializeChat().catch((error) => {
    setStatus(error.message, 'error');
});