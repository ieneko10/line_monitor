# tcp_client.py
import socket

HOST = '127.0.0.1'  # 接続先サーバ
PORT = 50007        # サーバ側と合わせる

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # サーバに接続
        s.connect((HOST, PORT))
        print(f"サーバ {HOST}:{PORT} に接続しました")

        while True:
            msg = input("送信するメッセージ（空で終了）: ")
            if not msg:
                break

            # 文字列 → バイト列にエンコードして送信
            s.sendall(msg.encode('utf-8'))

            # サーバからの応答を受信
            data = s.recv(1024)
            if not data:
                print("サーバから切断されました")
                break

            print("受信:", data.decode('utf-8'))

if __name__ == "__main__":
    main()
