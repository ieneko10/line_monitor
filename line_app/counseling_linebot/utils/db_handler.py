import json
import datetime

# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from django.conf import settings
from django.db import models
from counseling_linebot.models import Session, Setting, ChatHistory

# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
logger = start_logger(conf['LOGGER']['SYSTEM'])


SURVEY_MESSAGES = conf["SURVEY"]['SURVEY_MESSAGES']
SURVEY_LAST_MESSAGE = conf["SURVEY"]['SURVEY_LAST_MESSAGE']
LANGUAGE = conf["LANGUAGE"]
SESSIONS_DB = conf["SESSIONS_DB"]
LINEBOT_DB = conf["LINEBOT_DB"]

def init_db():
    """
    user_id: ユーザのLINE ID
    session_data: {
                   "counseling_mode": bool,    #カウンセリングモードかどうか
                   "keyword_accepted": bool,   #ユーザから同意を得たかどうか 
                   "survey_mode": bool,        #アンケートモードかどうか
                   "survey_progress": int,     #アンケートの進行度
                   "finished": bool,           #カウンセリングが終了しているかどうか
                   "session_id": str,          #セッションID（ランダムな文字列）
                   }
    # ユーザのLINE上のボタンの状態を管理する文字列．ユーザはボタン以外の動作（リッチメニュー操作や任意のテキスト送信）が可能なので，それらを無効にする
    flag: str: 'accepted', 'start_chat', 'reset_history'
    time: セッションの時間（秒）
    survey: dict[question]: アンケートの回答
    """
    logger.info("[Initializing Database]")
    # Django ORMを利用するため、ここではテーブル作成を行わない
    return

def init_settings_table():
    logger.info("[Initializing Settings Table]")
    return

def set_maintenance_mode(enabled: bool):
    logger.info(f"[Setting Maintenance Mode] {enabled}")
    Setting.objects.update_or_create(
        key="maintenance",
        defaults={"value": str(int(enabled))},
    )

def get_maintenance_mode() -> bool:
    setting = Setting.objects.filter(key="maintenance").first()
    value = bool(int(setting.value)) if setting else False
    logger.debug(f"[Getting Maintenance Mode] {value}")
    return value


def register_user(user_id):
    session_data = {
        "counseling_mode": False,
        "keyword_accepted": False,
        "survey_mode": False,
        "survey_progress": 0,
        "finished": True,
        "session_id": ''
    }
    Session.objects.update_or_create(
        user_id=user_id,
        defaults={
            "session_data": session_data,
            "flag": "",
            "time": 0,
            "survey": {},
        },
    )

def get_all_users():
    """
    全ユーザのuser_idを取得する
    """
    users = list(Session.objects.values_list("user_id", flat=True))
    if users:
        return users
    else:
        logger.warning("[Not Found] sessions テーブルにユーザが存在しません。")
        return []

def get_session(user_id):
    session = Session.objects.filter(user_id=user_id).first()
    if session is not None:
        return session.session_data
    else:
        logger.error(f"[Not Found] user_id '{user_id}' のセッションが見つかりません。")
        return None

def save_session(user_id, data):
    updated = Session.objects.filter(user_id=user_id).update(session_data=data)
    if not updated:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")
    

def reset_all_sessions():
    """
    全ユーザのセッションの"counseling_mode", "survey_mode","survey_progress"をリセットする
    """
    for session in Session.objects.all():
        data = session.session_data or {}
        data["counseling_mode"] = False
        data["survey_mode"] = False
        data["survey_progress"] = 0
        session.session_data = data
        session.save(update_fields=["session_data"])



def delete_session(user_id):
    Session.objects.filter(user_id=user_id).delete()

def get_flag(user_id):
    return Session.objects.filter(user_id=user_id).values_list("flag", flat=True).first()

def save_flag(user_id, flag):
    """
    ユーザのフラグを保存する
    """
    updated = Session.objects.filter(user_id=user_id).update(flag=flag)
    if not updated:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

