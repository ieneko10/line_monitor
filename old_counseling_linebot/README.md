# Counseling LINE Bot

AIを活用したカウンセリング支援LINE Botシステムです。リアルタイムでの対話機能、セッション管理、データベース連携などの機能を提供します。

## 概要

このシステムは以下の主要機能を提供します：
- LINE Messaging APIを使用したリアルタイム対話
- AIエンジン（OpenAI GPT / Google Gemini）による自然言語処理
- セッション管理とユーザー履歴の保存
- リッチメニューによる直感的なユーザーインターフェース
- 管理者向けのWebインターフェース

## システム要件

### Python環境
- **Python**: 3.11.1 以上

### 主要ライブラリ
| ライブラリ              | バージョン |
| --------------------- | ---------- |
| Flask                 | 3.1.0      |
| line-bot-sdk          | 3.17.1     |
| openai                | 1.90.0     |
| google-generativeai   | 0.8.4      |
| cheroot               | 10.0.1     |
| waitress              | 3.0.2      |
| pyngrok               | 7.2.11     |
| watchdog              | 6.0.0      |
| rapidfuzz             | 3.13.0     |

## ディレクトリ構成

```
counseling_linebot/
├── main.py                    # メインアプリケーション
├── bot.py                     # LINE Bot メインロジック
├── requirements.txt           # 依存関係
├── config/                    # 設定ファイル
│   ├── main.yaml             # メイン設定
│   ├── dumy_main.yaml        # ダミー設定（テンプレート）
│   ├── richmenu.yaml         # リッチメニュー設定
│   └── logger/               # ログ設定
│       ├── dialogue.yaml     # 対話ログ設定
│       └── system.yaml       # システムログ設定
├── database/                  # データベースファイル
│   ├── linebot.db            # LINE Bot データベース
│   └── sessions.db           # セッション管理DB
├── dialogue/                  # 対話履歴
├── image/                     # 画像リソース
│   ├── consent.png           # 同意画面
│   ├── counseling.png        # カウンセリングメニュー
│   ├── maintenance.png       # メンテナンス画面
│   ├── start.png             # 開始画面
│   ├── survey.png            # アンケート画面
│   └── remaining_time/       # 残り時間表示用画像
├── log/                       # ログファイル
│   ├── dialogue.log          # 対話ログ
│   └── system.log            # システムログ
├── prompt/                    # AIプロンプト
│   ├── system_prompt.txt     # システムプロンプト
│   └── case*.txt             # ケース別プロンプト
├── survey/                    # アンケート結果
├── templates/                 # HTMLテンプレート
│   └── success.html          # 成功ページ
└── utils/                     # ユーティリティ
    ├── db_handler.py         # データベース操作
    ├── main_massage.py       # メッセージ処理
    ├── richmenu.py           # リッチメニュー管理
    ├── set_logger.py         # ログ設定
    ├── template_message.py   # テンプレートメッセージ
    └── tool.py               # 汎用ツール
```

## 環境構築

### 1. LINE Developersの準備

1. **LINE Developersアカウント作成**
   - [LINE Developers](https://developers.line.biz/)にアクセス
   - LINEアカウントでログイン
   - 新規プロバイダーを作成

2. **Messaging APIチャネルの作成**
   - 「チャネル作成」→「Messaging API」を選択
   - 必要情報を入力してチャネル作成

3. **チャネル設定**
   - チャネルシークレットを確認
   - アクセストークンを発行
   - 応答メッセージ機能：無効
   - Webhook機能：有効

### 2. ngrokのセットアップ

**Windows環境:**
1. [ngrok公式サイト](https://ngrok.com/)でアカウント作成
2. Windows用バイナリをダウンロード
3. 適当なディレクトリに展開
4. 環境変数PATHに追加
5. Authtokenを設定：
   ```bash
   ngrok authtoken YOUR_AUTHTOKEN
   ```

**Linux環境:**
```bash
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok
```

### 3. Python環境のセットアップ

1. **仮想環境の作成（推奨）**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

2. **依存関係のインストール**
   ```bash
   pip install -r requirements.txt
   ```

### 4. 設定ファイルの準備

1. `config/dumy_main.yaml`を`config/main.yaml`にコピー
2. 以下の項目を設定：
   ```yaml
   LINE_CHANNEL_SECRET: "YOUR_CHANNEL_SECRET"
   LINE_ACCESS_TOKEN: "YOUR_ACCESS_TOKEN"
   OPENAI_API_KEY: "YOUR_OPENAI_API_KEY"  # OpenAI使用時
   GOOGLE_API_KEY: "YOUR_GOOGLE_API_KEY"  # Gemini使用時
   ```

## 実行方法

### 基本的な起動
```bash
python main.py ./config/main.yaml
```

### パラメータ指定
```bash
# カスタム設定ファイルで起動
python main.py ./config/custom_config.yaml

# デバッグモードで起動
python main.py ./config/main.yaml --debug
```

### 開発環境での実行手順

1. **アプリケーションの起動**
   ```bash
   python main.py ./config/main.yaml
   ```

2. **ngrokでローカルサーバーを公開**
   ```bash
   ngrok http 8443
   ```

3. **Webhook URLの設定**
   - ngrokで表示されたHTTPS URLをコピー
   - LINE DevelopersのWebhook URLに`https://your-ngrok-url.ngrok.io/callback`を設定

4. **動作確認**
   - LINE Botを友だち追加
   - メッセージを送信して応答を確認

## 主要機能

### 1. 対話機能
- リアルタイムでのAI対話
- コンテキストを保持したセッション管理
- 複数のAIエンジン対応（OpenAI GPT / Google Gemini）

### 2. リッチメニュー
- 直感的なメニューインターフェース
- セッション開始/終了
- アンケート機能
- メンテナンス表示

### 3. データ管理
- SQLiteを使用したデータ永続化
- ユーザーセッション履歴
- 対話ログの保存

### 4. ログシステム
- 構造化されたログ出力
- システムログと対話ログの分離
- YAML設定による柔軟なログ制御

## トラブルシューティング

### よくある問題

1. **Webhook URLが反応しない**
   - ngrokのURLが正しく設定されているか確認
   - `/callback`パスが追加されているか確認
   - HTTPSを使用しているか確認

2. **AI応答が返ってこない**
   - API キーが正しく設定されているか確認
   - ネットワーク接続を確認
   - ログファイルでエラーメッセージを確認

3. **データベースエラー**
   - `database/`ディレクトリの権限を確認
   - SQLiteファイルが存在するか確認

### ログの確認

```bash
# システムログ
tail -f log/system.log

# 対話ログ
tail -f log/dialogue.log
```

## 開発・カスタマイズ

### 新しいプロンプトの追加
1. `prompt/`ディレクトリに新しいテキストファイルを作成
2. `bot.py`でプロンプトローディング処理を更新

### リッチメニューのカスタマイズ
1. `image/`ディレクトリに新しい画像を追加
2. `config/richmenu.yaml`で設定を更新
3. `utils/richmenu.py`でメニュー作成処理を実行

### データベーススキーマの変更
1. `utils/db_handler.py`でスキーマを更新
2. 既存データのマイグレーション処理を実装

## ライセンス

このプロジェクトは開発・教育目的で作成されています。商用利用の際は適切なライセンス確認を行ってください。

## 注意事項

- 本番環境では適切なセキュリティ設定を行ってください
- API キーなどの機密情報は環境変数で管理してください
- 定期的なバックアップを実施してください
- ログファイルのローテーション設定を検討してください
