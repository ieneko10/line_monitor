import stripe
from flask import Flask, request, jsonify

app = Flask(__name__)

# Stripeのシークレットキー（環境変数などで管理するのが推奨）
stripe.api_key = ""

# Webhookの秘密鍵（Stripeダッシュボードで確認）
endpoint_secret = ""
import stripe
import os


def create_checkout_session(product_name: str, unit_amount: int, time_seconds: int, line_id: str, tunnel_url: str):
    """
    Stripe Checkout Session を作成する共通関数。

    Parameters:
        product_name (str): 商品名
        unit_amount (int): 金額（JPY, 税込み）
        time_seconds (int): セッションの有効時間（秒）
        line_id (str): ユーザーID（metadataに含める）
        tunnel_url (str): success_url / cancel_url のベースURL

    Returns:
        stripe.checkout.Session: 作成されたセッションオブジェクト
    """
    
    # Checkout Session を作成する際、payment_intent_data 内に metadata を付与
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "jpy",
                "product_data": {
                    "name": product_name,
                },
                "unit_amount": unit_amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        payment_intent_data={
            "metadata": {
                "time": time_seconds,
                "user_id": line_id
            }
        },
        success_url=f"{tunnel_url}/success",
        cancel_url=f"{tunnel_url}/cancel",
    )
    return session


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
        # customer_details オブジェクト内にメールアドレスが格納されています
        print(f"session: {session}")
        customer_details = session.get("customer_details", {})
        print(f'Customer details: {customer_details}')
        customer_email = customer_details.get("email")
        
        # （既存の処理）直接 session から metadata を取得している場合もありますが、
        # Checkout Session からは内部の PaymentIntent の metadata は取得できないため、
        # PaymentIntent の ID を使い、PaymentIntent オブジェクトを取得してメタデータを表示します。
        payment_intent_id = session.get("payment_intent")
        if payment_intent_id:
            # PaymentIntent を取得
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            print(f"Payment Intent Metadata: {payment_intent.metadata}")
        else:
            print("Payment intent ID not found in session.")
        
        # なお、もし直接 session 内の metadata も確認する場合（※checkout.session に metadata を設定していた場合）
        try:
            session_metadata = session.get("metadata", {})
            print(f"Session Metadata: {session_metadata}")
        except KeyError:
            print("session does not contain metadata")

        # metadataからLINE IDを取得
        try:
            line_id = session.get("metadata")
            print(f"LINE ID from metadata: {line_id}")
        except KeyError:
            line_id = None
            print('metadata does not contain LINE_ID')
        
        try:
            line_id = session.get("LINE_ID")
            print(f"LINE ID from session: {line_id}")
        except KeyError:
            line_id = None
            print('session does not contain LINE_ID')

        if line_id:
            print(f"Payment succeeded for LINE ID: {line_id}")
        else:
            print("Payment succeeded, but LINE ID not found in metadata.")

        # 出力内容を整形して表示
        if customer_email:
            print(f"Payment succeeded: Session ID: {session['id']}, Customer Email: {customer_email}")
        else:
            # もしメールアドレスや顧客IDが取得できない場合の処理
            print(f"Payment succeeded: Session ID: {session['id']}, but email or customer ID not found.")
    
    return jsonify(success=True)

if __name__ == "__main__":
    app.run(port=8091, debug=True)
