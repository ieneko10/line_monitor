"""
Flask Webアプリケーション起動スクリプト
"""

import os
from app import app

if __name__ == '__main__':
    # 環境変数から設定を取得（デフォルト値も設定）
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    print(f"Starting Flask application on {host}:{port}")
    print(f"Debug mode: {debug}")
    print("Press Ctrl+C to quit")
    
    app.run(host=host, port=port, debug=debug)
