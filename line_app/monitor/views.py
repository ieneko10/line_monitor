import json
import re

from linebot.v3.messaging.exceptions import ApiException

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from counseling_linebot.models import Session, ChatHistory, ReplyToken
from counseling_linebot.utils.template_message import reply_to_line_user
from counseling_linebot.utils.db_handler import save_dialogue_history

from logger.set_logger import start_logger
from logger.ansi import * 

# ロガーと設定の読み込み
conf = settings.MAIN_CONFIG
logger = start_logger(conf["LOGGER"]["SYSTEM"])

def sample_view(request):
    return render(request, 'sample.html')

@require_POST
def sample_log(request):
    data = json.loads(request.body)
    logger.info(f"Received data: {data}")
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
    # user_idに紐づくChatHistoryを取得
    logs = ChatHistory.objects.filter(user_id=user_id).order_by("post_time")
    last_start = ChatHistory.objects.filter(
        user_id=user_id,
        message="[START]",
    ).order_by("post_time").last()   # 最後の[START]を取得（セッション開始の目印）
    if last_start:
        logs = logs.filter(post_time__gt=last_start.post_time)   # 最後の[START]以降のログに絞る
    
    # 最新のログIDを取得
    user_logs = ChatHistory.objects.filter(user_id=user_id)
    latest_id = (
        user_logs
        .order_by("-id")   # 新しいレコード順（id 降順）に並べる
        .values_list("id", flat=True)    # id 列だけ取り出す（flat=Trueでタプルではなく単一値を返す．flat=Falseの場合：[(10,), (9,), ...]）
        .first()   # 先頭1件（= 最新 id）を取る
        or 0
    )
    
    # AI発話の最初の[]を削除
    for log in logs:
        if log.speaker == 'assistant':
            log.message = re.sub(r'^\[[^\]]*\]\s*', '', log.message)
    
    # セッション情報を取得(返答モードが"AI"か"Human"かを知るため)
    try:
        session = Session.objects.get(user_id=user_id)
    except Session.DoesNotExist:
        session = None
    
    context = {
        "user_id": user_id,
        "logs": logs,
        "session": session,
        "latest_log_id": latest_id,
    }
    return render(request, "monitor_detail.html", context)


@login_required
def chat_history_status(request, user_id):
    user_logs = ChatHistory.objects.filter(user_id=user_id)
    latest_id = (
        user_logs
        .order_by("-id")   # 新しいレコード順（id 降順）に並べる
        .values_list("id", flat=True)    # id 列だけ取り出す（flat=Trueでタプルではなく単一値を返す．flat=Falseの場合：[(10,), (9,), ...]）
        .first()   # 先頭1件（= 最新 id）を取る
        or 0
    )
    # logger.info(f"[Chat History Status] Latest Log ID: {latest_id}")
    return JsonResponse({"latest_id": latest_id})


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


@require_POST
@login_required
def session_stop(request, user_id):
    """
    セッションのモードを切り替える
    """
    data = json.loads(request.body)
    user_id = data.get('user_id')
    response_mode = 'Human' if data.get('human') else 'AI'
    logger.info(f"[Change Mode] User: {user_id}, New Mode: {response_mode}")
    try:
        session = Session.objects.get(user_id=user_id)
        session.session_data['response_mode'] = response_mode
        session.save()
        return redirect('monitor:session_detail', user_id=user_id)
    except Session.DoesNotExist:
        return redirect('monitor:session_detail', user_id=user_id)


@login_required
@require_POST
def send_reply(request, user_id):
    """
    モニター画面から返信を送信する
    """
    message = request.POST.get('message', '').strip()
    session = Session.objects.filter(user_id=user_id).first()
    session_id = session.session_data.get('session_id', '') if session and session.session_data else ''
    logger.info(f"[Monitor Reply] User: {user_id}, Message: {message}")
    
    reply_token = ReplyToken.objects.filter(user_id=user_id).order_by("-created_at").values_list("token", flat=True).first()
    logger.info(f"[Reply Token] {reply_token}")
    try:
        reply_to_line_user(reply_token, message)
        post_time = timezone.now()
        ChatHistory.objects.create(
            user_id=user_id,
            speaker="counselor",
            message=message,
            post_time=post_time,
            finished=0,
            session_id=session_id,
        )
        save_dialogue_history(user_id, 'counselor', message, session_id, post_time)
        
    except ApiException as e:
        logger.error(f"Failed to send reply: {e}")
    
    except Exception as e:
        logger.error(f'??? Unexpected error')
    
    return redirect('monitor:session_detail', user_id=user_id)