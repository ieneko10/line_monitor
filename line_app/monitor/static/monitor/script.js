document.addEventListener('click', function(e) {
    if (e.target && e.target.id === 'stopButton') {
        const userId = e.target.dataset.userId;
        const action = e.target.textContent.trim() === '応答モードに切り替え';
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || getCookie('csrftoken');
        fetch(`/monitor/session/stop/${userId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
				'Content-Type': 'application/json'
            },
			credentials: 'same-origin',
            body: JSON.stringify({ user_id: userId, human: action })
        })
        .then(() => window.location.reload())
        .catch(error => console.error('Toggle error:', error));
    }
});

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


// 更新ロジック:
//  1. ユーザーごとの最新ChatHistory IDだけを定期取得
//  2. 最新IDが増えたときだけページ内容を更新
//  3. スクロール位置は従来どおり保持
setInterval(function() {
    const container = document.querySelector('.log-container');
    const userId = container?.dataset.userId;
    if (!userId) return;

    const knownLatestId = Number(container.dataset.lastLogId || 0);

    fetch(`/monitor/session/history-status/${userId}/`, { credentials: 'same-origin' })
        .then(response => response.json())
        .then(status => {
            const latestId = Number(status.latest_id || 0);
            // console.log(latestId, knownLatestId);
            if (latestId <= knownLatestId) {
                return;
            }

            const chatLog = document.querySelector('.chat-log');
            const scrollTop = chatLog ? chatLog.scrollTop : 0;
            const scrollHeight = chatLog ? chatLog.scrollHeight : 0;
            const isAtBottom = chatLog ? (scrollTop + chatLog.clientHeight >= scrollHeight - 10) : false;
            const messageCount = document.querySelectorAll('.message').length;

            fetch(window.location.href)
                .then(response => response.text())
                .then(html => {
                    const parser = new DOMParser();
                    const newDoc = parser.parseFromString(html, 'text/html');
                    const newLogArea = newDoc.querySelector('.chat-log-area');
                    const oldLogArea = document.querySelector('.chat-log-area');
                    if (newLogArea && oldLogArea) {
                        oldLogArea.replaceWith(newLogArea);
                        const currentContainer = document.querySelector('.log-container');
                        if (currentContainer) {
                            currentContainer.dataset.lastLogId = String(latestId);
                        }

                        const newChatLog = document.querySelector('.chat-log');
                        const newMessageCount = document.querySelectorAll('.message').length;

                        if (newChatLog) {
                            if (newMessageCount > messageCount || isAtBottom) {
                                setTimeout(() => {
                                    newChatLog.scrollTop = newChatLog.scrollHeight;
                                }, 0);
                            } else {
                                newChatLog.scrollTop = scrollTop;
                            }
                        }
                    }
                })
                .catch(error => console.error('Update error:', error));
        })
        .catch(error => console.error('Status check error:', error));
}, 5000);



// 返信フォームの送信処理
const replyForm = document.getElementById('reply-form');
if (replyForm) {
    replyForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(replyForm);
        const csrfToken = formData.get('csrfmiddlewaretoken');
        const message = formData.get('message');
        
        fetch(replyForm.action, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams(formData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('reply-message-input').value = '';
                // チャットログを即座に更新
                const chatLog = document.querySelector('.chat-log');
                if (chatLog) {
                    chatLog.scrollTop = chatLog.scrollHeight;
                }
            }
        })
        .catch(error => console.error('Reply error:', error));
    });
}
