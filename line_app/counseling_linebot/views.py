import json
import os
import sys
import threading
from pathlib import Path

import stripe
from ruamel.yaml import YAML
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, FollowEvent, PostbackEvent, StickerMessageContent, TextMessageContent

# 既存実装の再利用（Flask版と同等機能）
ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT_DIR / "counseling_linebot"
sys.path.insert(0, str(LEGACY_DIR))

from logger.set_logger import start_logger
from logger.ansi import * 
from counseling_linebot.models import ChatHistory
from counseling_linebot.utils import richmenu 
from counseling_linebot.utils.bot import CounselorBot
from counseling_linebot.utils.async_llm import risk_level_detection_async
from counseling_linebot.utils.maintenance import FileChangeHandler, maintenance_mode_on 
from counseling_linebot.utils.db_handler import (
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
	save_survey_results,
	check_and_reset_session,
 	save_dialogue_history,
	add_reply_token,
	reset_risk_level,
)
from counseling_linebot.utils.tool import (
	TrackableTimer,
	format_structure,
	extract_event_info,
	load_config,
	create_checkout_session,
	create_directory,
	generate_session_id,
)
from counseling_linebot.utils.main_message import (
	shop,
	reply,
	start_chat,
	send_end_message,
	survey,
	timers,
)
from counseling_linebot.utils.template_message import (
	reply_to_line_user,
	push_to_line_user,
	send_yes_no_buttons,
)

# ディレクトリが存在しない場合は作成
create_directory()

# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
logger = start_logger(conf["LOGGER"]["SYSTEM"])

# ChatGPTのキー
os.environ["OPENAI_API_KEY"] = conf["OPENAI_API_KEY"]
os.environ["ANTHROPIC_API_KEY"] = conf["ANTHROPIC_API_KEY"]

# Telegramのキー CounselorAITest
TELEGRAM_KEY = conf["TELEGRAM_KEY"]

# モデルを指定
OPENAI_MODEL = conf["OPENAI_MODEL"]
TEMPERATURE = conf["TEMPERATURE"]
MAX_TOKENS = conf["MAX_TOKENS"]

KEYWORD_MESSAGE = conf["KEYWORD_MESSAGE"]
INIT_MESSAGE = conf["INIT_MESSAGE"]

# 対話開始キーワードが必要かどうか
NEED_START_KEYWORD = conf["NEED_START_KEYWORD"]

# 2択の質問
YES = "1:" + conf["YES_ANSWER"]
NO = "2:" + conf["NO_ANSWER"]

SESSIONS_DB = conf["SESSIONS_DB"]
LINEBOT_DB = conf["LINEBOT_DB"]

LINE_CHANNEL_SECRET = conf["LINE_CHANNEL_SECRET"]
LINE_ACCESS_TOKEN = conf["LINE_ACCESS_TOKEN"]

stripe.api_key = conf["STRIPE_SECRET"]
endpoint_secret = conf["STRIPE_WEBHOOK"]

# PORT番ポートのHTTPトンネルを開設する
PORT = conf["PORT"]

# ngrokを使うかどうか（管理コマンド実行時は接続しない）
if conf["NGROK"] and "runserver" in sys.argv:
	from pyngrok import ngrok  # noqa: E402

	tunnel = ngrok.connect(PORT, "http").public_url
else:
	tunnel = conf["SERVER_URL"] + f":{PORT}"
logger.info(f"{BG}[Public URL]{R} {tunnel}")


# リッチメニューIDを取得（なければ生成）
if os.path.exists(conf["RICHMENU_PATH"]):
	richmenu_ids = load_config(conf["RICHMENU_PATH"])
else:
	richmenu_ids = None
richmenu_ids = richmenu.create_richmenus(richmenu_ids)
yaml = YAML()
yaml.preserve_quotes = True  # コメントを保持
with open(conf["RICHMENU_PATH"], "w", encoding="utf-8") as f:  # 書き戻し（コメント・順序を保持したまま）
	yaml.dump(richmenu_ids, f)


# mil-ai
handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_ACCESS_TOKEN)


