import sys
import requests

# 自作モジュールのインポート
from utils.tool import load_config
from utils.set_logger import start_logger
from utils.ansi import *

# ロガーと設定の読み込み
config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(config_path)
logger = start_logger(conf['LOGGER']['SYSTEM'])

# LINEチャンネルアクセストークン
ACCESS_TOKEN = conf['LINE_ACCESS_TOKEN']

def consent():
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """

    image_path = "./image/consent.png"

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": "同意文の確認",
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 2500,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "同意文を送信",
                    "data": "consent"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 585,
                    "width": 2500,
                    "height": 1686
                },
                "action": {
                    "type": "postback",
                    "label": "同意なし",
                    "data": 'no_consent'
                }
            },
        ]
    }

    return create_richmenu(richmenu_data, image_path)




def counseling():
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """

    image_path = "./image/counseling.png"

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": "カウンセリング対話中",
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 625,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "会話履歴のリセット",
                    "data": "reset_history"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 1875,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "カウンセリング対話の終了",
                    "data": "end_chat"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 585,
                    "width": 2500,
                    "height": 1686
                },
                "action": {
                    "type": "postback",
                    "label": "残り時間の確認",
                    "data": "check_time"
                }
            }
        ]
    }

    return create_richmenu(richmenu_data, image_path)



def remaining_time(remaining_time):
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """
    
    if remaining_time > 60:
        image_path = './image/remaining_time/60over.png'
    else:
        image_path = f'./image/remaining_time/{int(remaining_time):02d}.png'

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": f"カウンセリング残り時間{remaining_time}分",
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 625,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "時間の更新",
                    "data": "update_time"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 1875,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "戻る",
                    "data": "back_to_menu"
                }
            }
        ]
    }


    return create_richmenu(richmenu_data, image_path)


def survey():
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 843
        },
        "selected": False,
        "name": "アンケートの終了",
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
                    "label": "アンケートの終了",
                    "data": "end_survey"
                }
            }
        ]
    }

    return create_richmenu(richmenu_data, "./image/survey.png")


def maintenance():
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 843
        },
        "selected": False,
        "name": "メンテナンス中",
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
                    "label": "メンテナンス中",
                    "data": "maintenance"
                }
            }
        ]
    }

    return create_richmenu(richmenu_data, "./image/maintenance.png")


def start():
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """

    image_path = "./image/start.png"

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": "カウンセリング開始",
        "chatBarText": "Tap to open",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": 625,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "会話履歴のリセット",
                    "data": "reset_history"
                }
            },
            {
                "bounds": {
                    "x": 625,
                    "y": 0,
                    "width": 1875,
                    "height": 585
                },
                "action": {
                    "type": "postback",
                    "label": "カウンセリング対話の開始",
                    "data": "start_chat"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 585,
                    "width": 2500,
                    "height": 1686
                },
                "action": {
                    "type": "postback",
                    "label": "shop_flexmessage",
                    "data": "shop"
                }
            }
        ]
    }

    return create_richmenu(richmenu_data, image_path)


def create_richmenu(richmenu_data, image_path):

    # リッチメニュー一覧取得
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
    response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
    richmenus = response.json().get('richmenus', [])
    # formatted_richmenus = format_structure(richmenus)
    # logger.debug(f"{formatted_richmenus}")
    for richmenu in richmenus:
        if richmenu['name'] == richmenu_data['name']:
            logger.ddebug(f"[RichMenu Already Exists] richmenu_id: {richmenu['richMenuId']}, name: {richmenu['name']}")
            return richmenu['richMenuId']

                   
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



def create_richmenus(config):
    if config == None:
        config = {'REMAINING_TIME': {}}
    config['CONSENT'] = consent()
    config['START'] = start()
    config['COUNSELING'] = counseling()
    config['SURVEY'] = survey()
    config['MAINTENANCE'] = maintenance()
    config['REMAINING_TIME']['60over'] = remaining_time(61)
    for i in range(61):
        config['REMAINING_TIME'][i] = remaining_time(i)

    return config



