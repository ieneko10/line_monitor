import os
import threading

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    ButtonsTemplate,
    MessageAction,
    TemplateMessage,
    TextMessage,
    PushMessageRequest
)
from linebot.v3.webhooks import MessageEvent, StickerMessageContent, TextMessageContent
from linebot.v3.messaging.models.flex_message import FlexMessage
from linebot.v3.messaging.models.flex_container import FlexContainer


# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from django.conf import settings
from counseling_linebot.utils.bot import CounselorBot
from counseling_linebot.utils import richmenu
from counseling_linebot.utils.tool import load_config, split_message
from counseling_linebot.utils.db_handler import (
    get_session,
    save_session,
    save_flag,
    reset_time,
    set_time,
    init_survey,
    save_survey,
    get_survey,
    save_survey_results,
)

# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
richmenu_ids = load_config(conf['RICHMENU_PATH'])
logger = start_logger(conf['LOGGER']['SYSTEM'])

# ユーザごとのタイマーを管理する辞書．ユーザはボタン以外の動作（リッチメニュー操作や任意のテキスト送信）が可能なので，それらを無効にする
timers = {}

STAMP = conf["STAMP"]
LANGUAGE = conf["LANGUAGE"]
YES = "1:" + conf["YES_ANSWER"]
NO = "2:" + conf["NO_ANSWER"]
INIT_MESSAGE = conf["INIT_MESSAGE"]
MODEL_TYPE = conf["MODEL_TYPE"]
OPENAI_MODEL = conf["OPENAI_MODEL"]
GEMINI_MODEL = conf["GEMINI_MODEL"]
VERYGOOD = "1:" + conf["SURVEY"]["VERYGOOD"]
GOOD = "2:" + conf["SURVEY"]["GOOD"]
FAIR = "3:" + conf["SURVEY"]["FAIR"]
BAD = "4:" + conf["SURVEY"]["BAD"]
VERYBAD = "5:" + conf["SURVEY"]["VERYBAD"]
SURVEY_MESSAGES = conf["SURVEY"]['SURVEY_MESSAGES']
SURVEY_LAST_MESSAGE = conf["SURVEY"]['SURVEY_LAST_MESSAGE']
SURVEY_INIT_MESSAGE = conf["SURVEY"]['SURVEY_INIT_MESSAGE']
FINISH_MESSAGE = conf["SURVEY"]['FINISH_MESSAGE']

LINEBOT_DB = conf["LINEBOT_DB"]

LINE_CHANNEL_SECRET = conf["LINE_CHANNEL_SECRET"]
LINE_ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]

#mil-ai
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)


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



def shop(event, tunnel):

    user_id = event.source.user_id
    bubble_dict = generate_shop_flex_message(url=tunnel, user_id=user_id)

    flex_contents = FlexContainer.from_dict(bubble_dict)
    flex_message = FlexMessage(
        alt_text="決済ページ",
        contents=flex_contents
    )

    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[flex_message]
            )
        )
    logger.debug(f"[Shop Flex Message] user: {user_id}")



def start_chat(event, reset=False):
    user_id = event.source.user_id

    # モデルタイプに応じてAPIキーとモデル名を設定
    if MODEL_TYPE.lower() == "gemini":
        api_key = os.environ.get('OPENAI_API_KEY', '')  # OpenAI APIキーは必須パラメータなので空文字でも設定
        google_api_key = conf.get('GOOGLE_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))
        model_name = GEMINI_MODEL
    else:
        api_key = os.environ['OPENAI_API_KEY']
        google_api_key = ""
        model_name = OPENAI_MODEL

    bot = CounselorBot(LINEBOT_DB, 
                INIT_MESSAGE, 
                api_key=api_key, 
                model_name=model_name,
                model_type=MODEL_TYPE,
                google_api_key=google_api_key,
                system_prompt_path="./counseling_linebot/prompts/system_prompt.txt", 
                example_files=["./counseling_linebot/prompts/case1_0.txt", "./counseling_linebot/prompts/case2_0.txt", "./counseling_linebot/prompts/case3_0.txt", "./counseling_linebot/prompts/case4_0.txt", "./counseling_linebot/prompts/case5_0.txt", "./counseling_linebot/prompts/case6_1.txt"]
                )
    
    init_message = bot.start_message(user_id)

    if "]" in init_message:
        init_message = init_message.split("]")[1].strip()
    else:
        init_message = init_message.strip()

    # init_messageを\n\nで分割し，分けて送信
    if reset:
        init_message = f"### システム通知 ###\n対話履歴をリセットしました。\n\n{init_message}"

    msgs = split_message(init_message)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=msgs
            )   
        )

                
