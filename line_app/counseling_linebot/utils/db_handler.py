import sqlite3
import json
import sys
import datetime

# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from utils.tool import load_config

# ロガーと設定の読み込み
config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(config_path)
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
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS sessions (
            user_id TEXT PRIMARY KEY,
            session_data TEXT,
            flag TEXT,
            time INTEGER DEFAULT 0,
            survey TEXT
        )
        ''')
    conn.commit()
    conn.close()

def init_settings_table():
    logger.info("[Initializing Settings Table]")
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

def set_maintenance_mode(enabled: bool):
    logger.info(f"[Setting Maintenance Mode] {enabled}")
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', ('maintenance', str(int(enabled))))
    conn.commit()
    conn.close()

def get_maintenance_mode() -> bool:
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('maintenance',))
    row = cursor.fetchone()
    conn.close()
    logger.debug(f"[Getting Maintenance Mode] {bool(int(row[0])) if row else False}")
    return bool(int(row[0])) if row else False


def register_user(user_id):
    session_data = {
        "counseling_mode": False,
        "keyword_accepted": False,
        "survey_mode": False,
        "survey_progress": 0,
        "finished": True,
        "session_id": ''
    }

    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (user_id, session_data, flag, time, survey)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        json.dumps(session_data, ensure_ascii=False),
        json.dumps('', ensure_ascii=False),
        0,  # 初期時間
        json.dumps({}, ensure_ascii=False)  # 初期アンケートは空のリスト
    ))
    conn.commit()
    conn.close()

def get_all_users():
    """
    全ユーザのuser_idを取得する
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM sessions")
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        return [row[0] for row in rows]
    else:
        logger.warning("[Not Found] sessions テーブルにユーザが存在しません。")
        return []

def get_session(user_id):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT session_data FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row != None:
        return json.loads(row[0])
    else:
        logger.error(f"[Not Found] user_id '{user_id}' のセッションが見つかりません。")
        return None

def save_session(user_id, data):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()

    # ユーザーが存在するか確認
    cursor.execute("SELECT 1 FROM sessions WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if exists:
        # セッションデータだけ更新
        cursor.execute("UPDATE sessions SET session_data = ? WHERE user_id = ?",
                       (json.dumps(data), user_id))
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

    conn.commit()
    conn.close()
    

def reset_all_sessions():
    """
    全ユーザのセッションの"counseling_mode", "survey_mode","survey_progress"をリセットする
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions
        SET session_data = json_set(session_data, 
                                    '$.counseling_mode', false, 
                                    '$.survey_mode', false,
                                    '$.survey_progress', 0
        )
    """)
    conn.commit()
    conn.close()



def delete_session(user_id):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_flag(user_id):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT flag FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None

def save_flag(user_id, flag):
    """
    ユーザのフラグを保存する
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()

    # ユーザーが存在するか確認
    cursor.execute("SELECT 1 FROM sessions WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if exists:
        # フラグだけ更新
        cursor.execute("UPDATE sessions SET flag = ? WHERE user_id = ?",
                       (flag, user_id))
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

    conn.commit()
    conn.close()

def reset_flag(user_id):
    """
    ユーザのフラグをリセットする
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET flag = ? WHERE user_id = ?",
        ('', user_id)
    )
    conn.commit()
    conn.close()

def reset_all_flags():
    """
    全ユーザのフラグをリセットする
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET flag = ''")
    conn.commit()
    conn.close()


def increment_time(user_id, seconds):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions
        SET time = time + ?
        WHERE user_id = ?
    """, (seconds, user_id))
    conn.commit()
    conn.close()

def get_time(user_id):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT time FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    else:
        # 新規挿入（必要なカラムすべて含む）
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。新規挿入します。")
        cursor.execute("INSERT INTO sessions (user_id, session_data, flag, time) VALUES (?, ?, ?, ?)",
                       (user_id, {}, '', 0))
        return 0
    
def set_time(user_id, seconds):
    """
    ユーザのセッション時間を設定する
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions
        SET time = ?
        WHERE user_id = ?
    """, (seconds, user_id))
    conn.commit()
    conn.close()
    
def reset_time(user_id):
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions
        SET time = 0
        WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()

def init_survey(user_id):
    """
    ユーザのアンケートを初期化する
    """
    survey_data = {msg: '' for msg in SURVEY_MESSAGES}
    survey_data[SURVEY_LAST_MESSAGE] = ''
    
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()

    # ユーザーが存在するか確認
    cursor.execute("SELECT 1 FROM sessions WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if exists:
        # アンケートだけ更新
        cursor.execute("UPDATE sessions SET survey = ? WHERE user_id = ?",
                       (json.dumps(survey_data, ensure_ascii=False), user_id))
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

    conn.commit()
    conn.close()

def get_survey(user_id):
    """
    ユーザのアンケートを取得する
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT survey FROM sessions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")
        return None

def save_survey(user_id, survey_data):
    """
    ユーザのアンケートを保存する
    """
    conn = sqlite3.connect(SESSIONS_DB)
    cursor = conn.cursor()

    # ユーザーが存在するか確認
    cursor.execute("SELECT 1 FROM sessions WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()

    if exists:
        # アンケートだけ更新
        cursor.execute("UPDATE sessions SET survey = ? WHERE user_id = ?",
                       (json.dumps(survey_data, ensure_ascii=False), user_id))
    else:
        logger.error(f"user_id '{user_id}' が sessions テーブルに存在しません。")

    conn.commit()
    conn.close()


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
    
    # LINEBOT_DBの読み込み
    conn = sqlite3.connect(LINEBOT_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT speaker, message, post_time, finished FROM chat_history WHERE user_id = ? ORDER BY post_time", (user_id,))
    rows = cursor.fetchall()
    conn.close()

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

    
