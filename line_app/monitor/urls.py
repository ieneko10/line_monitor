from django.urls import path
from . import views

app_name = 'monitor'

urlpatterns = [
    path('', views.monitor, name='monitor'),
    path('sessions/<str:user_id>/', views.session_detail, name='session_detail'),
    path('session/stop/<str:user_id>/', views.session_stop, name='session_stop'),
    path('session/reply/<str:user_id>/', views.send_reply, name='send_reply'),
    path('sample/', views.sample_view, name='sample'),
    path('sample/log/', views.sample_log, name='sample_log'),
]
