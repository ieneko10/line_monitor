import json
import os
from pathlib import Path

from openai import OpenAI
from django.conf import settings

from logger.set_logger import start_logger
from counseling_linebot.models import ChatHistory, Session


conf = settings.MAIN_CONFIG
logger = start_logger(conf["LOGGER"]["ASYNC_LLM"])

OPENAI_MODEL = conf["OPENAI_MODEL"]
RISK_PROMPT_PATH = conf["PROMPT"]["RISK_LEVEL_DETECTION"]


def risk_level_detection_async(user_id, session_id, current_uttr):
	"""対話履歴からリスクレベルを非同期で推定し、Sessionに保存する。"""
	try:
		logs = ChatHistory.objects.filter(user_id=user_id)
		if session_id:
			logs = logs.filter(session_id=session_id)
		logs = logs.order_by("post_time")

		dialogue_history = ""
		for log in logs[1:]:  # 最初のログはセッション開始のシステムメッセージなのでスキップ
			if log.speaker == "user":
				speaker_label = "ユーザ"
			elif log.speaker == "assistant":
				speaker_label = "AIカウンセラー"
			elif log.speaker == "counselor":
				speaker_label = "AIカウンセラー"
			else:
				speaker_label = str(log.speaker)
			dialogue_history += f"{speaker_label}: {log.message}\n"
		dialogue_history += f"ユーザ: {current_uttr}\n"

		with open(RISK_PROMPT_PATH, "r", encoding="utf-8") as f:
			prompt_template = f.read()
		prompt = prompt_template.replace("{{ dialogue_history }}", dialogue_history)
		logger.debug(f"[Risk Detection] Prompt:\n{prompt}")

		client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])  
		response = client.chat.completions.create(
			model=OPENAI_MODEL,
			messages=[{"role": "user", "content": prompt}],
			temperature=0,
		)
		content = response.choices[0].message.content or ""
		if "```" in content:
			content = content.replace("```json", "").replace("```", "").strip()

		parsed = json.loads(content)
		reason = parsed.get("reason", "")
		score = int(parsed.get("score", 0))
		score = max(0, min(3, score))
		Session.objects.filter(user_id=user_id).update(risk_level=score, risk_level_reason=reason)
		logger.info(f"[Risk Level] user: {user_id}, risk_level: {score}\n\treason: {reason}")

	except Exception as e:
		logger.error(f"[Risk Level] Failed to detect risk level for user {user_id}: {e}")
