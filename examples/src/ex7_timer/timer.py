from flask import Flask, request, abort
import threading

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# LINE APIの設定（アクセストークンとチャンネルシークレットを適切に設定してください）
configuration = Configuration(access_token='1pFR6RHEjX5BeNcvfcOxGTq0vn6pFpTv538Dx0wkEm6JZpF3e4wV4Mf6pq4uetbE5StJaUX7ebulAGP1Dor+as7TVehz4X7bGH9G+L77Pn7uirDHtWo5guHYLZYApg63sHgJ7bYYBfbm/LczEFF8zgdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('9c5a2878527950d4514945b4af0f82b3')


# ユーザごとのオウム返しセッションを管理する辞書
# キー: ユーザID, 値: セッション終了用のTimerオブジェクト
echo_sessions = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(e)
        abort(400)
    return 'OK'

def send_end_message(user_id: str):
    """
    セッション終了時に指定ユーザへ「終了」メッセージをプッシュ送信し、
    セッション状態を削除する
    """
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message_with_http_info(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text="終了")]
            )
        )
    # セッション管理辞書から削除
    echo_sessions.pop(user_id, None)
    print(f"【{user_id}】のオウム返しセッションが終了しました。")

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    """
    ① ユーザが「オウム返し」というメッセージを送信した場合 → セッション開始（Timerにより５分後に「終了」を送信）
    ② セッション中の場合 → ユーザが送信するメッセージをすべてそのまま返信
    ③ セッション外の場合、かつ「オウム返し」以外のメッセージは何も返信しない
    """
    user_id = event.source.user_id
    user_message = event.message.text

    # セッション中の場合は、どんなメッセージでもオウム返しを実行
    if user_id in echo_sessions:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=user_message)]
                )
            )
        print(f"【{user_id}】へのオウム返し: {user_message}")

    # セッション中でなく、かつオウム返し開始コマンドの場合
    elif user_message == "オウム返し":
        # ５分（300秒）後にセッション終了用の処理を実行するTimerを起動
        timer = threading.Timer(30, send_end_message, args=[user_id])
        timer.start()
        echo_sessions[user_id] = timer
        # ※開始時は返信しない（必要であれば「オウム返しを開始します」等、返信する実装に変更も可能）
        print(f"【{user_id}】でオウム返しセッション開始")
    # その他の場合（セッション外かつオウム返しのコマンドでない場合）は何も返信しない
    else:
        print(f"【{user_id}】からのメッセージ（セッション外、かつオウム返し以外）は無視: {user_message}")

if __name__ == "__main__":
    app.run(port=8080)
