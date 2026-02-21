
def get_openai_response(prompt_text, stream=False, user=None, num_tabs=1, model=settings.RESPONSE_MODEL, count_usage=True): 
    """API使用量制限チェック付きOpenAI API呼び出し"""
    
    # モデル名を抽出（辞書または文字列に対応）
    if isinstance(model, dict):
        model_name = model.get('model', 'gpt-4o-mini')
        api_type = model.get('api', 'openai')
    else:
        model_name = model
        api_type = 'openai'
    
    # API使用量制限をチェック（count_usageがTrueの場合のみ）
    if user and count_usage:
        try:
            usage = APIUsage.get_or_create_current_usage(user)
            if not usage.can_make_request(num_tabs=num_tabs):
                logger.warning(f"API使用量制限に達しました。ユーザー: {user.username}")
                return None
        except Exception as e:
            logger.error(f"API使用量チェックエラー: {e}")
            return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        completion_stream = client.chat.completions.create( 
            model=model_name,
            messages=[
                {"role": "user", "content": prompt_text}
            ],
            timeout=settings.TIMEOUT,
            temperature=settings.TEMPERATURE, 
            stream=stream 
        )
        if stream:
            return completion_stream # ストリームオブジェクトそのものを返す
        else:
            full_response = completion_stream.choices[0].message.content
            
            # API使用量を記録（count_usageがTrueの場合のみ）
            if user and count_usage:
                try:
                    usage = APIUsage.get_or_create_current_usage(user)
                    usage.increment_usage(num_tabs=num_tabs)
                except Exception as e:
                    logger.error(f"API使用量記録エラー: {e}")
            
            if '```' in full_response:
                full_response = full_response.replace('```json', '').replace('```', '').strip()

            return full_response

    except Exception as e:
        print(f"OpenAI API Error: {e}")
        raise # エラーを再送出
    return None # ここには到達しないはず (エラー時はraiseされるため)


def get_gemini_response(prompt_text, stream=False, user=None, num_tabs=1, model=settings.RESPONSE_MODEL, count_usage=True):
    """API使用量制限チェック付きGemini API呼び出し"""

    # モデル名を抽出（辞書または文字列に対応）
    if isinstance(model, dict):
        model_name = model.get('model', 'gemini-pro')
        api_type = model.get('api', 'gemini')
    else:
        model_name = model
        api_type = 'gemini'
    
    # API使用量制限をチェック（count_usageがTrueの場合のみ）
    if user and count_usage:
        try:
            usage = APIUsage.get_or_create_current_usage(user)
            if not usage.can_make_request(num_tabs=num_tabs):
                logger.warning(f"API使用量制限に達しました。ユーザー: {user.username}")
                return None
        except Exception as e:
            logger.error(f"API使用量チェックエラー: {e}")
            return None
    
    # Gemini APIの設定
    genai.configure(api_key=GEMINI_API_KEY)
    
    try:
        # GenerativeModelを作成
        gemini_model = genai.GenerativeModel(model_name)
        
        # 生成設定
        generation_config = {
            'temperature': settings.TEMPERATURE,
        }
        
        # コンテンツを生成
        response = gemini_model.generate_content(
            prompt_text,
            generation_config=generation_config,
            stream=stream
        )
        
        if stream:
            return response  # ストリームオブジェクトそのものを返す
        else:
            full_response = response.text
            
            # API使用量を記録（count_usageがTrueの場合のみ）
            if user and count_usage:
                try:
                    usage = APIUsage.get_or_create_current_usage(user)
                    usage.increment_usage(num_tabs=num_tabs)
                except Exception as e:
                    logger.error(f"API使用量記録エラー: {e}")
            
            # JSONコードブロックの除去
            if '```' in full_response:
                full_response = full_response.replace('```json', '').replace('```', '').strip()
            
            return full_response
    
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        raise  # エラーを再送出
    return None  # ここには到達しないはず (エラー時はraiseされるため)


def send_reply(request, user_id):

    # ユーザー発話の評価を非同期で実施
    evaluation_result = {'score': None, 'reason': None, 'completed': False}
    
    def run_evaluation_async():
        """バックグラウンドで評価を実行"""
        try:
            evaluation_prompt_path = os.path.join(settings.BASE_DIR, 'dialogues', 'prompts', 'prompt_evaluation_utterance.txt')
            logger.info(f"\t[単一発話の評価] prompt path: {evaluation_prompt_path}")
            with open(evaluation_prompt_path, 'r', encoding='utf-8') as f:
                evaluation_prompt_template = f.read()
            
            # 対話履歴を構築（評価用）
            dialogue_history_for_eval = ""
            logs_for_eval = session.logs.all().order_by('timestamp')
            for log in logs_for_eval:
                speaker_label = "クライアント" if log.speaker == 'ai' else "カウンセラー"
                dialogue_history_for_eval += f"{speaker_label}: {log.message}\n"
            
            # プロンプトのプレースホルダーを置換
            evaluation_prompt = evaluation_prompt_template.replace("{{ dialogue_history }}", dialogue_history_for_eval)
            evaluation_prompt = evaluation_prompt.replace("{{ latest_user_utterance }}", user_message_text)
            
            # モデル設定からモデル名を取得
            utterance_eval_model = settings.UTTERANCE_EVAL_MODEL
            if isinstance(utterance_eval_model, dict):
                model_name = utterance_eval_model.get('model', 'gpt-4o-mini')
                api_type = utterance_eval_model.get('api', 'openai')
                logger.info(f'\t[単一発話の評価] model: {model_name} (api: {api_type})')
            else:
                model_name = utterance_eval_model
                api_type = 'openai'
                logger.info(f'\t[単一発話の評価] model: {model_name}')
            
            # API種別に応じて評価を取得（使用量カウントなし）
            if api_type == 'gemini':
                evaluation_response = get_gemini_response(evaluation_prompt, stream=False, user=request.user, num_tabs=1, model=utterance_eval_model, count_usage=False)
            else:
                evaluation_response = get_openai_response(evaluation_prompt, stream=False, user=request.user, num_tabs=1, model=utterance_eval_model, count_usage=False)
            
            if evaluation_response:
                parsed_json = json.loads(evaluation_response)
                evaluation_result['score'] = parsed_json.get('score', 'N/A')
                evaluation_result['reason'] = parsed_json.get('reason', 'N/A')
                logger.info(f'\t[単一発話の評価]\n\t\tScore: {evaluation_result["score"]}\n\t\tReason: {evaluation_result["reason"]}')
            else:
                logger.warning(f'\t[単一発話の評価] API応答が取得できませんでした')
                
        except Exception as e:
            logger.error(f'\t[単一発話の評価] エラー内容：{e}')
        finally:
            evaluation_result['completed'] = True
    
    # 評価を別スレッドで開始
    eval_thread = threading.Thread(target=run_evaluation_async)
    eval_thread.daemon = True
    eval_thread.start()
