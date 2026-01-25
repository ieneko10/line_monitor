import sys, os
import requests
from ruamel.yaml import YAML

# 自作モジュールのインポート
from utils.tool import load_config, format_structure
from utils.set_logger import start_logger

# ロガーと設定の読み込み
logger = start_logger('./config/logger/system.yaml')
yaml_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(yaml_path)

# LINEチャンネルアクセストークン
ACCESS_TOKEN = conf['LINE_ACCESS_TOKEN']


def create_test_menu(image_path="./image/test.png"):
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """
    filename = os.path.basename(image_path)

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 843
        },
        "selected": False,
        "name": filename,
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 2500,
                    "height": 843
                },
                "action": {
                    "type": "postback",
                    "label": "リッチメニューのテスト",
                    "data": "test_richmenu"
                }
            }
        ]
    }

    richmenu_id = create_richmenuID(richmenu_data, image_path)

    return richmenu_id



def create_richmenuID(richmenu_data, image_path):

    # リッチメニュー一覧取得
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
    response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
    richmenus = response.json().get('richmenus', [])
    # formatted_richmenus = format_structure(richmenus)
    # logger.debug(f"{formatted_richmenus}")
    for rm in richmenus:
        if rm['name'] == richmenu_data['name']:
            logger.info(f"[RichMenu Already Exists] richmenu_id: {rm['richMenuId']}, name: {rm['name']}")
            return rm['richMenuId']

                   
    # リッチメニュー作成APIのURL
    richmenu_url = "https://api.line.me/v2/bot/richmenu"

    # リクエストヘッダー（JSON）
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # リッチメニュー作成のリクエスト送信
    response = requests.post(richmenu_url, headers=headers, json=richmenu_data)
    if response.status_code == 200:
        richmenu_id = response.json()["richMenuId"]
    else:
        logger.error(f"[RichMenu Creation Failed] error: {response.json()}")
    


    # 画像アップロードのヘッダー
    image_headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "image/png"
    }

    # 画像アップロードAPIのURL
    image_upload_url = f"https://api-data.line.me/v2/bot/richmenu/{richmenu_id}/content"

    # 画像ファイルを開いてPOSTリクエストを送信
    with open(image_path, "rb") as img:
        image_response = requests.post(image_upload_url, headers=image_headers, data=img)

    if image_response.status_code == 200:
        logger.info(f"[RichMenu Image Upload Success] richmenu_id: {richmenu_id}, image: {image_path}")
    else:
        logger.error(f"[RichMenu Creation Failed] error: {response.json()}")


    return richmenu_id



if __name__ == "__main__":

    yaml_path = './config/main.yaml'
    yaml = YAML()
    yaml.preserve_quotes = True  # 引用符も保持したい場合

    # ① 読み込み（コメント・順序を保持）
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.load(f)


    #リッチメニューの作成
    image_path = "./image/test.png"
    richmenu_id = create_test_menu(image_path=image_path)


    # ② 値の更新
    config['RICHMENU']['TEST'] = richmenu_id

    # ③ 書き戻し（コメント・順序を保持したまま）
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f)

