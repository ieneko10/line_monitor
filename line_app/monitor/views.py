from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from counseling_linebot.models import Session, ChatHistory
import re

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
    context = {
        "user_id": user_id,
        "logs": logs,
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
    セッションを停止する
    """
    if request.method == "POST":
        try:
            session = Session.objects.get(user_id=user_id)
            session.session_data['counseling_mode'] = False
            session.save()
            return redirect('monitor:session_detail', user_id=user_id)
        except Session.DoesNotExist:
            return redirect('monitor:session_detail', user_id=user_id)