def reset_flag(user_id):
    """
    ユーザのフラグをリセットする
    """
    Session.objects.filter(user_id=user_id).update(flag="")

def reset_all_flags():
    """
    全ユーザのフラグをリセットする
    """
    Session.objects.all().update(flag="")


def increment_time(user_id, seconds):
    Session.objects.filter(user_id=user_id).update(time=models.F("time") + seconds)

def get_time(user_id):
    session = Session.objects.filter(user_id=user_id).first()
    if session:
        return session.time
    logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。新規挿入します。")
    register_user(user_id)
    return 0
    
def set_time(user_id, seconds):
    """
    ユーザのセッション時間を設定する
    """
    Session.objects.filter(user_id=user_id).update(time=seconds)
    
def reset_time(user_id):
    Session.objects.filter(user_id=user_id).update(time=0)

def init_survey(user_id):
    """
    ユーザのアンケートを初期化する
    """
    survey_data = {msg: '' for msg in SURVEY_MESSAGES}
    survey_data[SURVEY_LAST_MESSAGE] = ''
    
    updated = Session.objects.filter(user_id=user_id).update(survey=survey_data)
    if not updated:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

def get_survey(user_id):
    """
    ユーザのアンケートを取得する
    """
    session = Session.objects.filter(user_id=user_id).first()
    if session:
        return session.survey
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")
        return None

def save_survey(user_id, survey_data):
    """
    ユーザのアンケートを保存する
    """
    updated = Session.objects.filter(user_id=user_id).update(survey=survey_data)
    if not updated:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")


def save_survey_results(user_id):
    """
    ユーザのアンケート結果をファイルに保存する
    """
    survey_results = get_survey(user_id)
    session = get_session(user_id)
    session_id = session.get('session_id', '')
    with open(f"survey/trial_{LANGUAGE}_{user_id}.txt", "a", encoding='utf-8') as w:
        # 日時を書き込み
        w.write(f"[{datetime.datetime.now()}] Session ID: {session_id}\n")
        for i in range(len(SURVEY_MESSAGES)):
            survey_message = SURVEY_MESSAGES[i]
            # survey_messageを\n\nで分割
            if "\n" in survey_message:
                survey_message = survey_message.split("\n")[-1]
            if survey_results[SURVEY_MESSAGES[i]] == '':
                w.write("\n")
                return
            w.write(f"{survey_message}\t{survey_results[SURVEY_MESSAGES[i]]}\n")
        
        w.write(f"{SURVEY_LAST_MESSAGE}\t{survey_results[SURVEY_LAST_MESSAGE]}\n\n")


def save_dialogue_history_from_db(user_id):
    """
    ユーザの対話履歴をファイルに保存する
    
    chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            speaker TEXT,
            message TEXT,
            post_time TEXT,
            finished INTEGER,
            write_flag INTEGER DEFAULT 0
        )

    """
    
    rows = ChatHistory.objects.filter(user_id=user_id).order_by("post_time").values_list(
        "speaker", "message", "post_time", "finished"
    )

    if not rows:
        logger.error(f"user_id '{user_id}' の対話履歴が見つかりません。")
        return

    with open(f"dialogue/{user_id}.txt", "a", encoding='utf-8') as w:
        for row in rows:
            speaker, message, post_time, finished = row
            # messageの\nをそのまま書き込む
            if "\n" in message:
                message = message.replace("\n", "\\n")
            w.write(f"{post_time}\t{finished}\t{speaker.ljust(9)}\t{message}\n")
        w.write("\n")

def save_dialogue_history(user_id, speaker, message, finished, post_time):
    """
    ユーザの対話履歴をファイルに保存する
    """
    with open(f"dialogue/{user_id}.txt", "a", encoding='utf-8') as w:
        # messageの\nをそのまま書き込む
        if "\n" in message:
            message = message.replace("\n", "\\n")
        w.write(f"{post_time}\t{finished}\t{speaker.ljust(9)}\t{message}\n")

    
