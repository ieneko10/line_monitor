from django.urls import path
from . import views

app_name = 'monitor'

urlpatterns = [
    path('', views.monitor, name='monitor'),
    path('sessions/<str:user_id>/', views.session_detail, name='session_detail'),
]
