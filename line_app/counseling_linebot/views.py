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
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, FollowEvent, PostbackEvent

# 既存実装の再利用（Flask版と同等機能）
ROOT_DIR = Path(__file__).resolve().parents[2]
LEGACY_DIR = ROOT_DIR / "counseling_linebot"
sys.path.insert(0, str(LEGACY_DIR))

from logger.set_logger import start_logger  # noqa: E402
from logger.ansi import *  # noqa: F403, E402
from utils.bot import CounselorBot  # noqa: E402
from utils import richmenu  # noqa: E402
from utils.maintenance import FileChangeHandler, maintenace_mode_on  # noqa: E402
from utils.db_handler import (  # noqa: E402
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
	save_survey_results,
)
from utils.tool import (  # noqa: E402
	TrackableTimer,
	format_structure,
	extract_event_info,
	load_config,
	create_checkout_session,
	create_directory,
	generate_session_id,
)
from utils.main_massage import (  # noqa: E402
	shop,
	reply,
	start_chat,
	send_end_message,
	survey,
	timers,
)
from utils.template_message import (  # noqa: E402
	reply_to_line_user,
	push_to_line_user,
	send_yes_no_buttons,
)

# ディレクトリが存在しない場合は作成
create_directory()

# ロガーと設定の読み込み
main_config_path = str(LEGACY_DIR / "config" / "main.yaml")
conf = load_config(main_config_path)
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

# ngrokを使うかどうか
if conf["NGROK"]:
	from pyngrok import ngrok  # noqa: E402

	tunnel = ngrok.connect(PORT, "http").public_url
else:
	tunnel = conf["SERVER_URL"] + f":{PORT}"
logger.info(f"{BG}[Public URL]{R} {tunnel}")


# データベースが存在しない場合は初期化
if not os.path.exists(SESSIONS_DB):
	init_db()
init_settings_table()  # メンテナンスモード用の設定テーブルを初期化


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
	logger.debug(f"[Follow Event] user: {event.source.user_id}")

	# ユーザのユーザIDを取得
	user_id = event.source.user_id
	session = get_session(user_id)

	# 初めて友達登録したユーザの場合、セッションとフラグを初期化
	if session is None or session["keyword_accepted"] == False:
		if session is None:
			logger.info(f"[New User] user: {user_id} (session not found)")
		elif session["keyword_accepted"] == False:
			logger.info(f"[Refollow] user: {user_id} (keyword not accepted)")
		register_user(user_id)  # ユーザをデータベースに登録

		# メンテナンス中の場合
		if get_maintenance_mode():
			logger.debug(
				f"[Maintenance Mode] user: {event.source.user_id} tried to follow during maintenance mode."
			)
			msg = (
				"友達登録ありがとうございます。\n\n現在、メンテナンス中のため、操作を受け付けていません。"
				"\n\nしばらく時間をおいてから再度お試しください。"
			)
			reply_to_line_user(event, msg)
			richmenu.apply_richmenu(
				richmenu_ids["MAINTENANCE"], user_id
			)  # メンテナンス用のリッチメニューを適用
			return

		richmenu.apply_richmenu(richmenu_ids["CONSENT"], user_id)  # リッチメニューを作成・適用

		# 同意を求めるメッセージを送信
		logger.debug(f"[Send Message] user: {user_id}\n  同意を求めるメッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="同意しますか？",
			alt_text="同意の確認",
			prepend_message="友達登録ありがとうございます！\n\n" + KEYWORD_MESSAGE,
			split=False,  # 同意メッセージは分割しない
		)
		save_flag(user_id, flag="consent")  # フラグを保存
		logger.debug(f"[Save Flag] flag: consent, user: {user_id}")

	else:
		logger.info(f"[Refollow] user: {user_id}")
		richmenu.apply_richmenu(richmenu_ids["START"], user_id)  # リッチメニューを作成・適用

		msg = "友達登録ありがとうございます！\n\n対話を開始するには、下のメニューを開き、操作を行ってください。"
		logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
		reply_to_line_user(event, msg)

	init_survey(user_id)  # アンケートを初期化


