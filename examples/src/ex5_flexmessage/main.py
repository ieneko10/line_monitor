"""
cd examples
python -m src.3_flexmessage.main
flex messageのサンプルコード
"""

import sys

from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter

from flask import Flask, render_template, redirect, jsonify

from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.messaging.models.flex_message import FlexMessage  # Flex Message を利用するためのインポート
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging.models.flex_container import FlexContainer
from linebot.v3.messaging.models.flex_component import FlexComponent

# 自作モジュールのインポート
from utils.set_logger import start_logger
from utils.tool import load_config
from utils.ansi import *
from src.ex4_stripe.checkout import create_checkout_session

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


app = Flask(__name__)


# LINE APIの設定
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"Error: {e}")
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):

    user_id = event.source.user_id

    # user_text = event.message.text
    if event.message.text == "/shop":
        # 1. Flex コンテナ辞書を生成
        bubble_dict = generate_shop_flex_message(url=tunnel, user_id=user_id)

        # 2. モデルに変換
        flex_contents = FlexContainer.from_dict(bubble_dict)
        flex_message = FlexMessage(
            alt_text="決済ページ",
            contents=flex_contents
        )

        # 3. ApiClient ブロック内でインスタンス生成＆送信
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
            )
        return
    
    # Flex Messageのコンテンツを定義
    container_dict = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Hello, LINE Bot!",
                    "size": "lg",
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": "これはFlex Messageです",
                    "size": "md"
                }
            ]
        }
    }
    flex_contents = FlexContainer.from_dict(container_dict)
    
    # Flex Messageのインスタンス作成（alt_textは代替テキスト）
    flex_message = FlexMessage(
        alt_text="Flex Message with Button",
        contents=flex_contents
    )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[flex_message]
            )
        )


def generate_shop_flex_message(url: str, user_id: str):
    def price_box(url, price, time_seconds):

        return {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": f"{time_seconds // 60}分",
                    "size": "md",
                    "weight": "bold"
                },
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "uri",
                        "label": f"¥{price}",
                        "uri": url
                    }
                }
            ]
        }
    
    url1 = url + '/checkout1?LINE_ID=' + user_id
    url2 = url + '/checkout2?LINE_ID=' + user_id
    url3 = url + '/checkout3?LINE_ID=' + user_id
    url4 = url + '/checkout4?LINE_ID=' + user_id

    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "lg",
            "contents": [
                price_box(url1, conf['ITEM_1']['PRICE'], conf['ITEM_1']['TIME']),
                price_box(url2, conf['ITEM_2']['PRICE'], conf['ITEM_2']['TIME']),
                price_box(url3, conf['ITEM_3']['PRICE'], conf['ITEM_3']['TIME']),
                price_box(url4, conf['ITEM_4']['PRICE'], conf['ITEM_4']['TIME']) 
            ]
        }
    }


@app.route('/checkout1', methods=['GET'])
def create_checkout_session1():
    # URLからパラメータを取得
    line_id = request.args.get('LINE_ID')
    # print(f"Received LINE_ID: {line_id}")

    try:
        session = create_checkout_session(
            product_name = conf['ITEM_1']['NAME'],
            unit_amount = conf['ITEM_1']['PRICE'],
            time_seconds = conf['ITEM_1']['TIME'],
            line_id = line_id,
            tunnel_url = tunnel
        )

        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/checkout2', methods=['GET'])
def create_checkout_session2():
    # URLからパラメータを取得
    line_id = request.args.get('LINE_ID')

    try:
        session = create_checkout_session(
            product_name = conf['ITEM_2']['NAME'],
            unit_amount = conf['ITEM_2']['PRICE'],
            time_seconds = conf['ITEM_2']['TIME'],
            line_id = line_id,
            tunnel_url = tunnel
        )
        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/checkout3', methods=['GET'])
def create_checkout_session3():
    # URLからパラメータを取得
    line_id = request.args.get('LINE_ID')

    try:
        session = create_checkout_session(
            product_name = conf['ITEM_3']['NAME'],
            unit_amount = conf['ITEM_3']['PRICE'],
            time_seconds = conf['ITEM_3']['TIME'],
            line_id = line_id,
            tunnel_url = tunnel
        )
        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    
    except Exception as e:
        return jsonify(error=str(e)), 400
    

@app.route('/checkout4', methods=['GET'])
def create_checkout_session4():
    # URLからパラメータを取得
    line_id = request.args.get('LINE_ID')

    try:
        session = create_checkout_session(
            product_name = conf['ITEM_4']['NAME'],
            unit_amount = conf['ITEM_4']['PRICE'],
            time_seconds = conf['ITEM_4']['TIME'],
            line_id = line_id,
            tunnel_url = tunnel
        )

        # 生成された Checkout Session の URL へリダイレクト
        return redirect(session.url, code=303)
    
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/success')
def success():
    return render_template("success.html")



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