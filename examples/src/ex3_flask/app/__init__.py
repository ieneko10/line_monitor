"""
Flask Web Application for counseling system example
シンプルなWebアプリケーションの例
"""

from flask import Flask


def create_app():
    """Application Factory Pattern を使用してFlaskアプリを作成"""
    app = Flask(__name__)
    
    # 設定を読み込み
    app.config.from_object('app.config')
    
    # ビューを登録
    from app import views
    views.init_app(app)
    
    return app


# アプリケーションインスタンスを作成
app = create_app()
