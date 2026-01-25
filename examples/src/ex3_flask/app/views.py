"""
ビューファイル - ルーティングとレスポンス処理
"""

from flask import render_template, request, jsonify


def init_app(app):
    """アプリケーションにルートを登録"""
    
    @app.route('/')
    def index():
        """メインページ"""
        message = "Flask Webアプリケーションのサンプルページです。"
        return render_template('index.html', message=message)

    @app.route('/test')  
    def test_page():
        """テストページ"""
        return render_template('test.html', title="テストページ")

    @app.route('/api/status')
    def api_status():
        """API ステータス確認用エンドポイント"""
        return jsonify({
            'status': 'ok',
            'message': 'Flask application is running'
        })

    @app.route('/checkout')
    def checkout():
        """チェックアウトページ"""
        return render_template('checkout.html', title="チェックアウト")

    @app.route('/success')
    def success():
        """決済成功ページ"""
        session_id = request.args.get("session_id")
        return render_template('success.html', 
                             session_id=session_id,
                             title="決済完了")

    @app.route('/cancel')
    def cancel():
        """決済キャンセルページ"""
        return render_template('cancel.html', title="決済キャンセル")

    @app.errorhandler(404)
    def not_found(error):
        """404エラーハンドラー"""
        return render_template('error.html', 
                             error_code=404,
                             error_message="ページが見つかりません"), 404

    @app.errorhandler(500)
    def internal_error(error):
        """500エラーハンドラー"""
        return render_template('error.html',
                             error_code=500, 
                             error_message="内部サーバーエラーが発生しました"), 500