# LINE Messaging APIのコールバックエンドポイント（ユーザからデータを受信したら最初にこの関数が呼ばれる）
@csrf_exempt
def callback(request):
	if request.method != "POST":
		return HttpResponse(status=405)

	try:
		payload = json.loads(request.body.decode("utf-8")) if request.body else {}
	except json.JSONDecodeError:
		payload = {}
	logger.debug(f"\n[Recieved Request] {extract_event_info(payload)}")

	signature = request.headers.get("X-Line-Signature", "")
	body = request.body.decode("utf-8")

	try:
		handler.handle(body, signature)
	except InvalidSignatureError:
		logger.debug("Invalid signature. Please check your channel access token/channel secret.")
		return HttpResponse(status=400)

	return HttpResponse("OK")


# --- Followイベントハンドラ（友達追加時） ---
@handler.add(FollowEvent)
def handle_follow(event):
	logger.info(f"[Follow Event] user: {event.source.user_id}")

	# ユーザのユーザIDを取得
	user_id = event.source.user_id
	session = get_session(user_id, tabs=1)

	# 初めて友達登録したユーザの場合、セッションとフラグを初期化
	if session is None or session["keyword_accepted"] == False:
		if session is None:
			logger.info(f"\t[New User] user: {user_id} (session not found)")
		elif session["keyword_accepted"] == False:
			logger.info(f"\t[Refollow] user: {user_id} (keyword not accepted)")
		register_user(user_id)  # ユーザをデータベースに登録

		# メンテナンス中の場合
		if get_maintenance_mode(tabs=1):
			logger.info(
				f"\t[Maintenance Mode] user: {event.source.user_id} tried to follow during maintenance mode."
			)
			msg = (
				"友達登録ありがとうございます。\n\n現在、メンテナンス中のため、操作を受け付けていません。"
				"\n\nしばらく時間をおいてから再度お試しください。"
			)
			reply_to_line_user(event.reply_token, msg)
			richmenu.apply_richmenu(
				richmenu_ids["MAINTENANCE"], user_id
			)  # メンテナンス用のリッチメニューを適用
			return

		richmenu.apply_richmenu(richmenu_ids["CONSENT"], user_id, tabs=1)  # リッチメニューを作成・適用

		# 同意を求めるメッセージを送信
		logger.debug(f"\t[Send Message] user: {user_id}\n\t  同意を求めるメッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="同意しますか？",
			alt_text="同意の確認",
			prepend_message="友達登録ありがとうございます！\n\n" + KEYWORD_MESSAGE,
			split=False,  # 同意メッセージは分割しない
		)
		save_flag(user_id, flag="consent")  # フラグを保存
		logger.debug(f"\t[Save Flag] flag: consent, user: {user_id}")

	else:
		logger.info(f"\t[Refollow] user: {user_id}")
		richmenu.apply_richmenu(richmenu_ids["START"], user_id, tabs=1)  # リッチメニューを作成・適用

		msg = "友達登録ありがとうございます！\n\n対話を開始するには、下のメニューを開き、操作を行ってください。"
		logger.debug(f"\t[Send Message] user: {user_id}\n\t  {repr(msg)}")
		reply_to_line_user(event.reply_token, msg)

	init_survey(user_id)  # アンケートを初期化


