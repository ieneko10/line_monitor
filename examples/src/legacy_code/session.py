import stripe
import secrets
import string
from flask import Flask, request, redirect, render_template

app = Flask(__name__)

# Stripe APIキー（環境変数で管理するのが推奨）
stripe.api_key = ""

def generate_unique_code(length=10):
    """セキュアな乱数で 10 桁のアルファベット列を生成する関数"""
    alphabet = string.ascii_letters  # 大文字・小文字のアルファベット
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    # ユニークコードを生成
    unique_code = generate_unique_code(10)

    # Stripe Checkout Session を作成
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price": "price_XXXXXXXXXXXX",  # 商品の price ID
            "quantity": 1,
        }],
        mode="payment",
        # 成功時のリダイレクトURLにユニークコードを付与
        success_url="https://your-domain.com/success?code=" + unique_code,
        cancel_url="https://your-domain.com/cancel",
        # 任意で metadata にも保存可能
        metadata={"unique_code": unique_code}
    )

    # Checkout Session の URL にリダイレクト
    return redirect(session.url, code=303)

@app.route("/success")
def success():
    """
    決済完了ページ
    URL のクエリパラメータからコードを取得して表示する例
    """
    unique_code = request.args.get("code", "コードがありません")
    # 実際の使用時はここで HTML テンプレートに埋め込むなどする
    return f"決済完了！あなたのユニークコードは: {unique_code}"

if __name__ == "__main__":
    app.run(port=5000, debug=True)
