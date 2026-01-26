import os, sys
import yaml
from watchdog.events import FileSystemEventHandler

# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from utils import richmenu
from utils.tool import load_config
from utils.template_message import broadcast_message
from utils.main_massage import timers
from utils.db_handler import get_all_users, reset_all_flags, reset_all_sessions, set_maintenance_mode


# ロガーと設定の読み込み
main_config_path = sys.argv[1] if len(sys.argv) > 1 else './config/main.yaml'
conf = load_config(main_config_path)
logger = start_logger(conf['LOGGER']['SYSTEM'])

richmenu_ids = load_config(conf['RICHMENU_PATH'])  # リッチメニューの設定を読み込み

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, filepath):
        self.filepath = filepath
        self.last_push_flag, self.last_richmenu_flag = self._load_initial_flag()

    def _load_initial_flag(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    push_flag = config.get("PUSH_FLAG", False)
                    richmenu_flag = config.get("RICHMENU_FLAG", False)
                    logger.debug(f"[Initial Load] PUSH_FLAG: {push_flag}, RICHMENU_FLAG: {richmenu_flag}")
                    return push_flag, richmenu_flag
                
            except Exception as e:
                logger.error(f"[Initialization Error] Failed to read YAML: {e}")
        
        else:
            logger.error(f"[Initialization Error] File not found: {self.filepath}")
            return None

    def on_modified(self, event):

        if event.src_path.endswith(os.path.basename(self.filepath)):
            try:
                with open(event.src_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    richmenu_flag = data.get("RICHMENU_FLAG", False)
                    push_flag = data.get("PUSH_FLAG", False)
                    msg = data.get("PUSH_MESSAGE", "")

                    if push_flag != self.last_push_flag:
                        if push_flag != True:
                            logger.debug(f"[File Change] PUSH_FLAG: {push_flag} != True")
                        elif push_flag == True:
                            logger.debug(f"[File Change] PUSH_FLAG: {push_flag} == True")
                            broadcast_message(msg)

                    elif richmenu_flag != self.last_richmenu_flag:
                        if richmenu_flag != True:
                            logger.debug(f"[File Change] RICHMENU_FLAG: {richmenu_flag} != True")
                        elif richmenu_flag == True:
                            logger.debug(f"[File Change] RICHMENU_FLAG: {richmenu_flag} == True")

                            maintenace_mode_on()
                    
                    self.last_richmenu_flag = richmenu_flag    
                    self.last_push_flag = push_flag

            except Exception as e:
                # yamlファイルの読み込み時，コロンがない場合などに発生（yamlファイル操作中に発生してしまうためコメントアウト）
                # logger.debug(f"[Load Yaml] Failed to read YAML: {repr(e)}")    
                pass


def maintenace_mode_on():
    set_maintenance_mode(True)  # メンテナンスモードをオンにする
    for timer in timers.values():
        timer.cancel()
    reset_all_sessions()
    reset_all_flags()  # 全てのフラグをリセット
    logger.info("[All Flag Reset]")
    logger.info("[All Session Reset]")
    
    # メンテナンス用のリッチメニューを適用
    all_users = get_all_users()    # データベースから全ユーザを取得
    logger.info(f'[All Richmenu Applied] maintenance mode for {len(all_users)} users')
    for user in all_users:
        richmenu.apply_richmenu(richmenu_ids['MAINTENANCE'], user)