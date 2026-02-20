from django.contrib import admin
from .models import Session, Setting, ChatHistory, ReplyToken
from django.contrib import admin
from .models import Session, Setting, ChatHistory, ReplyToken


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'flag', 'time', 'get_counseling_mode')
    search_fields = ('user_id',)
    readonly_fields = ('user_id',)
    list_per_page = 50
    
    def get_counseling_mode(self, obj):
        return obj.session_data.get('counseling_mode', False)
    get_counseling_mode.short_description = 'カウンセリング中'
    get_counseling_mode.boolean = True  # チェックマークで表示


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key',)


@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'speaker', 'short_message', 'post_time', 'finished', 'session_id')
    list_filter = ('speaker', 'finished', 'post_time')
    search_fields = ('user_id', 'session_id', 'message')
    readonly_fields = ('post_time',)
    ordering = ('-post_time',)
    date_hierarchy = 'post_time'  # 日付でのナビゲーション
    
    def short_message(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    short_message.short_description = 'メッセージ'


@admin.register(ReplyToken)
class ReplyTokenAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'token', 'created_at')
    search_fields = ('user_id', 'token')
    ordering = ('-created_at',)