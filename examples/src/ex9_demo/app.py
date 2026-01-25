import stripe
import requests
import random
import threading
import json
import sqlite3
from flask import Flask, request, jsonify, redirect, render_template
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, PushMessageRequest
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent, PostbackEvent
from pyngrok import ngrok

# 自作
from richmenu_request_sample import create_and_apply_richmenu
from api_key import LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, STRIPE_SECRET, STRIPE_WEBHOOK   # 利用時は，dumy_key.pyを参照

# 8080番ポートのHTTPトンネルを開設する
tunnel = ngrok.connect(8080, "http")
print("Public URL:", tunnel.public_url)

# ユーザごとのオウム返しセッションを管理する辞書
# キー: ユーザID, 値: セッション終了用のTimerオブジェクト
echo_sessions = {}

app = Flask(__name__)

# LINE APIの設定
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Stripeのシークレットキー（環境変数などで管理するのが推奨）
stripe.api_key = STRIPE_SECRET
# Webhookの秘密鍵（Stripeダッシュボードで確認）
endpoint_secret = STRIPE_WEBHOOK


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except:
        abort(400)

    return 'OK' 

# --- Followイベントハンドラ（友達追加時） ---
@handler.add(FollowEvent)
def handle_follow(event):
    # ユーザのユーザIDを取得
    user_id = event.source.user_id
    create_and_apply_richmenu(user_id, url=tunnel.public_url)  # リッチメニューを作成・適用
    
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
                messages=[TextMessage(text="時間となりましたので，カウンセリング対話を終了いたします。")]
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


@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id

    # 送信されたデータをチェック
    if event.postback.data == "action=send_flex":

        # 返信テキストにユーザIDを含める
        reply_text = f"あなたのユーザID："
        reply_text2 = f"{user_id}"

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text), TextMessage(text=reply_text2)]
                )
            )


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except stripe.error.SignatureVerificationError:
        return "Webhook signature verification failed", 400
    except stripe.error.StripeError:
        return "Stripe error", 400

    # 支払い成功イベントを処理
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        payment_intent_id = session.get("payment_intent")
        if payment_intent_id:
            # PaymentIntent を取得
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            print(f"Payment Intent Metadata: {payment_intent.metadata}")
        else:
            print("Payment intent ID not found in session.")

        user_id = payment_intent.metadata.get("user_id")
        print(user_id, type(user_id))
        reply_to_line_user(user_id, "ご購入ありがとうございました！")
        
        # ５分（300秒）後にセッション終了用の処理を実行するTimerを起動
        timer = threading.Timer(30, send_end_message, args=[user_id])
        timer.start()
        echo_sessions[user_id] = timer
        # ※開始時は返信しない（必要であれば「オウム返しを開始します」等、返信する実装に変更も可能）
        print(f"【{user_id}】でオウム返しセッション開始")
        
        # customer_details オブジェクト内にメールアドレスが格納されています
        # custom_fields = session.get("custom_fields", {})
        # LINE_ID = custom_fields[0].get("text", {}).get("value", None)
        # print(f"LINE ID from custom fields: {LINE_ID}")

        # reply_to_line_user(LINE_ID, "Payment succeeded! Thank you for your purchase.")
                

    return jsonify(success=True)


@app.route('/checkout', methods=['GET'])
def create_checkout_session():
    # URLからパラメータを取得
    line_id = request.args.get('LINE_ID')
    print(f"Received LINE_ID: {line_id}")

    rand_num = random.randint(1000, 9999)
    str_id = str(rand_num)
    print(f"Generated random number: {rand_num}")
    try:
        # Checkout Session を作成する際、payment_intent_data 内に metadata を付与
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "product_data": {
                        "name": "Sample Product",
                    },
                    # 1円 = 100 分なので、ここでは 1000 は 1000 円
                    "unit_amount": 1000,
                },
                "quantity": 1,
            }],
            mode="payment",
            # PaymentIntent にメタデータを付与（ここでは注文番号やユーザー ID など、必要な情報を設定）
            payment_intent_data={
                "metadata": {
                    "order_id": "6735",
                    "user_id": line_id
                }
            },
            # {CHECKOUT_SESSION_ID} は Checkout Session 作成後に置き換えられる
            success_url = tunnel.public_url + "/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url = tunnel.public_url + "/cancel",
        )
        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify(error=str(e)), 400


def reply_to_line_user(user_id, message):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        # 送信するテキストメッセージを作成
        message = TextMessage(text="ご購入ありがとうございました！")
        # Pushメッセージのリクエストオブジェクトを作成
        push_request = PushMessageRequest(
            to=user_id,
            messages=[message]
        )
        # push_message_with_http_info を実行して送信
        line_bot_api.push_message_with_http_info(push_request)

@app.route('/success')
def success():
    # クエリパラメータからセッションIDを取得
    session_id = request.args.get("session_id")
    return render_template("success.html", session_id=session_id)

@app.route('/cancel')
def cancel():
    return "支払いがキャンセルされました。"


if __name__ == "__main__":

    app.run(port=8080)

