import requests

# LINEチャンネルアクセストークン
ACCESS_TOKEN = '1pFR6RHEjX5BeNcvfcOxGTq0vn6pFpTv538Dx0wkEm6JZpF3e4wV4Mf6pq4uetbE5StJaUX7ebulAGP1Dor+as7TVehz4X7bGH9G+L77Pn7uirDHtWo5guHYLZYApg63sHgJ7bYYBfbm/LczEFF8zgdB04t89/1O/w1cDnyilFU='

def create_and_apply_richmenu(user_id, url):
    """
    ユーザーIDを受け取り、リッチメニューの作成・画像アップロード、
    及びそのリッチメニューを指定ユーザーに適用する関数
    """
    url = url + "/checkout?LINE_ID=" + user_id

    # リッチメニュー作成APIのURL
    richmenu_url = "https://api.line.me/v2/bot/richmenu"

    # リクエストヘッダー（JSON）
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    # リッチメニュー作成のデータ
    richmenu_data = {
        "size": {
            "width": 2500,
            "height": 1686
        },
        "selected": False,
        "name": "デフォルトのリッチメニューのテスト",
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
                    "label": "E-mailアドレスの確認・登録",
                    "data": "action=send_flex"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": 585,
                    "width": 625,
                    "height": 1686
                },
                "action": {
                    "type": "postback",
                    "label": "料金１",
                    "data": "action=send_flex"
                }
            },
            {
                "bounds": {
                    "x": 625,
                    "y": 585,
                    "width": 625,
                    "height": 1686
                },
                "action": {
                    "type": "uri",
                    "label": "料金２",
                    "uri": url
                }
            },
            {
                "bounds": {
                    "x": 1250,
                    "y": 585,
                    "width": 625,
                    "height": 1686
                },
                "action": {
                    "type": "uri",
                    "label": "料金３",
                    "uri": "https://techblog.lycorp.co.jp/ja/"
                }
            },
            {
                "bounds": {
                    "x": 1875,
                    "y": 585,
                    "width": 625,
                    "height": 1686
                },
                "action": {
                    "type": "uri",
                    "label": "料金４",
                    "uri": "https://techblog.lycorp.co.jp/ja/"
                }
            }
        ]
    }

    # リッチメニュー作成のリクエスト送信
    response = requests.post(richmenu_url, headers=headers, json=richmenu_data)
    if response.status_code == 200:
        richmenu_id = response.json()["richMenuId"]
        print(f"RichMenu ID: {richmenu_id}")

        # 画像アップロードAPIのURL
        image_upload_url = f"https://api-data.line.me/v2/bot/richmenu/{richmenu_id}/content"

        # 画像アップロードのヘッダー
        image_headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "image/png"
        }

        # 画像ファイルを開いてPOSTリクエストを送信
        with open("./image/price_large.png", "rb") as img:
            image_response = requests.post(image_upload_url, headers=image_headers, data=img)

        if image_response.status_code == 200:
            print("画像が正常にアップロードされました。")

            # ユーザーにリッチメニューを適用するAPIのURL
            apply_richmenu_url = f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{richmenu_id}"

            # ユーザー適用用ヘッダー
            apply_headers = {
                "Authorization": f"Bearer {ACCESS_TOKEN}"
            }
            
            apply_response = requests.post(apply_richmenu_url, headers=apply_headers)

            if apply_response.status_code == 200:
                print(f"ユーザー {user_id} にリッチメニューが適用されました。")
            else:
                print("ユーザーへのリッチメニュー適用に失敗しました:", apply_response.json())

        else:
            print("画像アップロードに失敗しました:", image_response.json())

    else:
        print("リッチメニュー作成に失敗しました:", response.json())

def canccel_richmenu(user_id):
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


if __name__ == "__main__":
    # 関数実行例: ユーザーIDをコンソールから受け取る
    user_id = "U0793e9b422849c7f11d256c7634680e7"
    # create_and_apply_richmenu(user_id)
    canccel_richmenu(user_id)
