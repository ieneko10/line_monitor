"""
cd examples
python -m src.2_richmenu.main
richmenuのサンプルコード
「menu」というメッセージを受け取ったら、リッチメニューを適用する。
"""
import sys, requests

from flask import Flask, request, abort
from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import PostbackEvent, MessageEvent, TextMessageContent

# 自作モジュールのインポート
from utils.set_logger import start_logger
from utils.tool import load_config, extract_event_info, format_structure
from utils.ansi import *
from utils.richmenu import create_test_menu

main_config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(main_config_path)
logger = start_logger(conf['LOGGER']['MAIN'])

# 設定
PORT = conf["PORT"]
LINE_CHANNEL_SECRET = conf["LINE_CHANNEL_SECRET"]
LINE_ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]


# ngrokを使うかどうか
if conf["NGROK"]:
    from pyngrok import ngrok
    tunnel = ngrok.connect(PORT, "http").public_url
else:
    tunnel = conf["SERVER_URL"] + f":{PORT}"
logger.info(f"{BG}[Public URL]{R} {tunnel}")


# リッチメニューIDを取得（なければ生成）
RICHMENU_ID = conf['RICHMENU']['TEST']
if RICHMENU_ID == None:
    image_path = "./image/test.png"
    richmenu_id = create_test_menu(image_path=image_path)
    RICHMENU_ID = richmenu_id
user_ids = []
logger.info(f"[RichMenu ID] {RICHMENU_ID}")


app = Flask(__name__)


# LINE APIの設定
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)

@app.route("/callback", methods=['POST'])
def callback():
    logger.info(f'\n[Recieved Request] {extract_event_info(request.json)}')

    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """
    「menu」というメッセージを受け取ったら、リッチメニューを適用する。
    """
    user_id = event.source.user_id

    if event.message.text == 'menu':

        # リッチメニューの更新処理        
        # ユーザーにリッチメニューを適用するAPIのURL
        apply_richmenu_url = f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{RICHMENU_ID}"

        # ユーザー適用用ヘッダー
        apply_headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
        }
        
        apply_response = requests.post(apply_richmenu_url, headers=apply_headers)

        if apply_response.status_code == 200:
            user_ids.append(user_id)
            logger.debug(f"[RichMenu Applied] test.png,  user: {user_id}")
        else:
            logger.error(f"[RichMenu Apply Failed] error: {apply_response.json()}\nuser: {user_id}")


        # ApiClientをコンテキストマネージャとして使用し、リソース管理を自動化
        with ApiClient(configuration) as api_client:
            # MessagingApiインスタンスの生成
            line_bot_api = MessagingApi(api_client)

            # 返信リクエストを作成（受信したテキストをそのまま返信）
            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text='リッチメニューを更新しました。')]  # 返信メッセージを設定
            )

            # 作成したリプライリクエストをLINE APIへ送信
            line_bot_api.reply_message_with_http_info(reply_request)

        logger.info(f'[System Reply Message] リッチメニューを更新しました。')



@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id

    # 送信されたデータをチェック
    if event.postback.data == "test_richmenu":

        # 返信テキストにユーザIDを含める
        text = f'リッチメニューのテストです。\nユーザID: {user_id[:8]}...'

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=text)]
                )
            )

        logger.info(f'[System Reply Message] {repr(text)}')


if __name__ == "__main__":

    # リッチメニュー一覧取得
    headers = {'Authorization': f'Bearer {LINE_ACCESS_TOKEN}'}
    response = requests.get('https://api.line.me/v2/bot/richmenu/list', headers=headers)
    richmenus = response.json().get('richmenus', [])
    formatted_richmenus = format_structure(richmenus)
    # logger.debug(f"{formatted_richmenus}")

    
    # デバッグモードでFlaskを起動
    if conf['DEBUG'] == True:
        if conf['NGROK'] == False and conf['SERVER_URL'] == "https://mil-ai.net":
            logger.warning(f"{RD}[WARNING]{R} \"{conf['SERVER_URL']}\"では、デバッグモードでの起動はできません。config/main.yaml の NGROK設定を True に変更してください。")
            sys.exit(1)

        app.run(host='0.0.0.0', port=PORT)

    
    # 本番モードでcherootのWSGIServerを起動
    else:
        server = WSGIServer(("0.0.0.0", PORT), app)

        # SSL証明書の設定（ローカルで動かす場合はngrokを利用）
        if conf['NGROK'] == False:
            server.ssl_adapter = BuiltinSSLAdapter('/cert/server.crt', '/cert/server.key')

        try:
            server.start()
        
        except KeyboardInterrupt:
            server.stop()
            logger.info("[KeyboardInterrupt]")
    

    for user_id in user_ids:
        # リッチメニューの削除
        delete_richmenu_url = f"https://api.line.me/v2/bot/user/{user_id}/richmenu"
        delete_headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
        }
        delete_response = requests.delete(delete_richmenu_url, headers=delete_headers)
        if delete_response.status_code == 200:
            logger.info(f"[RichMenu Deleted] user: {user_id}")
        else:
            logger.error(f"[RichMenu Delete Failed] error: {delete_response.json()}\nuser: {user_id}")
