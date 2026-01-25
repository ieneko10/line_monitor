"""
オウム返しを行うLINE Messaging APIのサンプルコード
cd example
python -m src.1_echo.main
"""

import sys

from flask import Flask, request, abort
from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

# 自作モジュールのインポート
from utils.set_logger import start_logger
from utils.tool import load_config, extract_event_info
from utils.ansi import *

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


# Flaskアプリケーションの初期化
app = Flask(__name__)

# LINE APIの設定
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)


@app.route("/callback", methods=['POST'])
def callback():
    """
    LINEからのWebhookリクエストを処理するエンドポイント。
    リクエストヘッダーから署名を取得し、リクエストボディを渡してイベントをハンドルする。
    """
    logger.info(f'[Recieved Request] {extract_event_info(request.json)}')
    # logger.info(f"[Recieved Request]\n{format_structure(request.json, indent=1)}")    # 冗長になるためコメントアウト

    # リクエストヘッダーからLINEの署名を取得
    signature = request.headers.get('X-Line-Signature')
    # リクエストボディをテキスト形式で取得
    body = request.get_data(as_text=True)

    try:
        # 署名とリクエストボディからイベント処理を実行
        handler.handle(body, signature)
    except Exception as e:
        # エラー発生時はエラー内容を出力し、400エラーを返す
        print("Error handling request:", e)
        abort(400)

    # 正常に処理された場合は "OK" を返す
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """
    受信したテキストメッセージと同じ内容を返信するエコー機能。
    """

    # ApiClientをコンテキストマネージャとして使用し、リソース管理を自動化
    with ApiClient(configuration) as api_client:
        # MessagingApiインスタンスの生成
        line_bot_api = MessagingApi(api_client)

        # 返信リクエストを作成（受信したテキストをそのまま返信）
        reply_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=event.message.text)]  # 返信メッセージを設定
        )

        # 作成したリプライリクエストをLINE APIへ送信
        line_bot_api.reply_message_with_http_info(reply_request)

        logger.info(f'[System Reply Message] {event.message.text}')


if __name__ == "__main__":
    
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
