# tcp_server.py
import socket

HOST = '127.0.0.1'  # 自分自身（ローカルホスト）
PORT = 50007        # 任意の空いているポート番号

def main():
    # IPv4 + TCP のソケットを作成
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # アドレスをソケットに割り当て
        s.bind((HOST, PORT))
        # 接続待ち状態にする（キュー長は 1 以上）
        s.listen(1)
        print(f"TCPサーバ起動中... {HOST}:{PORT} で待機")

        # クライアントからの接続を待つ（ブロッキング）
        conn, addr = s.accept()
        with conn:
            print(f"接続: {addr}")
            while True:
                # 最大 1024 バイト受信
                data = conn.recv(1024)
                if not data:
                    # 空データ → 切断とみなす
                    print("クライアント切断")
                    break

                print("受信:", data.decode('utf-8'))
                # 受け取ったデータをそのまま返す（エコー）
                conn.sendall(b"Echo: " + data)

if __name__ == "__main__":
    main()
