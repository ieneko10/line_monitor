import os
import random
from flask import Flask, redirect, render_template, request, jsonify
import stripe

app = Flask(__name__)

# Stripe API キーの設定（セキュリティのため環境変数から取得することを推奨）
stripe.api_key = ""

@app.route('/')
def create_checkout_session():
    rand_num = random.randint(1000, 9999)
    str_id = str(rand_num)
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
                    "user_id": str_id
                }
            },
            # {CHECKOUT_SESSION_ID} は Checkout Session 作成後に置き換えられる
            success_url="http://localhost:8080/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="http://localhost:8080/cancel",
        )
        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route('/success')
def success():
    # クエリパラメータからセッションIDを取得
    session_id = request.args.get("session_id")
    return render_template("success.html", session_id=session_id)

@app.route('/cancel')
def cancel():
    return "支払いがキャンセルされました。"

if __name__ == '__main__':
    app.run(port=8080, debug=True)
