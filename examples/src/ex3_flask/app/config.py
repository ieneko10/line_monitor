"""
Flask設定ファイル
アプリケーションの各種設定を管理
"""

import os

# 基本設定
DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-please-change-in-production'

# データベース設定（将来的な拡張用）
DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'

# その他の設定
TESTING = False
