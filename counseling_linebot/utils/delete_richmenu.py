"""
登録中のリッチメニューを一括削除
cd counseling_linebot
python -m utils.delete_richmenu
"""

import requests
import sys

# 自作モジュールのインポート
from utils.tool import load_config, start_logger


# ロガーと設定の読み込み
main_config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(main_config_path)
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
