import re
import random
from typing import List, Dict, Tuple, Any, Optional

from openai import OpenAI
import google.generativeai as genai
from rapidfuzz.process import extract
import re

# 自作モジュールのインポート
from logger.set_logger import start_logger
from logger.ansi import *
from django.conf import settings
from django.utils import timezone
from counseling_linebot.models import ChatHistory
from counseling_linebot.utils.tool import format_history
from counseling_linebot.utils.db_handler import save_dialogue_history, get_session

# ロガーの設定
conf = settings.MAIN_CONFIG
logger = start_logger(conf['LOGGER']['DIALOGUE'])

# Constants
DIALOGUE_FINISHED = 1
DIALOGUE_NOT_FINISHED = 0
DEFAULT_GEMINI_MODEL = "gemini-exp-1206"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_CONTEXT_NUM = 500   # 指定した user_id のチャット履歴を「新しい順」に最大 DEFAULT_CONTEXT_NUM 件まで取得
SIMILARITY_THRESHOLD = 40
RESPONSE_GENERATION_TRIALS = 3

# Type Aliases for Clarity
# ChatHistory = List[Dict[str, str]]

class APIClient:
    """
    Base class for interacting with AI APIs.
    """
    def __init__(self, api_key: str, model_name: str, temperature: float):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        logger.debug(f"\n[Initialized Bot] {self.__class__.__name__} with model: {model_name}, temperature: {temperature}")

    def reply(self, history: ChatHistory) -> str:
        raise NotImplementedError("Subclasses must implement the reply method")

class OpenAIReply(APIClient):
    """
    Handles communication with the OpenAI API.
    """
    def __init__(self, api_key: str, model_name: str, temperature: float = DEFAULT_TEMPERATURE):
        super().__init__(api_key, model_name, temperature)
        self.client = OpenAI(api_key=self.api_key)
        # logger.debug(f"[Bot] OpenAI client initialized with model: {model_name}")

    def reply(self, history: ChatHistory) -> str:
        # logger.debug(f"[Sending Request] History To OpenAI.")
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=history,
                temperature=self.temperature
            )
            res = response.choices[0].message.content
            # logger.debug(f"[Response Received] {repr(res)}")
            return res
        
        except Exception as e:
            logger.debug(f"[Bot] Error communicating with OpenAI: {e}")
            return "申し訳ありませんが、ただいま応答できません。"

class GeminiReply(APIClient):
    """
    Handles communication with the Google Gemini API.
    """
    def __init__(self, api_key: str, model_name: str = DEFAULT_GEMINI_MODEL, temperature: float = DEFAULT_TEMPERATURE):
        super().__init__(api_key, model_name, temperature)
        genai.configure(api_key=self.api_key)
        self.client = genai.GenerativeModel(self.model_name)
        self.config = genai.types.GenerationConfig(temperature=self.temperature)
        logger.debug(f"[Bot] Gemini client initialized with model: {model_name}")

    def _convert_history(self, history: ChatHistory) -> Tuple[List[Dict[str, Any]], str]:
        """
        Converts the internal chat history format to the format expected by the Gemini API.
        """
        gemini_history: List[Dict[str, Any]] = []
        for h in history:
            if h["role"] == "system":
                gemini_history.append({"role": "model" , "parts": h["content"]})
            elif h["role"] == "user":
                gemini_history.append({"role": "user" , "parts": h["content"]})
            elif h["role"] == "assistant":
                gemini_history.append({"role": "model" , "parts": h["content"]})
        return gemini_history, history[-1]["content"]

    def reply(self, history: ChatHistory) -> str:
        logger.debug(f"[Bot] Preparing Gemini request. History: {history}")
        try:
            gemini_history, user_input = self._convert_history(history)
            gemini_history = gemini_history[:-1]  # Remove the last message as it's the current user input
            chat = self.client.start_chat(history=gemini_history)
            response = chat.send_message(user_input, generation_config=self.config)
            logger.debug(f"[Bot] Gemini response received: {response.text}")
            return response.text
        except Exception as e:
            logger.debug(f"[Bot] Error communicating with Gemini: {e}")
            return "申し訳ありませんが、ただいま応答できません。"

