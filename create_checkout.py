import stripe

def create_checkout(product_name: str, unit_amount: int, user_id: str, tunnel_url: str):
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
                "user_id": user_id,
                "plan_name": product_name
            }
        },
        success_url=f"{tunnel_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{tunnel_url}/plans"
    )
    return session