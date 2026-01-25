import sys

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging.models import BroadcastRequest
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    ButtonsTemplate,
    MessageAction,
    TemplateMessage,
    PushMessageRequest,
    TextMessage
)

# 自作モジュールのインポート
from utils.set_logger import start_logger
from utils.tool import load_config, split_message

# ロガーと設定の読み込み
config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(config_path)
logger = start_logger(conf['LOGGER']['SYSTEM'])

YES = "1:" + conf["YES_ANSWER"]
NO = "2:" + conf["NO_ANSWER"]

DEBUG_PUSH_MESSAGE = conf.get("DEBUG_PUSH_MESSAGE", False)
DEBUG_USER_ID = conf.get("DEBUG_USER_ID", "")

LINE_CHANNEL_SECRET = conf["LINE_CHANNEL_SECRET"]
LINE_ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]

#mil-ai
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)

def reply_to_line_user(event, message):
    
    msgs = split_message(message)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 返信リクエストを作成
        reply_request = ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=msgs
        )

        # 作成したリプライリクエストをLINE APIへ送信
        line_bot_api.reply_message_with_http_info(reply_request)


def push_to_line_user(user_id, message, split=True):
    """
    指定されたユーザにメッセージをプッシュ送信する
    """
    if split:
        msgs = split_message(message)
    else:
        msgs = [TextMessage(text=message)]

    current_usage, quota = check_message_quota()

    logger.info(f"[Push Message] user_id: {user_id}")
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message_with_http_info(
            PushMessageRequest(
                to=user_id,
                messages=msgs
            )
        )

    updated_usage, _ = check_message_quota()
    logger.info(f'[Push Usage] {current_usage}/{quota} -> {updated_usage}/{quota}')


def send_yes_no_buttons(
    configuration,
    reply_token,
    question_text: str,
    alt_text: str = "",
    prepend_message: str = None,
    split: bool = True
):
    """
    YES/NO ボタン付きのメッセージを送信する共通関数。

    Parameters:
        configuration: LINE Messaging API の設定オブジェクト
        reply_token: イベントから取得した reply_token
        question_text: ボタンテンプレートに表示する質問文
        alt_text: テンプレートの代替テキスト
        prepend_message: 先頭に追加するテキスト（任意）
    """
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # prepend_message が指定されている場合は分割してメッセージリストに追加
        if prepend_message: # prepend_message が '' でない場合
            if split:
                messages = split_message(prepend_message)
            else:
                messages = [TextMessage(text=prepend_message)]
        else:
            messages = []

        messages.append(
            TemplateMessage(
                alt_text=alt_text,
                template=ButtonsTemplate(
                    text=question_text,
                    actions=[
                        MessageAction(label=YES, text=YES),
                        MessageAction(label=NO, text=NO)
                    ]
                )
            )
        )

        # メッセージの数が5を超える場合は警告を出す
        # LINE Messaging APIの仕様では、1回のリプライで送信できるメッセージは最大5つまで
        if len(messages) > 5:
            logger.warning(
                f"[Too Many Message] num_msgs:{len(messages)}. Only the first 5 will be sent."
            )
            messages = messages[:5]

        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages
            )
        )


def check_message_quota():
    """
    メッセージ送信の可能回数を確認する関数
    LINE Messaging APIのクォータ情報を取得し、現在の使用量を表示
    """
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        quota = messaging_api.get_message_quota()
        current_usage = messaging_api.get_message_quota_consumption()
        
        return current_usage.total_usage, quota.value


def broadcast_message(message: str):
    """
    一斉送信メッセージを送信する関数
    """
    
    try:
        # デバッグモードの場合は指定されたユーザにのみ送信
        if DEBUG_PUSH_MESSAGE:
            if DEBUG_USER_ID != "":
                logger.info(f"[Push Message] Sending to DEBUG_USER_ID: {DEBUG_USER_ID}")
                push_to_line_user(DEBUG_USER_ID, message, split=False)
            else:
                logger.error("[Push Message] DEBUG_USER_ID is not set. Cannot send debug message.")
            return
        
        else:
            current_usage, quota = check_message_quota()
            logger.info(f"[Broadcast Message]")
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                text_message = TextMessage(text=message)
                
                # 一斉送信リクエストを作成
                line_bot_api.broadcast_with_http_info(
                    BroadcastRequest(
                        messages=[text_message]
                    )
                )
            updated_usage, _ = check_message_quota()
            logger.info(f'[Push Usage] {current_usage}/{quota} -> {updated_usage}/{quota}')

    except Exception as e:
        logger.error(f"[Broadcast Error] Failed to send broadcast message:\n  {repr(e)}")
        return
    