def apply_richmenu(richmenu_id, user_id):

    # ユーザーにリッチメニューを適用するAPIのURL
    apply_richmenu_url = f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{richmenu_id}"

    # ユーザー適用用ヘッダー
    apply_headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    
    apply_response = requests.post(apply_richmenu_url, headers=apply_headers)

    richmenu_data = requests.get(f"https://api.line.me/v2/bot/richmenu/{richmenu_id}", headers=apply_headers).json()
    richmenu_name = richmenu_data.get('name', 'Unknown RichMenu')

    if apply_response.status_code == 200:
        logger.debug(f"[RichMenu Applied] {richmenu_name}, user: {user_id}")
    else:
        logger.error(f"[RichMenu Apply Failed] error: {apply_response.json()}\nuser: {user_id}")


def cancel_richmenu(user_id):
    """
    ユーザーIDを受け取り、そのユーザーに適用されているリッチメニューを削除する関数
    """
    # リッチメニュー削除APIのURL
    cancel_url = f"https://api.line.me/v2/bot/user/{user_id}/richmenu"

    # ヘッダー
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    # リクエスト送信
    response = requests.delete(cancel_url, headers=headers)

    if response.status_code == 200:
        print(f"ユーザー {user_id} のリッチメニューが削除されました。")
    else:
        print("リッチメニュー削除に失敗しました:", response.json())


def delete_all_richmenu():
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    # リッチメニュー一覧取得
    response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
    richmenus = response.json().get('richmenus', [])

    logger.info(len(richmenus))
    logger.info(richmenus[0])

    # 一括削除
    for rm in richmenus:
        richmenu_id = rm['richMenuId']
        del_response = requests.delete(f'https://api.line.me/v2/bot/richmenu/{richmenu_id}', headers=headers)
        logger.info(f'Deleted {richmenu_id}: {del_response.status_code}')


def check_richmenu(session, postback_data, user_id, richmenu_ids):
    """
    session情報をもとに、リッチメニューの適用状況が正しいかを確認する関数
    """
    if postback_data == 'maintenance':
        if session['keyword_accepted'] == False:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["CONSENT"]}')
            apply_richmenu(richmenu_ids['CONSENT'], user_id)
        elif session['keword_accepted'] == True and session['counseling_mode'] == False and session['survey_mode'] == False:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["START"]}')
            apply_richmenu(richmenu_ids['START'], user_id)
        elif session['counseling_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["COUNSELING"]}')
            apply_richmenu(richmenu_ids['COUNSELING'], user_id)
        elif session['survey_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["SURVEY"]}')
            apply_richmenu(richmenu_ids['SURVEY'], user_id)
        else:
            return True  # 問題ない場合はTrueを返す


    elif postback_data == 'consent' or postback_data == 'no_consent':
        if session['keyword_accepted'] == True and session['counseling_mode'] == False and session['survey_mode'] == False:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["START"]}')
            apply_richmenu(richmenu_ids['START'], user_id)
        elif session['counseling_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["COUNSELING"]}')
            apply_richmenu(richmenu_ids['COUNSELING'], user_id)
        elif session['survey_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["SURVEY"]}')
            apply_richmenu(richmenu_ids['SURVEY'], user_id)
        else:
            return True  # 問題ない場合はTrueを返す
    
    elif postback_data == 'start_chat' or postback_data == 'shop':
        if session['counseling_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["COUNSELING"]}')
            apply_richmenu(richmenu_ids['COUNSELING'], user_id)
        elif session['survey_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["SURVEY"]}')
            apply_richmenu(richmenu_ids['SURVEY'], user_id)
        else:
            return True  # 問題ない場合はTrueを返す
        
    elif postback_data == 'reset_history':
        if session['survey_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["SURVEY"]}')
            apply_richmenu(richmenu_ids['SURVEY'], user_id)
        else:
            return True
    
    elif postback_data == 'end_chat' or postback_data == 'check_time' or postback_data == 'back_to_menu' or postback_data == 'update_time':
        if session['survey_mode'] == True:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["SURVEY"]}')
            apply_richmenu(richmenu_ids['SURVEY'], user_id)
        else:
            return True

    elif postback_data == 'end_survey':
        if session['survey_mode'] == False:
            logger.info(f'{RD}[REAPPLY]{R} user: {user_id}, richmenu: {richmenu_ids["START"]}')
            apply_richmenu(richmenu_ids['START'], user_id)
        else:
            return True
    
    return False  # 再適用した場合はFalseを返す



if __name__ == '__main__':
    delete_all_richmenu()