# ユーザがリッチメニューのボタンを押したときのハンドラ
@handler.add(PostbackEvent)
def handle_postback(event):
	user_id = event.source.user_id
	logger.debug(f"[Postback Event] user: {user_id}, data: {event.postback.data}")
 
	if get_maintenance_mode(tabs=1):
		logger.debug(
			f"\t[Maintenance Mode] user: {event.source.user_id} tried to postback during maintenance mode."
		)
		msg = "現在、メンテナンス中のため、操作を受け付けていません。\n\nしばらく時間をおいてから再度お試しください。"
		reply_to_line_user(event.reply_token, msg)
		if event.postback.data != "maintenance":
			richmenu.apply_richmenu(
				richmenu_ids["MAINTENANCE"], user_id, tabs=1
			)  # メンテナンス用のリッチメニューを適用
		return

	session = get_session(user_id, tabs=1)
	logger.debug(
		f"\t[Postback Session] user: {user_id}\n{format_structure(session, indent=2)}\n\t\tflag: {get_flag(user_id)}\n\t\ttime: {get_time(user_id)}"
	)

	# 送信されたデータをチェック
	check_flag = richmenu.check_richmenu(
		session, event.postback.data, user_id, richmenu_ids, tabs=1
	)  # リッチメニューのチェックと適用
	if check_flag == False:
		return  # リッチメニューの再適用を行い，終了

	if event.postback.data == "consent":
		logger.debug(f"[Send Message] user: {user_id}\n  同意を求めるメッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="同意しますか？",
			alt_text="同意の確認",
			prepend_message=KEYWORD_MESSAGE,
			split=False,  # 同意メッセージは分割しない
		)

		logger.debug(f"[Save Flag] flag: consent, user: {user_id}")
		save_flag(user_id, flag="consent")  # フラグを保存

	elif event.postback.data == "no_consent":
		msg = "ご同意いただけない場合は、カウンセリング対話を開始できません。"
		logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
		reply_to_line_user(event.reply_token, msg)

	elif event.postback.data == "shop":
		shop(event, tunnel)

	elif event.postback.data == "reset_history":
		logger.debug(f"\t[Send Message] user: {user_id}\n\t\t対話履歴のリセットの確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="本当に対話履歴をリセットしますか？\n\nリセットすると、これまでの対話履歴がすべて消去されます。",
			alt_text="対話履歴のリセットの確認",
		)

		save_flag(user_id, flag="reset_history")  # フラグを保存
		logger.debug(f"\t[Save Flag] flag: reset_history, user: {user_id}")
	elif event.postback.data == "start_chat":
		if NEED_START_KEYWORD and session["keyword_accepted"] == False:
			msg = "カウンセリング対話を開始する前に、同意が必要です。\n\n下のメニューから同意を行ってください。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)

		elif session["counseling_mode"] == True:
			msg = "すでにカウンセリング対話が開始されています。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)
			richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id, tabs=1)

		else:
			session_time = get_time(user_id)
			if session_time == 0:
				msg = "メニューからご希望の時間を選択してください。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)

			else:
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\tカウンセリング対話の開始確認メッセージを送信")
				minutes = int(session_time // 60)
				seconds = int(session_time % 60)
				send_yes_no_buttons(
					configuration,
					reply_token=event.reply_token,
					question_text=f"現在のカウンセリング時間は{minutes}分{seconds:02d}秒です。カウンセリング対話を開始しますか？",
					alt_text="カウンセリング対話の開始確認",
				)
				save_flag(user_id, flag="start_chat")  # フラグを保存
				logger.debug(f"\t[Save Flag] flag: start_chat, user: {user_id}")
	elif event.postback.data == "end_chat":
		if check_and_reset_session(user_id, richmenu_ids, tabs=1):
			return

		logger.debug(f"\t[Send Message] user: {user_id}\n\t\tカウンセリング対話の終了確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="本当にカウンセリング対話を終了しますか？\n\n終了しても、残った時間は保持されます。",
			alt_text="カウンセリング対話の終了確認",
		)

		save_flag(user_id, flag="end_chat")  # フラグを保存
		logger.debug(f"\t[Save Flag] flag: end_chat, user: {user_id}")
	elif event.postback.data == "check_time":
		if check_and_reset_session(user_id, richmenu_ids, tabs=1):
			return
		logger.debug(f"\t[Checking Remaining Time] user {user_id}")
		try:
			with threading.Lock():
				remaining_time = timers[user_id].remaining_time()
				remaining_time = remaining_time // 60
				if remaining_time > 60:
					time_richmenu_id = richmenu_ids["REMAINING_TIME"]["60over"]
				else:
					time_richmenu_id = richmenu_ids["REMAINING_TIME"][remaining_time]
				richmenu.apply_richmenu(time_richmenu_id, user_id, tabs=1)
		except KeyError:
			logger.warning(f"\t[Warning] ユーザ'{user_id}'のタイマーが見つかりませんでした。")
			richmenu.apply_richmenu(richmenu_ids["START"], user_id, tabs=2)
			if session["counseling_mode"] == True:
				logger.warning(f"\t[Warning] ユーザ'{user_id}'はカウンセリングモードですが、タイマーが見つかりませんでした。セッションをリセットします。")
				session["counseling_mode"] = False
				save_session(user_id, session)

	elif event.postback.data == "back_to_menu":
		if check_and_reset_session(user_id, richmenu_ids, tabs=1):
			return
		logger.debug(f"\t[Back to Menu] user {user_id}")
		richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id, tabs=1)

	elif event.postback.data == "update_time":
		if check_and_reset_session(user_id, richmenu_ids, tabs=1):
			return
		logger.debug(f"\t[Update Remaining Time] user {user_id}")
		try:
			with threading.Lock():
				remaining_time = timers[user_id].remaining_time()
				remaining_time = remaining_time // 60
		except KeyError:
			logger.warning(f"\t[Warning] ユーザ'{user_id}'のタイマーが見つかりませんでした。")
			richmenu.apply_richmenu(richmenu_ids["START"], user_id, tabs=2)
			if session["counseling_mode"] == True:
				logger.warning(f"\t[Warning] ユーザ'{user_id}'はカウンセリングモードですが、タイマーが見つかりませんでした。セッションをリセットします。")
				session["counseling_mode"] = False
				save_session(user_id, session)
				return
		richmenu.apply_richmenu(richmenu_ids["REMAINING_TIME"][remaining_time], user_id, tabs=1)

	elif event.postback.data == "end_survey":
		if check_and_reset_session(user_id, richmenu_ids, tabs=1):
			return
		logger.debug(f"\t[Send Message] user: {user_id}\n\t\tアンケートの終了確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="アンケートを終了しますか？",
			alt_text="アンケートの終了確認",
		)

		save_flag(user_id, flag="end_survey")
		logger.debug(f"\t[Save Flag] flag: end_survey, user: {user_id}")
	elif event.postback.data == "maintenance":
		logger.warning(
			f"\t[WARNING] user: {user_id}  メンテナンス状態でないのに，メンテナンスメニューが適用されています。\n  再度リッチメニューを更新します。"
		)
		if session["keyword_accepted"] == False:
			richmenu.apply_richmenu(richmenu_ids["MAINTENANCE"], user_id, tabs=1)
		else:
			richmenu.apply_richmenu(richmenu_ids["START"], user_id, tabs=1)


