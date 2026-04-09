const chatHistoryElement = document.getElementById('chat-history');
const chatFormElement = document.getElementById('chat-form');
const chatMessageElement = document.getElementById('chat-message');
const chatSendButtonElement = document.getElementById('chat-send-button');
const chatStatusElement = document.getElementById('chat-status');
const chatThreadIdElement = document.getElementById('chat-thread-id');
const chatRunIdElement = document.getElementById('chat-run-id');
const chatResetButtonElement = document.getElementById('chat-reset-button');

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

function renderConversationMetadata(threadId, lastRunId) {
    if (threadId !== undefined) {
        chatThreadIdElement.textContent = threadId ?? '-';
    }

    if (lastRunId !== undefined && lastRunId !== null && lastRunId !== '') {
        chatRunIdElement.textContent = lastRunId;
    }
}

function clearConversationMetadata() {
    chatThreadIdElement.textContent = '-';
    chatRunIdElement.textContent = '-';
}

function formatEventTimestamp(timestamp) {
    if (!timestamp) {
        return '-';
    }

    const parsedDate = new Date(timestamp);
    if (Number.isNaN(parsedDate.getTime())) {
        return timestamp;
    }

    return parsedDate.toLocaleString();
}

function createStreamEventElement(event) {
    const itemElement = document.createElement('li');
    itemElement.className = 'chat-stream-event';

    const timestampElement = document.createElement('span');
    timestampElement.className = 'chat-stream-event-timestamp';
    timestampElement.textContent = formatEventTimestamp(event.timestamp);

    const typeElement = document.createElement('span');
    typeElement.className = 'chat-stream-event-type';
    typeElement.textContent = event.event_type ?? '-';

    const summaryElement = document.createElement('p');
    summaryElement.className = 'chat-stream-event-summary';
    summaryElement.textContent = event.summary ?? '';

    itemElement.appendChild(timestampElement);
    itemElement.appendChild(typeElement);
    itemElement.appendChild(summaryElement);

    return itemElement;
}

function createStreamEventsElement(message) {
    const streamEvents = Array.isArray(message.stream_events) ? message.stream_events : [];
    if (message.role !== 'assistant' || streamEvents.length === 0) {
        return null;
    }

    const detailsElement = document.createElement('details');
    detailsElement.className = 'chat-stream-details';

    const summaryElement = document.createElement('summary');
    summaryElement.className = 'chat-stream-summary';
    summaryElement.textContent = `Stream events (${streamEvents.length})`;

    const listElement = document.createElement('ol');
    listElement.className = 'chat-stream-events';

    for (const event of streamEvents) {
        listElement.appendChild(createStreamEventElement(event));
    }

    detailsElement.appendChild(summaryElement);
    detailsElement.appendChild(listElement);

    return detailsElement;
}

function createMessageElement(message) {
    const wrapperElement = document.createElement('div');
    wrapperElement.className = 'chat-message-block';

    const streamEventsElement = createStreamEventsElement(message);
    if (streamEventsElement !== null) {
        wrapperElement.appendChild(streamEventsElement);
    }

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
    wrapperElement.appendChild(messageElement);

    return wrapperElement;
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
    setStatus('Loading conversation...', 'loading');

    const response = await fetch('/chat/history', {
        method: 'GET',
        headers: {
            Accept: 'application/json',
        },
        cache: 'no-store',
    });

    if (!response.ok) {
        throw new Error('Unable to load chat history.');
    }

    const payload = await response.json();

    if (payload.thread_id === null) {
        clearConversationMetadata();
    } else {
        renderConversationMetadata(payload.thread_id, payload.last_run_id);
    }

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

async function resetConversation() {
    const response = await fetch('/chat/reset', {
        method: 'POST',
        headers: {
            Accept: 'application/json',
        },
    });

    const payload = await response.json();

    if (!response.ok) {
        throw new Error(payload.error ?? 'Unable to reset conversation.');
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
    chatResetButtonElement.disabled = true;
    chatMessageElement.disabled = true;
    setStatus('Sending message...', 'loading');

    try {
        const payload = await sendMessage(message);
        chatMessageElement.value = '';
        renderConversationMetadata(payload.thread_id, payload.run_id);
        await loadHistory();
        setStatus('Message sent successfully.', 'success');
        chatMessageElement.focus();
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        chatSendButtonElement.disabled = false;
        chatResetButtonElement.disabled = false;
        chatMessageElement.disabled = false;
    }
}

async function handleResetClick() {
    chatSendButtonElement.disabled = true;
    chatResetButtonElement.disabled = true;
    chatMessageElement.disabled = true;
    setStatus('Resetting conversation...', 'loading');

    try {
        await resetConversation();
        chatMessageElement.value = '';
        await loadHistory();
        setStatus('Conversation reset.', 'success');
        chatMessageElement.focus();
    } catch (error) {
        setStatus(error.message, 'error');
    } finally {
        chatSendButtonElement.disabled = false;
        chatResetButtonElement.disabled = false;
        chatMessageElement.disabled = false;
    }
}

async function initializeChat() {
    await loadHistory();
    clearStatus();
}

chatFormElement.addEventListener('submit', handleChatFormSubmit);
chatResetButtonElement.addEventListener('click', handleResetClick);

initializeChat().catch((error) => {
    setStatus(error.message, 'error');
});