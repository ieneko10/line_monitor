
import os, sys  
import stripe
import threading
from waitress import serve
from ruamel.yaml import YAML
from watchdog.observers import Observer
from cheroot.wsgi import Server as WSGIServer
from cheroot.ssl.builtin import BuiltinSSLAdapter
from flask import Flask, request, abort, jsonify, redirect, render_template

from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, FollowEvent, PostbackEvent

# 自作
from bot import CounselorBot
from utils.ansi import *
from utils import richmenu
from utils.maintenance import FileChangeHandler, maintenace_mode_on
from utils.set_logger import start_logger
from utils.db_handler import (
    init_db,
    init_settings_table,
    set_maintenance_mode,
    get_maintenance_mode,
    register_user,
    get_all_users,
    get_session,
    save_session,
    reset_all_sessions,
    get_flag,
    save_flag,
    reset_flag,
    reset_all_flags,
    get_time,
    increment_time,
    set_time,
    init_survey,
    save_survey_results
)
from utils.tool import (
    TrackableTimer,
    format_structure,
    extract_event_info,
    load_config,
    create_checkout_session,
    create_directory,
    generate_session_id
)
from utils.main_massage import (
    shop,
    reply,
    start_chat,
    send_end_message,
    survey,
    timers
)
from utils.template_message import (
    reply_to_line_user,
    push_to_line_user,
    send_yes_no_buttons
)

# ディレクトリが存在しない場合は作成
create_directory()

# ロガーと設定の読み込み
main_config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(main_config_path)
logger = start_logger(conf['LOGGER']['SYSTEM'])

# ChatGPTのキー
os.environ['OPENAI_API_KEY'] = conf['OPENAI_API_KEY']
os.environ["ANTHROPIC_API_KEY"] = conf["ANTHROPIC_API_KEY"]

# Telegramのキー CounselorAITest
TELEGRAM_KEY = conf["TELEGRAM_KEY"]

# モデルを指定
OPENAI_MODEL = conf["OPENAI_MODEL"]
TEMPERATURE = conf["TEMPERATURE"]
MAX_TOKENS = conf["MAX_TOKENS"]

KEYWORD_MESSAGE = conf["KEYWORD_MESSAGE"]
INIT_MESSAGE = conf['INIT_MESSAGE']

# 対話開始キーワードが必要かどうか
NEED_START_KEYWORD = conf["NEED_START_KEYWORD"]

# 2択の質問
YES = "1:" + conf["YES_ANSWER"]
NO = "2:" + conf["NO_ANSWER"]

SESSIONS_DB = conf["SESSIONS_DB"]
LINEBOT_DB = conf["LINEBOT_DB"]

LINE_CHANNEL_SECRET = conf["LINE_CHANNEL_SECRET"]
LINE_ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]

stripe.api_key = conf['STRIPE_SECRET']
endpoint_secret = conf['STRIPE_WEBHOOK']

# PORT番ポートのHTTPトンネルを開設する
PORT = conf["PORT"]

# ngrokを使うかどうか
if conf["NGROK"]:
    from pyngrok import ngrok
    tunnel = ngrok.connect(PORT, "http").public_url
else:
    tunnel = conf["SERVER_URL"] + f":{PORT}"
logger.info(f"{BG}[Public URL]{R} {tunnel}")


# データベースが存在しない場合は初期化
if not os.path.exists(SESSIONS_DB):
    init_db()
init_settings_table()   # メンテナンスモード用の設定テーブルを初期化


# リッチメニューIDを取得（なければ生成）
if os.path.exists(conf['RICHMENU_PATH']):
    richmenu_ids = load_config(conf['RICHMENU_PATH'])
else:
    richmenu_ids = None
richmenu_ids = richmenu.create_richmenus(richmenu_ids)
yaml = YAML()
yaml.preserve_quotes = True  # コメントを保持
with open(conf['RICHMENU_PATH'], 'w', encoding='utf-8') as f:    # 書き戻し（コメント・順序を保持したまま）
    yaml.dump(richmenu_ids, f)


app = Flask(__name__)

#mil-ai
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)


