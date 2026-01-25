from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import yaml
import time
import os

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, filepath):
        self.filepath = filepath
        self.last_content = self._load_initial_content()

    def _load_initial_content(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    return data.get("content", "").strip()
            except Exception as e:
                print(f"[初期化エラー] YAML読み込み失敗: {e}")
        return None

    def on_modified(self, event):
        if event.src_path.endswith(self.filepath):
            try:
                with open(event.src_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    content = data.get("content", "").strip()

                    if content != self.last_content:
                        print(f"[変更検知] content: {content}")
                        if content == "start":
                            print("→ 処理Aを1回だけ実行")
                        elif content == "end":
                            print("→ 処理Bを1回だけ実行")
                        self.last_content = content
            except Exception as e:
                print(f"YAML読み込みエラー: {e}")

# ファイル名を指定
yaml_file = "command.yaml"

# 監視開始
observer = Observer()
handler = FileChangeHandler(filepath=yaml_file)
observer.schedule(handler, path='.', recursive=False)
observer.start()

try:
    print("メイン処理を実行中...")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