def reply(event, tunnel):
    if STAMP and isinstance(event.message, StickerMessageContent):
        uttr = f"スタンプ（意図）: {event.message.keywords}"
    elif isinstance(event.message, TextMessageContent):
        uttr = event.message.text
    else:
        return

    user_id = event.source.user_id
    session = get_session(user_id)

    # モデルタイプに応じてAPIキーとモデル名を設定
    if MODEL_TYPE.lower() == "gemini":
        api_key = os.environ.get('OPENAI_API_KEY', '')  # OpenAI APIキーは必須パラメータなので空文字でも設定
        google_api_key = conf.get('GOOGLE_API_KEY', os.environ.get('GOOGLE_API_KEY', ''))
        model_name = GEMINI_MODEL
    else:
        api_key = os.environ['OPENAI_API_KEY']
        google_api_key = ""
        model_name = OPENAI_MODEL

    bot = CounselorBot(LINEBOT_DB, 
                INIT_MESSAGE, 
                api_key=api_key, 
                model_name=model_name,
                model_type=MODEL_TYPE,
                google_api_key=google_api_key,
                system_prompt_path="./counseling_linebot/prompts/system_prompt.txt", 
                example_files=["./counseling_linebot/prompts/case1_0.txt", 
                               "./counseling_linebot/prompts/case2_0.txt", 
                               "./counseling_linebot/prompts/case3_0.txt", 
                               "./counseling_linebot/prompts/case4_0.txt", 
                               "./counseling_linebot/prompts/case5_0.txt", 
                               "./counseling_linebot/prompts/case6_1.txt"]
                )
    response, is_finished = bot.reply(user_id, uttr, remove_thought=True)
    
    response = response.strip()
    
    if is_finished:
        session["counseling_mode"] = False  # カウンセリングモードを終了
        session["survey_mode"] = True       # アンケートモードを開始
        save_session(user_id, session)
        logger.debug(f'[Save Session] user: {user_id}\n  counseling_mode: {session["counseling_mode"]}\n  survey_mode: {session["survey_mode"]}')

        # タイマーをストップし，セッション内の時間を更新
        with threading.Lock():
            remaining_time = timers[user_id].cancel()  
            del timers[user_id]  # タイマーを削除
        set_time(user_id, remaining_time)  # セッション時間を更新

        richmenu.apply_richmenu(richmenu_ids['SURVEY'], user_id)  # アンケートのリッチメニューを適用
        survey(event, tunnel)    # アンケートを開始
    
    # 通常のカウンセリング対話の応答
    else:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)

            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response)]
                )   
            )



def send_end_message(user_id: str):
    """
    セッション終了時に指定ユーザへ「終了」メッセージをプッシュ送信し、
    セッション状態を削除する
    """
    session = get_session(user_id)
    try:
        logger.debug(f'[Send Message] 時間終了によるカウンセリング対話の終了メッセージと，アンケートの開始確認メッセージを送信')
        survey_push(user_id)  # アンケートを開始
    except Exception as e:
        logger.error(f"Failed to send end message to user {user_id}: {e}")
    
    reset_time(user_id)  # セッション時間をリセット
    richmenu.apply_richmenu(richmenu_ids['SURVEY'], user_id)  # アンケートのリッチメニューを適用
    session['counseling_mode'] = False
    session['survey_mode'] = True
    save_session(user_id, session)  # セッションを保存
    logger.debug(f'[Save Session] user: {user_id}\n  counseling_mode: {session["counseling_mode"]}\n  survey_mode: {session["survey_mode"]}')


