from pyngrok import ngrok

# 5000番ポートのHTTPトンネルを開設する
tunnel = ngrok.connect(8080, "http")
print("Public URL:", tunnel.public_url)

# 例：Flask アプリケーションを起動する場合
from flask import Flask
app = Flask(__name__)
@app.route("/")
def index():
    return "Hello, ngrok!"


@app.route("/aaa")
def aaa():
    return "aaa, ngrok!"

if __name__ == "__main__":
    app.run(port=8080)

input("Press Enter to terminate ngrok tunnel...")
ngrok.disconnect(tunnel.public_url)