@app.route("/callback", methods=['POST'])
def callback():
    logger.debug(f'\n[Recieved Request] {extract_event_info(request.json)}')
    # logger.debug(f"\n[Recieved Request]\n{format_structure(request.json, indent=1)}")    # 冗長になるためコメントアウト

    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.debug("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


# --- Followイベントハンドラ（友達追加時） ---
@handler.add(FollowEvent)
def handle_follow(event):
    logger.debug(f"[Follow Event] user: {event.source.user_id}")

    # ユーザのユーザIDを取得
    user_id = event.source.user_id
    session = get_session(user_id)

    # 初めて友達登録したユーザの場合、セッションとフラグを初期化
    if session is None or session['keyword_accepted'] == False:
        if session is None:
            logger.info(f"[New User] user: {user_id} (session not found)")
        elif session['keyword_accepted'] == False:
            logger.info(f"[Refollow] user: {user_id} (keyword not accepted)")
        register_user(user_id)  # ユーザをデータベースに登録

        # メンテナンス中の場合
        if get_maintenance_mode():
            logger.debug(f"[Maintenance Mode] user: {event.source.user_id} tried to follow during maintenance mode.")
            msg = '友達登録ありがとうございます。\n\n現在、メンテナンス中のため、操作を受け付けていません。\n\nしばらく時間をおいてから再度お試しください。'
            reply_to_line_user(event, msg)
            richmenu.apply_richmenu(richmenu_ids['MAINTENANCE'], user_id)  # メンテナンス用のリッチメニューを適用（基本的に適用されているはずだが，たまにバグるため）
            return

        richmenu.apply_richmenu(richmenu_ids['CONSENT'], user_id)   # リッチメニューを作成・適用

        # 同意を求めるメッセージを送信
        logger.debug(f"[Send Message] user: {user_id}\n  同意を求めるメッセージを送信")
        send_yes_no_buttons(configuration,
                            reply_token=event.reply_token,
                            question_text='同意しますか？',
                            alt_text='同意の確認',
                            prepend_message='友達登録ありがとうございます！\n\n'+KEYWORD_MESSAGE,
                            split=False  # 同意メッセージは分割しない
                            )
        save_flag(user_id, flag='consent')  # フラグを保存
        logger.debug(f'[Save Flag] flag: consent, user: {user_id}')
    
    else:
        logger.info(f'[Refollow] user: {user_id}')
        richmenu.apply_richmenu(richmenu_ids['START'], user_id)  # リッチメニューを作成・適用

        msg = '友達登録ありがとうございます！\n\n対話を開始するには、下のメニューを開き、操作を行ってください。'
        logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
        reply_to_line_user(event, msg)
    
    init_survey(user_id)  # アンケートを初期化
    

# ユーザがリッチメニューのボタンを押したときのハンドラ
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id

    if get_maintenance_mode():
        logger.debug(f"[Maintenance Mode] user: {event.source.user_id} tried to postback during maintenance mode.")
        msg = '現在、メンテナンス中のため、操作を受け付けていません。\n\nしばらく時間をおいてから再度お試しください。'
        reply_to_line_user(event, msg)
        if event.postback.data != 'maintenance':
            richmenu.apply_richmenu(richmenu_ids['MAINTENANCE'], user_id)  # メンテナンス用のリッチメニューを適用（基本的に適用されているはずだが，たまにバグるため）
        return

    session = get_session(user_id)
    logger.debug(f'[Postback Session] user: {user_id}\n{format_structure(session, indent=1)}\n  flag: {get_flag(user_id)}\n  time: {get_time(user_id)}')
    
    # 送信されたデータをチェック
    check_flag = richmenu.check_richmenu(session, event.postback.data, user_id, richmenu_ids)  # リッチメニューのチェックと適用
    if check_flag == False:
        return  # リッチメニューの再適用を行い，終了
    # logger.debug(f'[Postback Data] {event.postback.data}')
    if event.postback.data == "consent":
        logger.debug(f"[Send Message] user: {user_id}\n  同意を求めるメッセージを送信")
        send_yes_no_buttons(configuration,
                            reply_token=event.reply_token,
                            question_text='同意しますか？',
                            alt_text='同意の確認',
                            prepend_message=KEYWORD_MESSAGE,
                            split=False  # 同意メッセージは分割しない
        )
        
        logger.debug(f'[Save Flag] flag: consent, user: {user_id}')
        save_flag(user_id, flag='consent')  # フラグを保存

    elif event.postback.data == "no_consent":
        msg = 'ご同意いただけない場合は、カウンセリング対話を開始できません。'
        logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
        reply_to_line_user(event, msg)

    elif event.postback.data == "shop":
        shop(event, tunnel)

    elif event.postback.data == "reset_history":
        # Chatの開始，またはカウンセリング時間の確認
        logger.debug(f'[Send Message] user: {user_id}\n  対話履歴のリセットの確認メッセージを送信')
        send_yes_no_buttons(configuration,
                            reply_token=event.reply_token,
                            question_text="本当に対話履歴をリセットしますか？\n\nリセットすると、これまでの対話履歴がすべて消去されます。",
                            alt_text="対話履歴のリセットの確認",
                            )

        save_flag(user_id, flag='reset_history')  # フラグを保存
        logger.debug(f'[Save Flag] flag: reset_history, user: {user_id}')

    elif event.postback.data == "start_chat":
        # 同意が必要な場合、同意を求めるメッセージを送信
        if NEED_START_KEYWORD and session["keyword_accepted"] == False:
            msg = 'カウンセリング対話を開始する前に、同意が必要です。\n\n下のメニューから同意を行ってください。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)

        # 通常，メニューの変更により，カウンセリング対話中は"start_chat"は呼ばれないが，メニュー更新バグで呼ばれることがある
        elif session['counseling_mode'] == True:
            msg = 'すでにカウンセリング対話が開始されています。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)
            # start_chatが押されてしまった場合，リッチメニューを更新し直す
            richmenu.apply_richmenu(richmenu_ids['COUNSELING'], user_id)

        else:
            session_time = get_time(user_id)
            if session_time == 0:
                msg = 'メニューからご希望の時間を選択してください。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)
            
            else:
                # Chatの開始，またはカウンセリング時間の確認
                logger.debug(f'[Send Message] user: {user_id}\n  カウンセリング対話の開始確認メッセージを送信')
                minutes = int(session_time // 60)
                seconds = int(session_time % 60)
                send_yes_no_buttons(configuration,
                                    reply_token=event.reply_token,
                                    question_text=f"現在のカウンセリング時間は{minutes}分{seconds:02d}秒です。カウンセリング対話を開始しますか？",
                                    alt_text="カウンセリング対話の開始確認",
                                    )
                save_flag(user_id, flag='start_chat')  # フラグを保存
                logger.debug(f'[Save Flag] flag: start_chat, user: {user_id}')

    elif event.postback.data == "end_chat":
        assert session['counseling_mode'] == True, "カウンセリングモードでないのにend_chatが呼ばれました"
        
        logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話の終了確認メッセージを送信")
        send_yes_no_buttons(configuration,
                            reply_token=event.reply_token,
                            question_text="本当にカウンセリング対話を終了しますか？\n\n終了しても、残った時間は保持されます。",
                            alt_text="カウンセリング対話の終了確認",
                            )

        save_flag(user_id, flag='end_chat')  # フラグを保存
        logger.debug(f'[Save Flag] flag: end_chat, user: {user_id}')


    elif event.postback.data == "check_time":
        logger.debug(f"[Checking Remaining Time] user {user_id}")
        with threading.Lock():
            remaining_time = timers[user_id].remaining_time()  # タイマーから残り時間を取得
        remaining_time = remaining_time // 60  # 秒を分に変換
        richmenu.apply_richmenu(richmenu_ids['REMAINING_TIME'][remaining_time], user_id)  # 残り時間に応じたリッチメニューを適用
    
    elif event.postback.data == "back_to_menu":
        logger.debug(f"[Back to Menu] user {user_id}")
        richmenu.apply_richmenu(richmenu_ids['COUNSELING'], user_id)  # カウンセリングセッションのリッチメニューを適用

    elif event.postback.data == "update_time":
        logger.debug(f"[Update Remaining Time] user {user_id}")
        with threading.Lock():
            remaining_time = timers[user_id].remaining_time()  # タイマーから残り時間を取得
        remaining_time = remaining_time // 60  # 秒を分に変換
        richmenu.apply_richmenu(richmenu_ids['REMAINING_TIME'][remaining_time], user_id)

    elif event.postback.data == "end_survey":
        logger.debug(f"[Send Message] user: {user_id}\n  アンケートの終了確認メッセージを送信")
        send_yes_no_buttons(configuration,
                            reply_token=event.reply_token,
                            question_text="アンケートを終了しますか？",
                            alt_text="アンケートの終了確認",
                            )

        save_flag(user_id, flag='end_survey')  # フラグを保存
        logger.debug(f'[Save Flag] flag: end_survey, user: {user_id}')
    
    elif event.postback.data == 'maintenance':
        logger.warning(f'[WARNING] user: {user}  メンテナンス状態でないのに，メンテナンスメニューが適用されています。\n  再度リッチメニューを更新します。')
        if session['keyword_accepted'] == False:
            richmenu.apply_richmenu(richmenu_ids['MAINTENANCE'], user)
        else:
            richmenu.apply_richmenu(richmenu_ids['START'], user_id)


# ユーザからメッセージを受信したときのハンドラ
@handler.add(MessageEvent) #, message=TextMessageContent)
def handle_message(event):
    if get_maintenance_mode():
        logger.debug(f"[Maintenance Mode] user: {event.source.user_id} tried to send a message during maintenance mode.")
        msg = '現在、メンテナンス中のため、メッセージを受け付けていません。\n\nしばらく時間をおいてから再度お試しください。'
        reply_to_line_user(event, msg)
        return
    
    user_id = event.source.user_id
    session = get_session(user_id)
    flag = get_flag(user_id)

    logger.debug(f'[Message Session] user: {user_id}\n{format_structure(session, indent=1)}\n  flag: {flag}\n  time: {get_time(user_id)}')

    # 同意が必要かつ，同意文を送信し（flagが'consent'），まだ同意を得ていない場合
    if NEED_START_KEYWORD and flag=='consent' and session["keyword_accepted"] == False:
        if event.message.text == YES:
            session["keyword_accepted"] = True
            save_session(user_id, session)
            logger.debug(f'[Save Session] user: {user_id}\n  keyword_accepted: {session["keyword_accepted"]}')

            msg = 'ご同意ありがとうございます。メニューからご希望の時間を選択してください。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)
            richmenu.apply_richmenu(richmenu_ids['START'], user_id)  # 同意後のリッチメニューを適用

        else:
            session["keyword_accepted"] = False
            save_session(user_id, session)
            logger.debug(f'[Save Session] user: {user_id}\n  keyword_accepted: {session["keyword_accepted"]}')

            msg = 'ご同意いただけない場合は、カウンセリング対話を開始できません。\n\n同意はいつでも下のメニューから行えます。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)
    
    elif NEED_START_KEYWORD and session['keyword_accepted'] == False:
        msg = '下のメニューから同意を行うことで、カウンセリング対話を開始できます。'
        logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
        reply_to_line_user(event, msg)
    
    elif flag == 'start_chat':
        if event.message.text == YES:
            # session_time(秒)後にセッション終了用の処理を実行するTimerを起動
            session_time = get_time(user_id)
            timer = TrackableTimer(session_time, send_end_message, args=[user_id])
            timer.start()
            with threading.Lock():
                timers[user_id] = timer  # タイマーを保存
            # reset_time(user_id)  # セッション時間を0でリセット　※プログラム実行中にどこかでエラーが起きると，ユーザのtimeが0のままになってしまうため，コメントアウト
            
            session['counseling_mode'] = True
            session['session_id'] = generate_session_id(n=10)  # セッションIDを生成
            save_session(user_id, session)
            logger.debug(f'[Save Session] user: {user_id}\n  counseling_mode: {session["counseling_mode"]}\n  sessionID: {session["session_id"]}')

            richmenu.apply_richmenu(richmenu_ids['COUNSELING'], user_id)  # カウンセリングセッションのリッチメニューを適用

            if session['finished'] == True:
                logger.debug(f'[Send Message] user: {user_id}\n  カウンセリング対話の開始メッセージを送信')
                start_chat(event)  # カウンセリング対話を開始
                session['finished'] = False
                save_session(user_id, session)
                logger.debug(f'[Save Session] user: {user_id}\n  finished: {session["finished"]}')
            else:
                msg = 'カウンセリング対話を再開します。\n\n新しく会話を始める場合は、メニューから“Reset”ボタンを押してください。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)

            logger.info(f'[Counseling Start] user: {user_id}, session_time: {session_time} seconds')
            
        else:
            msg = 'カウンセリング対話を開始したい場合、もう一度メニューから“Start Chat”を選択して下さい。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)

    elif flag == 'reset_history':
        if event.message.text == YES:
            # 対話履歴をリセット
            bot = CounselorBot(LINEBOT_DB, 
                INIT_MESSAGE, 
                api_key=os.environ['OPENAI_API_KEY'], 
                model_name=OPENAI_MODEL,
                system_prompt_path="prompt/system_prompt.txt", 
                example_files=["prompt/case1_0.txt", "prompt/case2_0.txt", "prompt/case3_0.txt", "prompt/case4_0.txt", "prompt/case5_0.txt", "prompt/case6_1.txt"]
                )
            bot.finish_dialogue(user_id)
            session['finished'] = True  # セッションを終了状態にする
            if session['counseling_mode'] == True:
                logger.debug(f'[Send Message] user: {user_id}\n  対話履歴をリセットし，カウンセリング対話を開始')
                start_chat(event, reset=True)
            else:
                session['finished'] = True  # セッションを終了状態にする
                save_session(user_id, session)
                logger.debug(f'[Save Session] user: {user_id}\n  finished: {session["finished"]}')

                msg = '対話履歴をリセットしました。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)
        else:
            msg = '対話履歴のリセットをキャンセルしました。'
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            reply_to_line_user(event, msg)
    
    # 同意を得て，かつカウンセリングモードでない場合
    elif session['keyword_accepted'] == True and session['counseling_mode'] == False and not session['survey_mode'] == True:
        msg = 'カウンセリング対話を開始するには、メニューからご希望の時間を選択してください。'
        logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
        reply_to_line_user(event, msg)

    elif session['counseling_mode'] == True:
        if flag == 'end_chat':
            # カウンセリング対話を終了する
            if event.message.text == YES:
                session['counseling_mode'] = False
                session['survey_mode'] = True  # アンケートモードに切り替え
                save_session(user_id, session)  # セッションを保存
                logger.debug(f'[Save Session] user: {user_id}\n  counseling_mode: {session["counseling_mode"]}\n  survey_mode: {session["survey_mode"]}')

                # タイマーをキャンセル
                with threading.Lock():
                    remaining_time = timers[user_id].cancel()  # タイマーをキャンセル
                    del timers[user_id]  # タイマーを削除
                set_time(user_id, remaining_time)  # セッション時間を更新
                logger.info(f'[Counseling End] user: {user_id}, remaining_time: {remaining_time} seconds')

                # アンケートのリッチメニューを適用
                richmenu.apply_richmenu(richmenu_ids['SURVEY'], user_id)

                # アンケートの開始メッセージを送信
                logger.debug(f'[Send Message] user: {user_id}\n  カウンセリング対話を終了し，アンケートの開始確認メッセージを送信')
                survey(event, tunnel)  # アンケートを開始
                return # flagリセットを回避
            
            # カウンセリング対話を終了しない
            else:
                msg = '対話を続けます。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)
        
        else:
            logger.debug(f'[Send Message] user: {user_id}\n  カウンセリング対話のメッセージを送信')
            reply(event, tunnel)
            return # 対話が終了した場合の，flagリセットを回避

    elif session['survey_mode'] == True:
        # アンケートに協力するかどうかを確認するメッセージに対して
        if flag == 'start_survey':
            if event.message.text == YES:
                session['survey_progress'] = 1
                session['survey_mode'] = True
                save_session(user_id, session)  # セッションを保存
                logger.debug(f'[Save Session] user: {user_id}\n  survey_progress: {session["survey_progress"]}\n  survey_mode: {session["survey_mode"]}')
                logger.debug(f'[Send Message] user: {user_id}\n  アンケートを送信')
                survey(event, tunnel)  # アンケートを開始
            else:
                session['survey_mode'] = False
                session['survey_progress'] = 0
                save_session(user_id, session)  # セッションを保存
                logger.debug(f'[Save Session] user: {user_id}\n  survey_mode: {session["survey_mode"]}\n  survey_progress: {session["survey_progress"]}')

                richmenu.apply_richmenu(richmenu_ids['START'], user_id)  # リッチメニューを適用
                msg = 'ご利用ありがとうございました。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)

        # アンケートを終了するかどうかを確認するメッセージに対して
        elif flag == 'end_survey':
            if event.message.text == NO:
                logger.debug(f'[Send Message] user: {user_id}\n  アンケートを継続し，アンケートを再度送信')
                survey(event, tunnel)  # アンケートを継続
            else:
                session['survey_progress'] = 0  # ここで，初期化しない場合，次回アンケート開始時に前回のアンケートの続きから始まる
                session['survey_mode'] = False  # アンケートモードを終了
                save_session(user_id, session)  # セッションを保存
                logger.debug(f'[Save Session] user: {user_id}\n  survey_progress: {session["survey_progress"]}\n  survey_mode: {session["survey_mode"]}')

                # アンケート結果をファイルに書き込む
                save_survey_results(user_id)

                init_survey(user_id)  # アンケートを初期化
                richmenu.apply_richmenu(richmenu_ids['START'], user_id)  # リッチメニューを適用
                msg = 'ご利用ありがとうございました。'
                logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
                reply_to_line_user(event, msg)

        else:
            logger.debug(f'[Send Message] user: {user_id}\n  アンケートの送信')
            survey(event, tunnel) # survey_progress==0のときのみ，flagにstart_surveyを設定
            return # flagリセットを回避
    
    else:
        logger.error(f"[Unexpected Session]")
    
    # フラグをリセット        
    reset_flag(user_id)



@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except stripe.error.SignatureVerificationError:
        return "Webhook signature verification failed", 400
    except stripe.error.StripeError:
        return "Stripe error", 400

    # 支払い成功イベントを処理
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        payment_intent_id = session.get("payment_intent")
        if payment_intent_id:
            # PaymentIntent を取得
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            # print(f"Payment Intent Metadata: {payment_intent.metadata}")
        else:
            pass
            # print("Payment intent ID not found in session.")

        user_id = payment_intent.metadata.get("user_id")
        purchased_time = payment_intent.metadata.get("time") 
        increment_time(user_id, purchased_time)  # 購入時間分のカウンセリング時間を増やす
        
        # pushメッセージは送信制限があるため，try-exceptで囲む
        try:
            msg = "ご購入ありがとうございました！\nメニューから“Start Chat”を押すとカウンセリング対話を開始できます。"
            logger.debug(f'[Send Message] user: {user_id}\n  {repr(msg)}')
            push_to_line_user(user_id, msg)
        except Exception as e:
            logger.error(f"[Send Message Error] Failed to send message to user {user_id}: {e}")

        logger.info(f'[Checkout] user: {user_id} additinal_time: {purchased_time}, total_time: {get_time(user_id)}')

    return jsonify(success=True)


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


@app.route('/cancel')
def cancel():
    return "支払いがキャンセルされました。"


if __name__ == "__main__":
    port = int(os.getenv("PORT", PORT))
    server = WSGIServer(("0.0.0.0", PORT), app)

    # SSL証明書の設定（ローカルで動かす場合はコメントアウト）
    if conf['NGROK'] == False:
        server.ssl_adapter = BuiltinSSLAdapter('/cert/server.crt', '/cert/server.key')
    
    # 初期化
    reset_all_flags()
    reset_all_sessions()  # セッションをリセット
    set_maintenance_mode(False)  # メンテナンスモードをオフにする
    logger.info("[All Flag Reset]")
    logger.info("[All Session Reset]")

    # 全ユーザのリッチメニューを初期化
    all_users = get_all_users()    # データベースから全ユーザを取得
    logger.info(f'[All Richmenu Initialized] {len(all_users)} users')
    for user in all_users:
        session = get_session(user)
        if session['keyword_accepted'] == False:
            richmenu.apply_richmenu(richmenu_ids['CONSENT'], user)
        else:
            richmenu.apply_richmenu(richmenu_ids['START'], user)

    # 監視開始
    observer = Observer()
    file_handler = FileChangeHandler(filepath=main_config_path)
    observer.schedule(file_handler, path='./config', recursive=False)
    observer.start()
            
    try:
        server.start()

    except KeyboardInterrupt:
        if get_maintenance_mode() == False:
            maintenace_mode_on()
        observer.stop()
        observer.join()
        server.stop()
        logger.info("[Server Shutdown]")