from django.db import models


class Session(models.Model):
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
