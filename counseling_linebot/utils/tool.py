
import time
import threading
import yaml
import stripe
import os, sys
import random
import string
from ruamel.yaml import YAML
from typing import List, Dict, Any

from linebot.v3.messaging import TextMessage

# 自作モジュールのインポート
from utils.set_logger import start_logger
from utils.ansi import *


# 設定の読み込み
def load_config(file_path):
    yaml = YAML()
    yaml.preserve_quotes = True  # コメントを保持
    with open(file_path, 'r', encoding='utf-8') as file:
        config = yaml.load(file)
    return config

config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(config_path)
logger = start_logger(conf['LOGGER']['SYSTEM'])



# 特定ディレクトリが存在しない場合は作成する関数
def create_directory():
    directories = [
        'database',
        'survey',
        'dialogue'
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Directory '{directory}' created.")
        else:
            pass


def split_message(message: str) -> list:
    """
    "\\n\\n" でメッセージを分割し、TextMessageのリストを返す。
    """
    msgs = []
    for msg in message.split("\n\n"):
        msgs.append(TextMessage(text=msg))
    return msgs


def create_checkout_session(product_name: str, unit_amount: int, time_seconds: int, line_id: str, tunnel_url: str):
    """
    Stripe Checkout Session を作成する共通関数。

    Parameters:
        product_name (str): 商品名
        unit_amount (int): 金額（JPY, 税込み）
        time_seconds (int): セッションの有効時間（秒）
        line_id (str): ユーザーID（metadataに含める）
        tunnel_url (str): success_url / cancel_url のベースURL

    Returns:
        stripe.checkout.Session: 作成されたセッションオブジェクト
    """
    
    # Checkout Session を作成する際、payment_intent_data 内に metadata を付与
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "jpy",
                "product_data": {
                    "name": product_name,
                },
                "unit_amount": unit_amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        payment_intent_data={
            "metadata": {
                "time": time_seconds,
                "user_id": line_id
            }
        },
        success_url=f"{tunnel_url}/success",
        cancel_url=f"{tunnel_url}/cancel",
    )
    return session


class TrackableTimer:
    def __init__(self, timeout, function, args=None):
        self.timeout = timeout
        self.function = function
        self.args = args if args else []
        self.start_time = None
        self.timer = None

    def start(self):
        self.start_time = time.time()
        self.timer = threading.Timer(self.timeout, self.function, args=self.args)
        self.timer.start()

    def cancel(self):
        if self.timer:
            self.timer.cancel()
        
        # 残り時間をreturn
        return self.remaining_time()

    def remaining_time(self):
        if self.start_time is None:
            return self.timeout
        elapsed = time.time() - self.start_time
        return max(0, self.timeout - elapsed)


# 辞書，リストなどのデータ構造を整形して文字列に変換する関数
def format_structure(data, indent=0):
    lines = []
    prefix = '  ' * indent

    if isinstance(data, dict):
        for key, value in data.items():
            key_str = f"{prefix}{key}:"
            if isinstance(value, (dict, list)):
                lines.append(key_str)
                lines.append(format_structure(value, indent + 1))
            else:
                lines.append(f"{key_str} {value}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            item_str = f"{prefix}- {idx} -:"
            if isinstance(item, (dict, list)):
                lines.append(f"{item_str}")
                lines.append(format_structure(item, indent + 1))
            else:
                lines.append(f"{item_str} {item}")
    else:
        lines.append(f"{prefix}{data}")

    return '\n'.join(lines)



def extract_event_info(data: Dict[str, Any]) -> Any:
    """
    辞書から 'events' → [0] → 'type' を取得し、
    type に応じて event から特定のキー・値を抽出する。
    """
    try:
        events = data.get("events")
        if not events:
            return "空のeventsを取得"

        event = events[0]
        if not isinstance(event, dict):
            raise ValueError("events[0] が辞書ではありません")

        event_type = event.get("type")
        if not event_type:
            raise ValueError("event に 'type' キーがありません")

        # type に応じた処理
        user_id = event.get("source", {}).get("userId", "Unknown")
        if event_type == "follow":
            return f'user: {user_id}\n  type: {event_type}'
        
        elif event_type == "postback":
            postback_data = event.get("postback").get('data', 'Unknown postback data')
            return f'user: {user_id}\n  type: {event_type}\n  data: {postback_data}'
        
        elif event_type == "message":
            message_type = event.get("message", {}).get("type", "Unknown message type")
            if message_type == "text":
                message = event.get("message", {}).get("text", "Unknown message text")

            elif message_type == "sticker":   # スタンプメッセージ
                message = event.get("message", {}).get("keywords", "Unknown sticker keywords")

            elif message_type == "image":
                message = "(画像メッセージ)"

            return f'user: {user_id}\n  type: {event_type}: {message_type}\n  msg: {repr(message)}'
        
        elif event_type == "unfollow":
            return f'user: {user_id}\n  type: {event_type}'
        
        else:
            return f'user: {user_id}\n  type: {event_type}: 未対応のタイプ'

    except Exception as e:
        return {"error": str(e)}



def format_history(history: List[Dict[str, str]], indent: int = 0, max_chars: int = None) -> str:
    """
    チャット履歴を 'role: content' の形式で1行ずつ整形し、各行の先頭に指定した空白を挿入する。
    改行を含む content はスペースに置き換え、max_chars 文字までに制限する（オプション）。
    
    Parameters:
        history: チャット履歴（辞書のリスト）
        indent: 各行の先頭に追加する空白の数（デフォルト0）
        max_chars: content の最大文字数（None の場合は制限なし）
    """
    prefix = " " * indent
    lines = []
    for entry in history:
        role = entry["role"]
        content = entry["content"].replace("\n", " ").strip()

        # max_chars が指定されている場合、content を制限する
        if max_chars is not None:
            content = content[:max_chars]
            
            # max_chars より長い場合は末尾に "..."
            if len(entry["content"]) > max_chars:
                content += "..."
            
        lines.append(f"{prefix}{role}: {content}")

    return "\n".join(lines)


def generate_session_id(n: int) -> str:
    """
    n 桁のランダムな英数字からなるセッションIDを生成する。
    
    Parameters:
        n: 生成する文字数（桁数）
    Returns:
        ランダムなセッションID（str）
    """
    characters = string.ascii_letters + string.digits  # a-zA-Z0-9
    return ''.join(random.choices(characters, k=n))