# ユーザがリッチメニューのボタンを押したときのハンドラ
@handler.add(PostbackEvent)
def handle_postback(event):
	user_id = event.source.user_id

	if get_maintenance_mode():
		logger.debug(
			f"[Maintenance Mode] user: {event.source.user_id} tried to postback during maintenance mode."
		)
		msg = "現在、メンテナンス中のため、操作を受け付けていません。\n\nしばらく時間をおいてから再度お試しください。"
		reply_to_line_user(event, msg)
		if event.postback.data != "maintenance":
			richmenu.apply_richmenu(
				richmenu_ids["MAINTENANCE"], user_id
			)  # メンテナンス用のリッチメニューを適用
		return

	session = get_session(user_id)
	logger.debug(
		f"[Postback Session] user: {user_id}\n{format_structure(session, indent=1)}\n  flag: {get_flag(user_id)}\n  time: {get_time(user_id)}"
	)

	# 送信されたデータをチェック
	check_flag = richmenu.check_richmenu(
		session, event.postback.data, user_id, richmenu_ids
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
		logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
		reply_to_line_user(event, msg)

	elif event.postback.data == "shop":
		shop(event, tunnel)

	elif event.postback.data == "reset_history":
		logger.debug(f"[Send Message] user: {user_id}\n  対話履歴のリセットの確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="本当に対話履歴をリセットしますか？\n\nリセットすると、これまでの対話履歴がすべて消去されます。",
			alt_text="対話履歴のリセットの確認",
		)

		save_flag(user_id, flag="reset_history")  # フラグを保存
		logger.debug(f"[Save Flag] flag: reset_history, user: {user_id}")

	elif event.postback.data == "start_chat":
		if NEED_START_KEYWORD and session["keyword_accepted"] == False:
			msg = "カウンセリング対話を開始する前に、同意が必要です。\n\n下のメニューから同意を行ってください。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)

		elif session["counseling_mode"] == True:
			msg = "すでにカウンセリング対話が開始されています。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)
			richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id)

		else:
			session_time = get_time(user_id)
			if session_time == 0:
				msg = "メニューからご希望の時間を選択してください。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)

			else:
				logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話の開始確認メッセージを送信")
				minutes = int(session_time // 60)
				seconds = int(session_time % 60)
				send_yes_no_buttons(
					configuration,
					reply_token=event.reply_token,
					question_text=f"現在のカウンセリング時間は{minutes}分{seconds:02d}秒です。カウンセリング対話を開始しますか？",
					alt_text="カウンセリング対話の開始確認",
				)
				save_flag(user_id, flag="start_chat")  # フラグを保存
				logger.debug(f"[Save Flag] flag: start_chat, user: {user_id}")

	elif event.postback.data == "end_chat":
		assert session["counseling_mode"] == True, "カウンセリングモードでないのにend_chatが呼ばれました"

		logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話の終了確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="本当にカウンセリング対話を終了しますか？\n\n終了しても、残った時間は保持されます。",
			alt_text="カウンセリング対話の終了確認",
		)

		save_flag(user_id, flag="end_chat")  # フラグを保存
		logger.debug(f"[Save Flag] flag: end_chat, user: {user_id}")

	elif event.postback.data == "check_time":
		logger.debug(f"[Checking Remaining Time] user {user_id}")
		with threading.Lock():
			remaining_time = timers[user_id].remaining_time()
		remaining_time = remaining_time // 60
		richmenu.apply_richmenu(richmenu_ids["REMAINING_TIME"][remaining_time], user_id)

	elif event.postback.data == "back_to_menu":
		logger.debug(f"[Back to Menu] user {user_id}")
		richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id)

	elif event.postback.data == "update_time":
		logger.debug(f"[Update Remaining Time] user {user_id}")
		with threading.Lock():
			remaining_time = timers[user_id].remaining_time()
		remaining_time = remaining_time // 60
		richmenu.apply_richmenu(richmenu_ids["REMAINING_TIME"][remaining_time], user_id)

	elif event.postback.data == "end_survey":
		logger.debug(f"[Send Message] user: {user_id}\n  アンケートの終了確認メッセージを送信")
		send_yes_no_buttons(
			configuration,
			reply_token=event.reply_token,
			question_text="アンケートを終了しますか？",
			alt_text="アンケートの終了確認",
		)

		save_flag(user_id, flag="end_survey")
		logger.debug(f"[Save Flag] flag: end_survey, user: {user_id}")

	elif event.postback.data == "maintenance":
		logger.warning(
			f"[WARNING] user: {user_id}  メンテナンス状態でないのに，メンテナンスメニューが適用されています。\n  再度リッチメニューを更新します。"
		)
		if session["keyword_accepted"] == False:
			richmenu.apply_richmenu(richmenu_ids["MAINTENANCE"], user_id)
		else:
			richmenu.apply_richmenu(richmenu_ids["START"], user_id)