# ユーザからメッセージを受信したときのハンドラ
@handler.add(MessageEvent)
def handle_message(event):
	logger.debug(f"[Message Event] user: {event.source.user_id}, message: {event.message.text}")
	
	if get_maintenance_mode(tabs=1):
		logger.debug(
			f"\t[Maintenance Mode] user: {event.source.user_id} tried to send a message during maintenance mode."
		)
		msg = "現在、メンテナンス中のため、メッセージを受け付けていません。\n\nしばらく時間をおいてから再度お試しください。"
		reply_to_line_user(event.reply_token, msg)
		return

	user_id = event.source.user_id
	session = get_session(user_id, tabs=1)
	flag = get_flag(user_id)

	logger.debug(
		f"\t[Message Session] user: {user_id}\n{format_structure(session, indent=2)}\n\t\tflag: {flag}\n\t\ttime: {get_time(user_id)}"
	)

	if NEED_START_KEYWORD and flag == "consent" and session["keyword_accepted"] == False:
		if event.message.text == YES:
			session["keyword_accepted"] = True
			save_session(user_id, session)
			logger.debug(f"\t[Save Session] user: {user_id}\n\t\tkeyword_accepted: {session['keyword_accepted']}")

			msg = "ご同意ありがとうございます。メニューのShopからご希望の時間を選択してください。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)
			richmenu.apply_richmenu(richmenu_ids["START"], user_id, tabs=1)

		else:
			session["keyword_accepted"] = False
			save_session(user_id, session)
			logger.debug(f"\t[Save Session] user: {user_id}\n\t\tkeyword_accepted: {session['keyword_accepted']}")

			msg = "ご同意いただけない場合は、カウンセリング対話を開始できません。\n\n同意はいつでも下のメニューから行えます。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)

	elif NEED_START_KEYWORD and session["keyword_accepted"] == False:
		msg = "下のメニューから同意を行うことで、カウンセリング対話を開始できます。"
		logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
		reply_to_line_user(event.reply_token, msg)

	elif flag == "start_chat":
		if event.message.text == YES:
			session_time = get_time(user_id)
			timer = TrackableTimer(session_time, send_end_message, args=[user_id])
			timer.start()
			with threading.Lock():
				timers[user_id] = timer
				logger.info(f"\t[Start Timer] user: {user_id}, time: {session_time} seconds")

			session["counseling_mode"] = True
			# session["session_id"] = generate_session_id(n=10)
			save_session(user_id, session)
			logger.debug(
				f"\t[Save Session] user: {user_id}\n\t\tcounseling_mode: {session['counseling_mode']}\n\t\tsessionID: {session['session_id']}"
			)

			richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id, tabs=1)

			reset_risk_level(user_id, tabs=1)
			if session["finished"] == True:
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\tカウンセリング対話の開始メッセージを送信")
				start_chat(event)
				session["finished"] = False
				save_session(user_id, session)
				logger.debug(f"\t[Save Session] user: {user_id}\n\t\tfinished: {session['finished']}")
			else:
				msg = "カウンセリング対話を再開します。\n\n新しく会話を始める場合は、メニューから“Reset”ボタンを押してください。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)

			logger.info(f"\t[Counseling Start] user: {user_id}, session_time: {session_time} seconds")

		else:
			msg = "カウンセリング対話を開始したい場合、もう一度メニューから“Start Chat”を選択して下さい。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)

	elif flag == "reset_history":
		if event.message.text == YES:
			bot = CounselorBot(
				LINEBOT_DB,
				INIT_MESSAGE,
				api_key=os.environ["OPENAI_API_KEY"],
				model_name=OPENAI_MODEL,
				system_prompt_path="./counseling_linebot/prompts/system_prompt.txt",
				example_files=[
					"./counseling_linebot/prompts/case1_0.txt",
					"./counseling_linebot/prompts/case2_0.txt",
					"./counseling_linebot/prompts/case3_0.txt",
					"./counseling_linebot/prompts/case4_0.txt",
					"./counseling_linebot/prompts/case5_0.txt",
					"./counseling_linebot/prompts/case6_1.txt",
				],
			)
			bot.finish_dialogue(user_id)
			reset_risk_level(user_id, tabs=1)
			session["session_id"] = generate_session_id(n=10)
			if session["counseling_mode"] == True:
				save_session(user_id, session)
				logger.debug(f"\t[Save Session] user: {user_id}\n\t\tfinished: {session['finished']}\n\t\tsession_id: {session['session_id']}")
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t対話履歴をリセットし，カウンセリング対話を開始")
				start_chat(event, reset=True)
			else:
				session["finished"] = True
				save_session(user_id, session)
				logger.debug(f"\t[Save Session] user: {user_id}\n\t\tfinished: {session['finished']}\n\t\tsession_id: {session['session_id']}")
				msg = "対話履歴をリセットしました。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)
		else:
			msg = "対話履歴のリセットをキャンセルしました。"
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
			reply_to_line_user(event.reply_token, msg)

	elif session["keyword_accepted"] == True and session["counseling_mode"] == False and not session["survey_mode"] == True:
		msg = "カウンセリング対話を開始するには、メニューからご希望の時間を選択してください。"
		logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
		reply_to_line_user(event.reply_token, msg)

	elif session["counseling_mode"] == True:
		if flag == "end_chat":
			if event.message.text == YES:
				session["counseling_mode"] = False
				session["survey_mode"] = True
				save_session(user_id, session)
				logger.debug(
					f"\t[Save Session] user: {user_id}\n\t\tcounseling_mode: {session['counseling_mode']}\n\t\tsurvey_mode: {session['survey_mode']}"
				)

				try:
					with threading.Lock():
						remaining_time = timers[user_id].cancel()
						del timers[user_id]
				except KeyError:
					logger.warning(f"\t[Warning] ユーザ'{user_id}'のタイマーが見つかりませんでした。")
					if session["counseling_mode"] == True:
						logger.warning(f"\t[Warning] ユーザ'{user_id}'はカウンセリングモードですが、タイマーが見つかりませんでした。セッションをリセットします。")
						session["counseling_mode"] = False
						save_session(user_id, session)
					return
				set_time(user_id, remaining_time)
				logger.info(f"[Counseling End] user: {user_id}, remaining_time: {remaining_time} seconds")

				richmenu.apply_richmenu(richmenu_ids["SURVEY"], user_id)

				logger.debug(f"[Send Message] user: {user_id}\n\t\tカウンセリング対話を終了し，アンケートの開始確認メッセージを送信")
				survey(event, tunnel)
				return

			else:
				msg = "対話を続けます。"
				logger.debug(f"[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)

		else:
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\tカウンセリング対話のメッセージを送信")
			mode = session['response_mode']
			logger.info(f"\t[Mode] {mode}, type:{type(event.reply_token)}")
			add_reply_token(user_id, event.reply_token, tabs=1)
   
			if isinstance(event.message, StickerMessageContent):
				msg = f"スタンプ（意図）: {event.message.keywords}"
			elif isinstance(event.message, TextMessageContent):
				msg = event.message.text
			else:
				logger.warning(f"\t[Warning] 非対応のメッセージタイプ: {type(event.message)}")
				return
   
			# 非同期でリスクレベルの検出を行うスレッドを起動
			logger.info(f"\t[Risk Detection] 非同期でリスクレベルの検出を行うスレッドを起動")
			risk_thread = threading.Thread(
				target=risk_level_detection_async,
				args=(user_id, session.get("session_id", ""), msg),
				daemon=True,
			)
			risk_thread.start()
   
			if session['response_mode'] == 'Human':
				
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t人間が対応中のため、メッセージを送信せずに終了")
				post_time = timezone.now()
				logger.debug(f"\t[Save Dialogue History] message: {msg}")
				ChatHistory.objects.create(
					user_id=user_id,
					speaker="user",
					message=msg,
					post_time=post_time,
					finished=0,
					session_id=session["session_id"],
				)
				save_dialogue_history(user_id, 'user', msg, session["session_id"], post_time)
				return

			else:     # response_mode == 'AI'
				reply(event, tunnel)

	elif session["survey_mode"] == True:
		if flag == "start_survey":
			if event.message.text == YES:
				session["survey_progress"] = 1
				session["survey_mode"] = True
				save_session(user_id, session)
				logger.debug(
					f"\t[Save Session] user: {user_id}\n\t\tsurvey_progress: {session['survey_progress']}\n\t\tsurvey_mode: {session['survey_mode']}"
				)
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\tアンケートを送信")
				survey(event, tunnel)
			else:
				session["survey_mode"] = False
				session["survey_progress"] = 0
				save_session(user_id, session)
				logger.debug(
					f"\t[Save Session] user: {user_id}\n\t\tsurvey_mode: {session['survey_mode']}\n\t\tsurvey_progress: {session['survey_progress']}"
				)

				richmenu.apply_richmenu(richmenu_ids["START"], user_id)
				msg = "ご利用ありがとうございました。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)

		elif flag == "end_survey":
			if event.message.text == NO:
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\tアンケートを継続し，アンケートを再度送信")
				survey(event, tunnel)
			else:
				session["survey_progress"] = 0
				session["survey_mode"] = False
				save_session(user_id, session)
				logger.debug(
					f"\t[Save Session] user: {user_id}\n\t\tsurvey_progress: {session['survey_progress']}\n\t\tsurvey_mode: {session['survey_mode']}"
				)

				save_survey_results(user_id)

				init_survey(user_id)
				richmenu.apply_richmenu(richmenu_ids["START"], user_id)
				msg = "ご利用ありがとうございました。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				reply_to_line_user(event.reply_token, msg)

		else:
			logger.debug(f"\t[Send Message] user: {user_id}\n\t\tアンケートの送信")
			survey(event, tunnel)
			return

	else:
		logger.error("[Unexpected Session]")

	reset_flag(user_id)


@csrf_exempt
def stripe_webhook(request):
	if request.method != "POST":
		return HttpResponse(status=405)

	payload = request.body.decode("utf-8")
	sig_header = request.headers.get("Stripe-Signature")
	logger.ddebug("[Checkout]")

	try:
		event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
		logger.debug(f"[Webhook Event] {event['type']}\n{format_structure(event, indent=1)}")
	except stripe.error.SignatureVerificationError:
		logger.error("[Webhook Error] Webhook signature verification failed.\n\tmain.yamlのSTRIPE_WEBHOOKを確認してください。")
		return HttpResponse("Webhook signature verification failed", status=400)
	except stripe.error.StripeError:
		logger.error("[Webhook Error] Stripe error occurred while processing webhook.")
		return HttpResponse("Stripe error", status=400)

	if event["type"] == "checkout.session.completed":
		session = event["data"]["object"]
		payment_intent_id = session.get("payment_intent")
		if payment_intent_id:
			payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
		else:
			payment_intent = None

		if payment_intent:
			user_id = payment_intent.metadata.get("user_id")
			purchased_time = payment_intent.metadata.get("time")
			increment_time(user_id, purchased_time)

			try:
				msg = "ご購入ありがとうございました！\nメニューから“Start Chat”を押すとカウンセリング対話を開始できます。"
				logger.debug(f"\t[Send Message] user: {user_id}\n\t\t{repr(msg)}")
				push_to_line_user(user_id, msg)
			except Exception as e:
				logger.error(f"\t[Send Message Error] Failed to send message to user {user_id}: {e}")

			logger.info(
				f"\t[Checkout] user: {user_id} additinal_time: {purchased_time}, total_time: {get_time(user_id)}"
			)

	return JsonResponse({"success": True})


def create_checkout_session1(request):
	line_id = request.GET.get("LINE_ID")

	try:
		session = create_checkout_session(
			product_name=conf["ITEM_1"]["NAME"],
			unit_amount=conf["ITEM_1"]["PRICE"],
			time_seconds=conf["ITEM_1"]["TIME"],
			line_id=line_id,
			tunnel_url=tunnel,
		)
		logger.debug(f"[Checkout Session Created] URL: {session.url}")
		return redirect(session.url, permanent=False)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)


