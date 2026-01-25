import sqlite3
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

# --- SQLite3 のデータベース初期化 ---
def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

def register_user(user_id):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    # 同一ユーザIDがある場合は無視（重複登録しない）
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# DBを初期化
init_db()

# --- Flask アプリと LINE Bot API 設定 ---
app = Flask(__name__)

# ご自分のアクセストークンとチャネルシークレットに置き換えてください
configuration = Configuration(access_token='YOUR_ACCESS_TOKEN')
handler = WebhookHandler('YOUR_CHANNEL_SECRET')

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Error:", e)
        abort(400)
        
    return 'OK'

# --- Followイベントハンドラ（友達追加時） ---
@handler.add(FollowEvent)
def handle_follow(event):
    # ユーザのユーザIDを取得
    user_id = event.source.user_id
    # SQLite3にユーザIDを登録
    register_user(user_id)
    
    # ウェルカムメッセージを返信（任意）
    welcome_message = TextMessage(text="友達登録ありがとうございます！")
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[welcome_message]
            )
        )

# --- 既存のテキストメッセージハンドラ例 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    reply_text = f"あなたのユーザIDは {event.source.user_id} です。"
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

if __name__ == "__main__":
    app.run(port=8080)
