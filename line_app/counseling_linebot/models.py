from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Session(models.Model):
	"""
	user_id: ユーザのLINE ID
	session_data: {
	               "counseling_mode": bool,    #カウンセリングモードかどうか
	               "keyword_accepted": bool,   #ユーザから同意を得たかどうか 
	               "survey_mode": bool,        #アンケートモードかどうか
	               "survey_progress": int,     #アンケートの進行度
	               "finished": bool,           #カウンセリングが終了しているかどうか
	               "session_id": str,          #セッションID（ランダムな文字列）
	               "response_mode": str,       #応答モード（"AI" or "Human"）デフォルトは"AI"
	               }
	# ユーザのLINE上のボタンの状態を管理する文字列．ユーザはボタン以外の動作（リッチメニュー操作や任意のテキスト送信）が可能なので，それらを無効にする
	flag: str: 'accepted', 'start_chat', 'reset_history', 'consent'
	time: セッションの時間（秒）
	risk_level: int (0-3): リスクレベル
	survey: dict[question]: アンケートの回答
	"""
	user_id = models.CharField(max_length=255, primary_key=True)
	session_data = models.JSONField(default=dict)
	flag = models.TextField(blank=True, default="")
	time = models.IntegerField(default=0)
	risk_level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(3)])
	risk_level_reason = models.TextField(blank=True, default="")  # リスクレベルの理由を保存するフィールド
	survey = models.JSONField(default=dict)
	summary = models.TextField(blank=True, default="")  # カウンセリング内容の要約を保存するフィールド


class Setting(models.Model):
	key = models.CharField(max_length=255, primary_key=True)
	value = models.TextField()


class ChatHistory(models.Model):
	user_id = models.CharField(max_length=255)
	speaker = models.CharField(max_length=64)
	message = models.TextField()
	post_time = models.DateTimeField()
	finished = models.IntegerField(default=0)
	session_id = models.CharField(max_length=64, default="")

class ReplyToken(models.Model):
	user_id = models.CharField(max_length=255, default="")
	token = models.TextField()
	created_at = models.DateTimeField()