def survey_push(user_id):
    """
    replyメッセージではなく、プッシュメッセージでアンケート開始確認を送信する
    """

    if os.path.exists(f"survey/trial_{LANGUAGE}_{user_id}.txt") is False:
        with open(f"survey/trial_{LANGUAGE}_{user_id}.txt", "w") as w:
            w.close()

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # YES/NOボタンを作成
        message_template = [
            TextMessage(text="時間となりましたので，カウンセリング対話を終了いたします。"),
            TextMessage(text=SURVEY_INIT_MESSAGE),
            TemplateMessage(
                alt_text="アンケートにご協力いただけますか？",
                template=ButtonsTemplate(
                    text="アンケートにご協力いただけますか？",
                    actions=[
                        MessageAction(label=YES, text=YES),
                        MessageAction(label=NO, text=NO),
                    ]
                )
            )
        ]
        line_bot_api.push_message_with_http_info(
            PushMessageRequest(
                to=user_id,
                messages=message_template
            )   
        )

        logger.debug(f'[Save Flag] flag: start_survey, user: {user_id}')
        save_flag(user_id, flag='start_survey')  # フラグを保存
    

def survey(event, tunnel):

    # eventがMessageEventであることを確認（PostbackEventのend_chatにより，surveyが呼ばれることもあるため）
    if isinstance(event, MessageEvent):
        uttr = event.message.text
    else:
        uttr = ''

    user_id = event.source.user_id
    session = get_session(user_id)

    # アンケート結果を保存するためのtxtファイルを作成
    if os.path.exists(f"survey/trial_{LANGUAGE}_{user_id}.txt") is False:
        with open(f"survey/trial_{LANGUAGE}_{user_id}.txt", "w") as w:
            w.close()

    survey_progress = session["survey_progress"]
    logger.debug(f"[Survey Progress] {survey_progress}/{len(SURVEY_MESSAGES)}, user {user_id}")

    # アンケートの開始確認メッセージを送信
    if survey_progress == 0:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            # YES/NOボタンを作成
            message_template = [
                TextMessage(text=SURVEY_INIT_MESSAGE),
                TemplateMessage(
                    alt_text="アンケートにご協力いただけますか？",
                    template=ButtonsTemplate(
                        text="アンケートにご協力いただけますか？",
                        actions=[
                            MessageAction(label=YES, text=YES),
                            MessageAction(label=NO, text=NO),
                        ]
                    )
                )
            ]
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=message_template
                )   
            )

        logger.debug(f'[Save Flag] flag: start_survey, user: {user_id}')
        save_flag(user_id, flag='start_survey')  # フラグを保存

    # 選択式アンケートの終了時，自由記述アンケートを送信
    elif survey_progress == len(SURVEY_MESSAGES):
        if uttr.startswith(VERYGOOD) or uttr.startswith(GOOD) or uttr.startswith(FAIR) or uttr.startswith(BAD) or uttr.startswith(VERYBAD):
            # session[SURVEY_MESSAGES[survey_progress-1]] = uttr
            survey_results = get_survey(user_id)
            survey_results[SURVEY_MESSAGES[survey_progress-1]] = uttr
            save_survey(user_id, survey_results)  # アンケート結果を保存
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=SURVEY_LAST_MESSAGE)]
                    )   
                )
            session["survey_progress"] = 100
            save_session(user_id, session)
            logger.debug(f'[Save Session] user: {user_id}\n  survey_progress: {session["survey_progress"]}')
        
        # 選択肢から回答されなかった場合，もう一度，最後の選択式アンケートを送信
        else:
            question_text = SURVEY_MESSAGES[survey_progress-1]
            message_template = [
                TemplateMessage(
                    alt_text="選択肢",
                    template=ButtonsTemplate(
                        text=question_text,
                        actions=[
                            MessageAction(label=VERYGOOD, text=VERYGOOD),
                            MessageAction(label=GOOD, text=GOOD),
                            MessageAction(label=FAIR, text=FAIR),
                            # MessageAction(label=BAD, text=BAD),
                            # MessageAction(label=VERYBAD, text=VERYBAD),
                        ]
                    )
                ),
                TemplateMessage(
                    alt_text="続き",
                    template=ButtonsTemplate(
                        text="(選択肢つづき)",
                        actions=[
                            # MessageAction(label=VERYGOOD, text=VERYGOOD),
                            # MessageAction(label=GOOD, text=GOOD),
                            # MessageAction(label=FAIR, text=FAIR),
                            MessageAction(label=BAD, text=BAD),
                            MessageAction(label=VERYBAD, text=VERYBAD),
                        ]
                    )
                )
            ]
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=message_template
                ) 
            )


    # 自由記述アンケート終了時
    elif survey_progress > len(SURVEY_MESSAGES):
        survey_results = get_survey(user_id)
        survey_results[SURVEY_LAST_MESSAGE] = uttr
        save_survey(user_id, survey_results)  # アンケート結果を保存
        
        save_survey_results(user_id)  # アンケート結果をファイルに保存

        # アンケート終了メッセージを送信
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=FINISH_MESSAGE)]
                )   
            )
            
        # 初期化
        richmenu.apply_richmenu(richmenu_ids['START'], user_id)  # リッチメニューを適用
        new_session_data = {"counseling_mode": False, "keyword_accepted": True, "survey_mode": False, "survey_progress": 0, "finished": False}
        save_session(user_id, new_session_data)
        logger.debug(f'[Reset Session] user: {user_id}')
        init_survey(user_id)  # アンケートを初期化

    # アンケート進行中
    elif survey_progress >= 1:
        # 選択肢からの回答の場合，survey_progressを1つ進める
        if uttr.startswith(VERYGOOD) or uttr.startswith(GOOD) or uttr.startswith(FAIR) or uttr.startswith(BAD) or uttr.startswith(VERYBAD):
            survey_results = get_survey(user_id)
            survey_results[SURVEY_MESSAGES[survey_progress-1]] = uttr
            save_survey(user_id, survey_results)  # アンケート結果を保存

            session["survey_progress"] = survey_progress + 1
            save_session(user_id, session)
            logger.debug(f'[Save Session] user: {user_id}\n  survey_progress: {session["survey_progress"]}')

            # session を再取得して最新の survey_progress を使用
            session = get_session(user_id)
        
        current_survey_progress = session.get("survey_progress", 1) # 1から始まる想定

        # 5択の回答ボタンを作成
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            # SURVEY_MESSAGES のインデックスは current_survey_progress - 1
            if current_survey_progress -1 < len(SURVEY_MESSAGES):
                question_text = SURVEY_MESSAGES[current_survey_progress-1]
            else:
                # アンケート項目がない場合はエラーまたは最終処理へ
                logger.error(f"Survey message index out of bounds for user {user_id}")
                # ここで最終メッセージを送信するなどの処理が必要かもしれない
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=SURVEY_LAST_MESSAGE)] # 仮
                    )
                )
                session["survey_progress"] = 100 # 完了状態へ
                save_session(user_id, session)
                logger.debug(f'[Save Session] user: {user_id}\n  survey_progress: {session["survey_progress"]}')
                return

            message_template = [
                TemplateMessage(
                    alt_text="選択肢",
                    template=ButtonsTemplate(
                        text=question_text,
                        actions=[
                            MessageAction(label=VERYGOOD, text=VERYGOOD),
                            MessageAction(label=GOOD, text=GOOD),
                            MessageAction(label=FAIR, text=FAIR),
                            # MessageAction(label=BAD, text=BAD),
                            # MessageAction(label=VERYBAD, text=VERYBAD),
                        ]
                    )
                ),
                TemplateMessage(
                    alt_text="続き",
                    template=ButtonsTemplate(
                        text="(選択肢つづき)",
                        actions=[
                            # MessageAction(label=VERYGOOD, text=VERYGOOD),
                            # MessageAction(label=GOOD, text=GOOD),
                            # MessageAction(label=FAIR, text=FAIR),
                            MessageAction(label=BAD, text=BAD),
                            MessageAction(label=VERYBAD, text=VERYBAD),
                        ]
                    )
                )
            ]
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=message_template
                ) 
            )
