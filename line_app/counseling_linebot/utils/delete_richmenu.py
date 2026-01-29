"""
登録中のリッチメニューを一括削除
cd counseling_linebot
python -m utils.delete_richmenu
"""

import requests

# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from django.conf import settings


# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
logger = start_logger(conf['LOGGER']['SYSTEM'])

ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]

headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}'
}

# リッチメニュー一覧取得
response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
richmenus = response.json().get('richmenus', [])

print(len(richmenus), 'rich menus found.')

# 一括削除
for rm in richmenus:
    richmenu_id = rm['richMenuId']
    del_response = requests.delete(f'https://api.line.me/v2/bot/richmenu/{richmenu_id}', headers=headers)
    print(f'Deleted {richmenu_id}: {del_response.status_code}')