def create_checkout_session2(request):
	line_id = request.GET.get("LINE_ID")

	try:
		session = create_checkout_session(
			product_name=conf["ITEM_2"]["NAME"],
			unit_amount=conf["ITEM_2"]["PRICE"],
			time_seconds=conf["ITEM_2"]["TIME"],
			line_id=line_id,
			tunnel_url=tunnel,
		)
		logger.debug(f"[Checkout Session Created] URL: {session.url}")
		return redirect(session.url, permanent=False)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)


def create_checkout_session3(request):
	line_id = request.GET.get("LINE_ID")

	try:
		session = create_checkout_session(
			product_name=conf["ITEM_3"]["NAME"],
			unit_amount=conf["ITEM_3"]["PRICE"],
			time_seconds=conf["ITEM_3"]["TIME"],
			line_id=line_id,
			tunnel_url=tunnel,
		)
		logger.debug(f"[Checkout Session Created] URL: {session.url}")
		return redirect(session.url, permanent=False)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)


def create_checkout_session4(request):
	line_id = request.GET.get("LINE_ID")

	try:
		session = create_checkout_session(
			product_name=conf["ITEM_4"]["NAME"],
			unit_amount=conf["ITEM_4"]["PRICE"],
			time_seconds=conf["ITEM_4"]["TIME"],
			line_id=line_id,
			tunnel_url=tunnel,
		)
		logger.debug(f"[Checkout Session Created] URL: {session.url}")
		return redirect(session.url, permanent=False)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)


def success(request):
	return render(request, "success.html")


def cancel(request):
	return HttpResponse("支払いがキャンセルされました。")