class CounselorBot:
    """
    A counseling bot that uses an AI model to generate responses.
    """
    def __init__(self, db_path: str,
                 init_message: str,
                 system_prompt_path: str,
                 example_files: List[str],
                 api_key: str,
                 model_name: str,
                 model_type: str = "openai",
                 google_api_key: str = "",
                 language: str = "Japanese"):
        self.db_path = db_path
        self.init_message = init_message
        self.system_prompt_path = system_prompt_path
        self.example_files = example_files
        self.api_key = api_key
        self.model_type = model_type.lower()
        self.google_api_key = google_api_key
        self.language = language
        self.conn = None
        self.cursor = None
        
        # モデルタイプに応じてクライアントを初期化
        if self.model_type == "gemini":
            if not self.google_api_key:
                raise ValueError("Google API key is required for Gemini model")
            self.client = GeminiReply(api_key=self.google_api_key, model_name=model_name)
        else:  # デフォルトはOpenAI
            self.client = OpenAIReply(api_key=self.api_key, model_name=model_name)
        
        self._initialize_database()
        logger.debug(f'[Load Examples] {self.example_files}')
        self.system_prompt = self._load_system_prompt()
        self.examples = self._load_examples()

    def _initialize_database(self):
        """
        Connects to the SQLite database and creates the chat history table if it doesn't exist.
        """
        # Django ORMを利用するため、ここではテーブル作成を行わない
        return

    def _load_system_prompt(self) -> str:
        """
        Loads the system prompt from the specified file.
        """
        try:
            with open(self.system_prompt_path, "r", encoding='utf-8') as f:
                prompt = f.read()
                return prompt
        except FileNotFoundError:
            logger.error(f"[ERROR] System prompt file not found: {self.system_prompt_path}")
            return ""
        except Exception as e:
            logger.error(f"[ERROR] Error loading system prompt: {e}")
            return ""

    def _load_examples(self) -> List[str]:
        """
        Loads example prompts from the specified files.
        """
        examples = []
        for file in self.example_files:
            try:
                with open(file, "r", encoding='utf-8') as f:
                    examples.append("".join(f.readlines()))
            except FileNotFoundError:
                logger.warning(f"[Bot] Example file not found: {file}")
            except Exception as e:
                logger.error(f"[Bot] Error loading example file {file}: {e}")
        return examples

    def start_message(self, user_id: str) -> str:
        """
        Starts a new conversation with the user, initializes the dialogue in the database.
        """
        logger.info(f"[StartChat] user: {user_id}")
        session = get_session(user_id)
        session_id = session.get('session_id', '')
        try:
            post_time = timezone.now()
            ChatHistory.objects.create(
                user_id=user_id,
                speaker="user",
                message="[START]",
                post_time=post_time,
                finished=DIALOGUE_FINISHED,
                session_id=session_id,
            )
            save_dialogue_history(user_id, "user", "[START]", session_id, post_time)  # Save to file

            post_time = timezone.now()
            ChatHistory.objects.create(
                user_id=user_id,
                speaker="assistant",
                message=self.init_message,
                post_time=post_time,
                finished=DIALOGUE_NOT_FINISHED,
                session_id=session_id,
            )
            save_dialogue_history(user_id, "assistant", self.init_message, session_id, post_time)  # Save to file
            return self.init_message
        except Exception as e:
            logger.debug(f"[Bot] Error starting conversation for user {user_id}: {e}")
            return "エラーが発生しました。もう一度お試しください。"

    # 指定した user_id のチャット履歴を「新しい順」に最大 context_num 件まで取得
    def _get_history(self, user_id: str, context_num: int) -> ChatHistory:
        """
        Retrieves the chat history for a given user.
        """
        try:
            rows = (
                ChatHistory.objects.filter(user_id=user_id)
                .order_by("-id")
                .values_list("speaker", "message", "finished")[:context_num]
            )

            history: ChatHistory = []
            for speaker, message, finished in rows:
                if finished == DIALOGUE_FINISHED:
                    break
                history.append({"role": speaker, "content": message})
            return history[::-1]

        except Exception as e:
            logger.debug(f"[Bot] Error retrieving chat history for user {user_id}: {e}")
            return []

    def _generate_response(self, history: ChatHistory, trial_num: int = RESPONSE_GENERATION_TRIALS, user_id: str ='') -> Tuple[str, int]:
        """
        Generates a response using the AI model, with multiple trials to find a suitable response.
        """
        log_hist = format_history(history, indent=2, max_chars=200)
        logger.debug(f"[Sending Request] NumTrials:{trial_num}, History: \n{log_hist}")
        prev_last_reply = next((h["content"] for h in reversed(history) if h["role"] == "assistant"), "")
        best_reply: Tuple[int, Optional[str], int] = (9999, None, DIALOGUE_NOT_FINISHED)

        for i in range(trial_num):
            rand_id = random.randrange(len(self.examples))   # ランダムにexampleを選択
            prompt = self.system_prompt + self.examples[rand_id]
            augmented_history = [{"role": "system", "content": prompt}] + history
            generated_response = self.client.reply(augmented_history)

            finished = DIALOGUE_NOT_FINISHED
            if "[Dialogue Finished]" in generated_response:
                finished = DIALOGUE_FINISHED

            # Skip if the response contains Markdown
            if any(char in generated_response for char in ["*", "#", "-", "_"]):
                logger.debug(f"[Bot] Skipping response due to Markdown: {generated_response[:100]}...")
                continue

            if "\n\n" in generated_response:
                generated_response = generated_response.split("\n\n")[0]

            removed_response = re.sub(r"\[.*?\]\s+", "", generated_response)   # AIからの応答に含まれる[]で囲まれた文字列を削除
            removed_prev_last_reply = re.sub(r"\[.*?\]\s+", "", prev_last_reply)  # 前回の応答に含まれる[]で囲まれた文字列を削除
            similarity = extract(removed_response, [removed_prev_last_reply])[0][1]   # 前回の応答と，今回生成された応答の類似度を計算
            logger.debug(f"[Trial {i+1}] Similarity: {similarity:.3f}, example: {self.example_files[rand_id]} \n  Generated response: {repr(removed_response)}")

            if similarity < SIMILARITY_THRESHOLD:
                logger.info(f"[Acceptable] user: {user_id},  {similarity:.3f} < {SIMILARITY_THRESHOLD}\n  SendMessage: {repr(generated_response)}")
                return generated_response, finished

            if similarity < best_reply[0]:
                best_reply = (similarity, generated_response, finished)
                # logger.debug(f"[Better Response] Trial {i + 1}, similarity: {similarity}")

        if best_reply[1]:
            logger.warning(f"[Unacceptable] user: {user_id},  {best_reply[0]:.3f} > {SIMILARITY_THRESHOLD}\n  SendMessage: {repr(best_reply[1])}")
            return best_reply[1], best_reply[2]
        else:
            logger.info(f"[ERROR] Failed to generate a suitable response after multiple trials.")
            return "申し訳ありませんが、応答を生成できませんでした。", DIALOGUE_NOT_FINISHED

    def finish_dialogue(self, user_id: str):
        """
        Marks the dialogue as finished in the database.
        """
        logger.info(f"[Finishing Dialogue] user: {user_id}")
        session_id = get_session(user_id).get('session_id', '')
        try:
            post_time = timezone.now()
            ChatHistory.objects.create(
                user_id=user_id,
                speaker="user",
                message="[END]",
                post_time=post_time,
                finished=DIALOGUE_FINISHED,
                session_id=session_id,
            )
            save_dialogue_history(user_id, "user", "[END]", session_id, post_time)  # Save to file
        except Exception as e:
            logger.debug(f"[Bot] Error finishing dialogue for user {user_id}: {e}")

    def reply(self, user_id: str, message: str, remove_thought: bool = False, context_num: int = DEFAULT_CONTEXT_NUM) -> str:
        """
        Handles a user's message, saves it to the database, generates a response, and saves the response.
        """
        logger.info(f"[Receive Message] user: {user_id}\n  message: {repr(message)}")
        session_id = get_session(user_id).get('session_id', '')
        try:
            post_time = timezone.now()
            ChatHistory.objects.create(
                user_id=user_id,
                speaker="user",
                message=message,
                post_time=post_time,
                finished=DIALOGUE_NOT_FINISHED,
                session_id=session_id,
            )
            save_dialogue_history(user_id, "user", message, session_id, post_time)  # Save to file

            history = self._get_history(user_id, context_num)
            response, is_finished = self._generate_response(history, user_id=user_id)

            post_time = timezone.now()
            ChatHistory.objects.create(
                user_id=user_id,
                speaker="assistant",
                message=response,
                post_time=post_time,
                finished=0,
                session_id=session_id,
            )
            save_dialogue_history(user_id, "assistant", response, session_id, post_time)  # Save to file

            if remove_thought:
                response = re.sub(r'\[.*?\]', '', response)

            return response, is_finished
        except Exception as e:
            logger.debug(f"[ERROR] Error processing message from user {user_id}: {e}")
            return "エラーが発生しました。もう一度お試しください。", False


# if __name__ == "__main__":
#     bot = CounselorBot(
#         db_path="chat_history.db",
#         init_message=INIT_MESSAGE,
#         api_key=OPENAI_API_KEY,
#         system_prompt_path="prompt/system_prompt.txt",
#         example_files=[
#             "prompt/case1_0.txt",
#             "prompt/case2_0.txt",
#             "prompt/case3_0.txt",
#             "prompt/case4_0.txt",
#             "prompt/case5_0.txt",
#             "prompt/case6_1.txt",
#         ]
#     )
#     print(bot.start_message("test"))