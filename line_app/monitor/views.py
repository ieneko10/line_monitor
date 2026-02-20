from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from counseling_linebot.models import Session, ChatHistory
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from logger.set_logger import start_logger
from logger.ansi import * 

# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
logger = start_logger(conf["LOGGER"]["SYSTEM"])

def sample_view(request):
    return render(request, 'sample.html')

@require_POST
def sample_log(request):
    import json
    data = json.loads(request.body)
    if data.get('is_cancel'):
        logger.info("解除ボタンが押された")
    else:
        logger.info("Sample button pressed.")
    return JsonResponse({"ok": True})

@login_required
def monitor(request):
    """
    現在カウンセリング中のセッション一覧を表示
    """
    # counseling_mode=Trueのセッションを取得
    sessions = Session.objects.all()
    active_sessions = []
    
    for session in sessions:
        if session.session_data and session.session_data.get('counseling_mode', False):
            active_sessions.append(session)
    
    context = {
        'sessions': active_sessions,
    }
    return render(request, 'monitor.html', context)


@login_required
def session_detail(request, user_id):
    """
    セッションの対話ログ詳細
    """
    logs = ChatHistory.objects.filter(user_id=user_id).order_by("post_time")
    last_start = ChatHistory.objects.filter(
        user_id=user_id,
        message="[START]",
    ).order_by("post_time").last()
    if last_start:
        logs = logs.filter(post_time__gt=last_start.post_time)
    
    # AI発話の最初の[]を削除
    for log in logs:
        if log.speaker == 'assistant':
            log.message = re.sub(r'^\[[^\]]*\]\s*', '', log.message)
    
    # セッション情報を取得
    try:
        session = Session.objects.get(user_id=user_id)
    except Session.DoesNotExist:
        session = None
    
    context = {
        "user_id": user_id,
        "logs": logs,
        "session": session,
    }
    return render(request, "monitor_detail.html", context)


def login_view(request):
    """
    簡易ログイン画面
    """
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            next_url = request.GET.get("next") or "/"
            return redirect(next_url)
        messages.error(request, "ユーザー名またはパスワードが正しくありません。")

    return render(request, "login.html")


def logout_view(request):
    """
    ログアウト
    """
    if request.method == "POST":
        auth_logout(request)
    return redirect("/")


@login_required
def session_stop(request, user_id):
    """
    セッションのモードを切り替える
    """
    if request.method == "POST":
        try:
            session = Session.objects.get(user_id=user_id)
            # response_modeをトグル（デフォルトは"AI"）
            current_response_mode = session.session_data.get('response_mode', 'AI')
            if current_response_mode == 'AI':
                session.session_data['response_mode'] = 'Human'
                session.session_data['counseling_mode'] = False
            else:
                session.session_data['response_mode'] = 'AI'
                session.session_data['counseling_mode'] = True
            session.save()
            return redirect('monitor:session_detail', user_id=user_id)
        except Session.DoesNotExist:
            return redirect('monitor:session_detail', user_id=user_id)


@login_required
def send_reply(request, user_id):
    """
    モニター画面から返信を送信する
    """
    if request.method == "POST":
        message = request.POST.get('message', '').strip()
        if message:
            from linebot.v3.messaging import (
                MessagingApi,P
                PushMessageRequest,
                TextMessage
            )
            from linebot.v3.messaging import Configuration
            from django.utils import timezone
            
            # メッセージをLINEに送信
            try:
                configuration = Configuration(access_token=settings.MAIN_CONFIG['LINE_ACCESS_TOKEN'])
                with MessagingApi(configuration) as api:
                    api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text=message)]
                        )
                    )
                
                # チャット履歴に保存
                ChatHistory.objects.create(
                    user_id=user_id,
                    speaker='assistant',
                    message=message,
                    post_time=timezone.now()
                )
                
                logger.info(f"[Monitor Reply] Sent message to user {user_id}")
                return JsonResponse({"success": True})
            except Exception as e:
                logger.error(f"[Monitor Reply Error] {str(e)}")
                return JsonResponse({"success": False, "error": str(e)}, status=500)
        
        return JsonResponse({"success": False, "error": "No message provided"}, status=400)
    
    return JsonResponse({"success": False, "error": "Invalid method"}, status=405)
