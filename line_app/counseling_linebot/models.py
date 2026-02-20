from django.db import models


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
	flag: str: 'accepted', 'start_chat', 'reset_history', 'consent
	time: セッションの時間（秒）
	survey: dict[question]: アンケートの回答
	"""
	user_id = models.CharField(max_length=255, primary_key=True)
	session_data = models.JSONField(default=dict)
	flag = models.TextField(blank=True, default="")
	time = models.IntegerField(default=0)
	survey = models.JSONField(default=dict)


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
