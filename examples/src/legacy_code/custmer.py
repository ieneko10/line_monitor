import stripe
import sqlite3

# Stripe APIキー（環境変数で管理するのが推奨）
stripe.api_key = ""

# SQLiteデータベースのセットアップ
conn = sqlite3.connect("stripe_users.db")
cursor = conn.cursor()

# 顧客情報を保存するテーブルを作成
cursor.execute("""
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stripe_customer_id TEXT NOT NULL,
    email TEXT NOT NULL
)
""")
conn.commit()

# Stripeで顧客を作成し、IDを取得
def create_customer(email=None):
    customer = stripe.Customer.create(description="Stripe User")
    stripe_customer_id = customer.id

    # データベースに保存
    cursor.execute("INSERT INTO customers (stripe_customer_id, email) VALUES (?, ?)", (stripe_customer_id))
    conn.commit()

    print(f"顧客作成成功: {stripe_customer_id}")
    return stripe_customer_id

# 顧客情報を取得
def get_customer(stripe_customer_id):
    cursor.execute("SELECT * FROM customers WHERE stripe_customer_id = ?", (stripe_customer_id,))
    return cursor.fetchone()

# テスト実行
email = "user@example.com"
customer_id = create_customer()
print("保存された顧客情報:", get_customer(customer_id))

# データベース接続を閉じる
conn.close()
