from django.shortcuts import render
from counseling_linebot.models import Session

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