# ユーザからメッセージを受信したときのハンドラ
@handler.add(MessageEvent)
def handle_message(event):
	if get_maintenance_mode():
		logger.debug(
			f"[Maintenance Mode] user: {event.source.user_id} tried to send a message during maintenance mode."
		)
		msg = "現在、メンテナンス中のため、メッセージを受け付けていません。\n\nしばらく時間をおいてから再度お試しください。"
		reply_to_line_user(event, msg)
		return

	user_id = event.source.user_id
	session = get_session(user_id)
	flag = get_flag(user_id)

	logger.debug(
		f"[Message Session] user: {user_id}\n{format_structure(session, indent=1)}\n  flag: {flag}\n  time: {get_time(user_id)}"
	)

	if NEED_START_KEYWORD and flag == "consent" and session["keyword_accepted"] == False:
		if event.message.text == YES:
			session["keyword_accepted"] = True
			save_session(user_id, session)
			logger.debug(f"[Save Session] user: {user_id}\n  keyword_accepted: {session['keyword_accepted']}")

			msg = "ご同意ありがとうございます。メニューのShopからご希望の時間を選択してください。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)
			richmenu.apply_richmenu(richmenu_ids["START"], user_id)

		else:
			session["keyword_accepted"] = False
			save_session(user_id, session)
			logger.debug(f"[Save Session] user: {user_id}\n  keyword_accepted: {session['keyword_accepted']}")

			msg = "ご同意いただけない場合は、カウンセリング対話を開始できません。\n\n同意はいつでも下のメニューから行えます。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)

	elif NEED_START_KEYWORD and session["keyword_accepted"] == False:
		msg = "下のメニューから同意を行うことで、カウンセリング対話を開始できます。"
		logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
		reply_to_line_user(event, msg)

	elif flag == "start_chat":
		if event.message.text == YES:
			session_time = get_time(user_id)
			timer = TrackableTimer(session_time, send_end_message, args=[user_id])
			timer.start()
			with threading.Lock():
				timers[user_id] = timer

			session["counseling_mode"] = True
			session["session_id"] = generate_session_id(n=10)
			save_session(user_id, session)
			logger.debug(
				f"[Save Session] user: {user_id}\n  counseling_mode: {session['counseling_mode']}\n  sessionID: {session['session_id']}"
			)

			richmenu.apply_richmenu(richmenu_ids["COUNSELING"], user_id)

			if session["finished"] == True:
				logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話の開始メッセージを送信")
				start_chat(event)
				session["finished"] = False
				save_session(user_id, session)
				logger.debug(f"[Save Session] user: {user_id}\n  finished: {session['finished']}")
			else:
				msg = "カウンセリング対話を再開します。\n\n新しく会話を始める場合は、メニューから“Reset”ボタンを押してください。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)

			logger.info(f"[Counseling Start] user: {user_id}, session_time: {session_time} seconds")

		else:
			msg = "カウンセリング対話を開始したい場合、もう一度メニューから“Start Chat”を選択して下さい。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)

	elif flag == "reset_history":
		if event.message.text == YES:
			bot = CounselorBot(
				LINEBOT_DB,
				INIT_MESSAGE,
				api_key=os.environ["OPENAI_API_KEY"],
				model_name=OPENAI_MODEL,
				system_prompt_path="prompt/system_prompt.txt",
				example_files=[
					"prompt/case1_0.txt",
					"prompt/case2_0.txt",
					"prompt/case3_0.txt",
					"prompt/case4_0.txt",
					"prompt/case5_0.txt",
					"prompt/case6_1.txt",
				],
			)
			bot.finish_dialogue(user_id)
			session["finished"] = True
			if session["counseling_mode"] == True:
				logger.debug(f"[Send Message] user: {user_id}\n  対話履歴をリセットし，カウンセリング対話を開始")
				start_chat(event, reset=True)
			else:
				session["finished"] = True
				save_session(user_id, session)
				logger.debug(f"[Save Session] user: {user_id}\n  finished: {session['finished']}")

				msg = "対話履歴をリセットしました。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)
		else:
			msg = "対話履歴のリセットをキャンセルしました。"
			logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
			reply_to_line_user(event, msg)

	elif session["keyword_accepted"] == True and session["counseling_mode"] == False and not session["survey_mode"] == True:
		msg = "カウンセリング対話を開始するには、メニューからご希望の時間を選択してください。"
		logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
		reply_to_line_user(event, msg)

	elif session["counseling_mode"] == True:
		if flag == "end_chat":
			if event.message.text == YES:
				session["counseling_mode"] = False
				session["survey_mode"] = True
				save_session(user_id, session)
				logger.debug(
					f"[Save Session] user: {user_id}\n  counseling_mode: {session['counseling_mode']}\n  survey_mode: {session['survey_mode']}"
				)

				with threading.Lock():
					remaining_time = timers[user_id].cancel()
					del timers[user_id]
				set_time(user_id, remaining_time)
				logger.info(f"[Counseling End] user: {user_id}, remaining_time: {remaining_time} seconds")

				richmenu.apply_richmenu(richmenu_ids["SURVEY"], user_id)

				logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話を終了し，アンケートの開始確認メッセージを送信")
				survey(event, tunnel)
				return

			else:
				msg = "対話を続けます。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)

		else:
			logger.debug(f"[Send Message] user: {user_id}\n  カウンセリング対話のメッセージを送信")
			reply(event, tunnel)
			return

	elif session["survey_mode"] == True:
		if flag == "start_survey":
			if event.message.text == YES:
				session["survey_progress"] = 1
				session["survey_mode"] = True
				save_session(user_id, session)
				logger.debug(
					f"[Save Session] user: {user_id}\n  survey_progress: {session['survey_progress']}\n  survey_mode: {session['survey_mode']}"
				)
				logger.debug(f"[Send Message] user: {user_id}\n  アンケートを送信")
				survey(event, tunnel)
			else:
				session["survey_mode"] = False
				session["survey_progress"] = 0
				save_session(user_id, session)
				logger.debug(
					f"[Save Session] user: {user_id}\n  survey_mode: {session['survey_mode']}\n  survey_progress: {session['survey_progress']}"
				)

				richmenu.apply_richmenu(richmenu_ids["START"], user_id)
				msg = "ご利用ありがとうございました。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)

		elif flag == "end_survey":
			if event.message.text == NO:
				logger.debug(f"[Send Message] user: {user_id}\n  アンケートを継続し，アンケートを再度送信")
				survey(event, tunnel)
			else:
				session["survey_progress"] = 0
				session["survey_mode"] = False
				save_session(user_id, session)
				logger.debug(
					f"[Save Session] user: {user_id}\n  survey_progress: {session['survey_progress']}\n  survey_mode: {session['survey_mode']}"
				)

				save_survey_results(user_id)

				init_survey(user_id)
				richmenu.apply_richmenu(richmenu_ids["START"], user_id)
				msg = "ご利用ありがとうございました。"
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				reply_to_line_user(event, msg)

		else:
			logger.debug(f"[Send Message] user: {user_id}\n  アンケートの送信")
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
		logger.error("[Webhook Error] Webhook signature verification failed.\n\t main.yamlのSTRIPE_WEBHOOKを確認してください。")
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
				logger.debug(f"[Send Message] user: {user_id}\n  {repr(msg)}")
				push_to_line_user(user_id, msg)
			except Exception as e:
				logger.error(f"[Send Message Error] Failed to send message to user {user_id}: {e}")

			logger.info(
				f"[Checkout] user: {user_id} additinal_time: {purchased_time}, total_time: {get_time(user_id)}"
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
		return redirect(session.url, permanent=False)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=400)


def success(request):
	return render(request, "success.html")


def cancel(request):
	return HttpResponse("支払いがキャンセルされました。")
