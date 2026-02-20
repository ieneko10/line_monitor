document.addEventListener('click', function(e) {
    if (e.target && e.target.id === 'stopButton') {
        const userId = e.target.dataset.userId;
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || getCookie('csrftoken');
        fetch(`/monitor/session/stop/${userId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            }
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
//  1. 更新前のスクロール位置とメッセージ数を保存
//  2. 新しいメッセージが追加されたか、または元々一番下にあったかをチェック
//  3. いずれかの場合は一番下にスクロール
//  4. そうでない場合は、元のスクロール位置に復元
setInterval(function() {
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
            const newContent = newDoc.querySelector('.log-container');
            const oldContent = document.querySelector('.log-container');
            if (newContent && oldContent) {
                oldContent.replaceWith(newContent);
                
                const newChatLog = document.querySelector('.chat-log');
                const newMessageCount = document.querySelectorAll('.message').length;
                
                if (newChatLog) {
                    if (newMessageCount > messageCount || isAtBottom) {
                        // 新しいメッセージが追加されたか、元々一番下にいた場合は一番下にスクロール
                        setTimeout(() => {
                            newChatLog.scrollTop = newChatLog.scrollHeight;
                        }, 0);
                    } else {
                        // メッセージ数が変わらない場合はスクロール位置を復元
                        newChatLog.scrollTop = scrollTop;
                    }
                }
            }
        })
        .catch(error => console.error('Update error:', error));
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
