from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views import View
import stripe
import json
from datetime import datetime, timedelta
from .models import SubscriptionPlan, UserSubscription, APIUsage

from subscriptions.create_checkout import create_checkout
from logger.set_logger import start_logger

logger = start_logger('logger/config/system.yaml')
logger.ddebug("[Execution] subscriptions/views.py")

# Stripe設定
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')


@login_required
def subscription_plans(request):
    """サブスクリプションプラン一覧"""
    username = request.user.username
    plans = SubscriptionPlan.objects.filter(is_active=True)
    
    # only_free_plansがTrueの場合、無料プランのみを表示
    if getattr(settings, 'ONLY_FREE_PLANS', False):
        plans = plans.filter(price=0)
        logger.debug(f"[ページ表示] サブスクリプションプラン一覧（無料プランのみ） UserName: {username} subscriptions/plans.html")
    else:
        logger.debug(f"[ページ表示] サブスクリプションプラン一覧 UserName: {username} subscriptions/plans.html")
    # 各プランに confirm_url を追加（無料プランは除く）
    for plan in plans:
        if plan.price > 0:  # 有料プランのみ
            session = create_checkout(
                product_name=plan.name,
                unit_amount=int(plan.price),  # Stripeはセント単位で価格を設定
                user_id=username,
                tunnel_url='http://127.0.0.1:8080/subscriptions'
            )
            plan.confirm_url = session.url
            logger.debug(f"\t[表示プラン] {plan.name} - ¥{plan.price}/月 - URL: {plan.confirm_url[:60]}")
        else:
            plan.confirm_url = None  # 無料プランはURLなし
            logger.debug(f"\t[表示プラン] {plan.name} - 無料プラン（URL生成なし）")

    # 現在のユーザーのサブスクリプション情報を取得
    current_subscription = None
    try:
        current_subscription = UserSubscription.objects.get(user=request.user)
        logger.debug(f"\t[Subscription Check] User: {current_subscription.user.username}, Status: {current_subscription.status}, Current Period End: {current_subscription.current_period_end}, Now: {timezone.now()}")
    except UserSubscription.DoesNotExist:
        logger.debug(f"\t[Subscription Check] No active subscription for user: {request.user.username}")
        pass
    
    context = {
        'plans': plans,
        'current_subscription': current_subscription,
        'stripe_public_key': getattr(settings, 'STRIPE_PUBLIC_KEY', ''),
    }
    return render(request, 'subscriptions/plans.html', context)


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(View):
    """Stripe Webhookハンドラー"""

    def post(self, request):
        logger.info("[Stripe Webhook] Received POST request")
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        endpoint_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
        
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except ValueError:
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError:
            return HttpResponse(status=400)
        
        # イベントタイプに応じて処理
        logger.debug(f"\t[Stripe Webhook] Event type: {event['type']}")
        if event['type'] == 'checkout.session.completed':
            self.handle_checkout_completed(event['data']['object'])
        else:
            logger.error(f"[Stripe Webhook] Unhandled event type: {event['type']}")
        
        return HttpResponse(status=200)
    

    def handle_checkout_completed(self, session):
        """Checkoutセッション完了時の処理"""
        payment_intent_id = session.get('payment_intent')
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        user_id = payment_intent.metadata.get('user_id')
        plan_name = payment_intent.metadata.get('plan_name')
        logger.debug(f"\t[Payment Succeeded] user_id: {user_id}, plan_name: {plan_name}")

        if user_id and plan_name:
            from django.contrib.auth.models import User
            try:
                user = User.objects.get(username=user_id)
                plan = SubscriptionPlan.objects.get(name=plan_name)

                # 終了日を計算（全プラン共通で1ヶ月後）
                end_date = timezone.now() + timedelta(days=30)
                
                # サブスクリプション情報を更新または作成
                subscription, created = UserSubscription.objects.get_or_create(
                    user=user,
                    defaults={
                        'plan': plan,
                        'status': 'active',
                        'current_period_start': timezone.now(),
                        'current_period_end': end_date,
                        # 'stripe_customer_id': session['customer'],
                        # 'stripe_subscription_id': session['subscription'],
                    }
                )
                
                plan_changed = False
                if not created:
                    old_plan_name = subscription.plan.name
                    subscription.plan = plan
                    subscription.status = 'active'
                    subscription.current_period_start = timezone.now()
                    subscription.current_period_end = end_date
                    # subscription.stripe_customer_id = session['customer']
                    # subscription.stripe_subscription_id = session['subscription']
                    subscription.save()
                    plan_changed = True
                    logger.info(f"[Webhook] Updated existing subscription for user: {user.username}, changed from {old_plan_name} to {plan.name}")
                else:
                    plan_changed = True
                    logger.info(f"[Webhook] Created new subscription for user: {user.username}, plan: {plan.name}")
                
                # プラン変更時はAPI使用量をリセット
                if plan_changed:
                    current_usage = APIUsage.get_or_create_current_usage(user)
                    current_usage.request_count = 0
                    current_usage.save()
                    logger.info(f"[Webhook] Reset API usage for user: {user.username} due to plan change")
                    
                logger.info(f"[Webhook] Successfully processed subscription for user: {user.username}, plan: {plan.name}, end_date: {end_date}, created: {created}")
                    
            except (User.DoesNotExist, SubscriptionPlan.DoesNotExist):
                logger.error(f"\t[Error] User or Plan not found for user_id: {user_id}, plan_name: {plan_name}")
                pass
    

@login_required
def subscription_success(request):
    """サブスクリプション成功ページ"""
    # Stripeセッションからの成功後処理
    session_id = request.GET.get('session_id')
    logger.info(f"[Subscription Success] Accessed by user: {request.user.username}, session_id: {session_id}")
    
    if session_id:
        try:
            # Stripeセッション情報を取得
            session = stripe.checkout.Session.retrieve(session_id)
            logger.info(f"[Subscription Success] Retrieved session: {session_id}")
            
            if session.payment_status == 'paid':
                # 支払い完了後の処理
                payment_intent_id = session.get('payment_intent')
                if payment_intent_id:
                    payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                    user_id = payment_intent.metadata.get('user_id')
                    plan_name = payment_intent.metadata.get('plan_name')
                    
                    logger.info(f"[Subscription Success] Processing payment for user: {user_id}, plan: {plan_name}")
                    
                    if user_id == request.user.username and plan_name:
                        from django.contrib.auth.models import User
                        try:
                            plan = SubscriptionPlan.objects.get(name=plan_name)
                            
                            # 終了日を計算（全プラン共通で1ヶ月後）
                            end_date = timezone.now() + timedelta(days=30)
                            
                            # サブスクリプション情報を更新
                            subscription, created = UserSubscription.objects.get_or_create(
                                user=request.user,
                                defaults={
                                    'plan': plan,
                                    'status': 'active',
                                    'current_period_start': timezone.now(),
                                    'current_period_end': end_date,
                                }
                            )
                            
                            plan_changed = False
                            if not created:
                                # プラン変更があった場合のみ更新
                                if subscription.plan != plan or subscription.current_period_end is None:
                                    old_plan_name = subscription.plan.name
                                    subscription.plan = plan
                                    subscription.status = 'active'
                                    subscription.current_period_start = timezone.now()
                                    subscription.current_period_end = end_date
                                    subscription.save()
                                    plan_changed = True
                                    logger.info(f"[Subscription Success] Updated existing subscription for user: {request.user.username}, changed from {old_plan_name} to {plan.name}")
                                else:
                                    logger.info(f"[Subscription Success] Subscription already up-to-date for user: {request.user.username}")
                            else:
                                plan_changed = True
                                logger.info(f"[Subscription Success] Created new subscription for user: {request.user.username}")
                            
                            # プラン変更時はAPI使用量をリセット
                            if plan_changed:
                                current_usage = APIUsage.get_or_create_current_usage(request.user)
                                current_usage.request_count = 0
                                current_usage.save()
                                logger.info(f"[Subscription Success] Reset API usage for user: {request.user.username} due to plan change")
                            
                            messages.success(request, f'{plan_name}プランへの変更が完了しました。API使用量もリセットされました。')
                            
                        except SubscriptionPlan.DoesNotExist:
                            logger.error(f"[Subscription Success] Plan not found: {plan_name}")
                            messages.error(request, 'プランが見つかりませんでした。')
                            
                    else:
                        logger.error(f"[Subscription Success] User mismatch or missing plan name")
                        messages.error(request, 'ユーザー情報が一致しません。')
                else:
                    logger.error(f"[Subscription Success] No payment_intent in session")
                    messages.error(request, '支払い情報が見つかりませんでした。')
            else:
                logger.warning(f"[Subscription Success] Payment not completed: {session.payment_status}")
                messages.warning(request, '支払いが完了していません。')
                
        except stripe.error.StripeError as e:
            logger.error(f"[Subscription Success] Stripe error: {str(e)}")
            messages.error(request, 'Stripeでエラーが発生しました。')
        except Exception as e:
            logger.error(f"[Subscription Success] Unexpected error: {str(e)}")
            messages.error(request, '予期しないエラーが発生しました。')
    
    return render(request, 'subscriptions/success.html')


@login_required
def api_usage_status(request):
    """API使用状況を表示"""
    logger.debug(f"[ページ表示] API使用状況,  User: {request.user.username} subscriptions/usage_status.html")
    
    try:
        subscription = UserSubscription.objects.get(user=request.user)
        
        # 期限切れチェックと自動更新（無料プランの場合）
        if subscription.current_period_end and subscription.current_period_end < timezone.now():
            if subscription.plan.price == 0:  # 無料プランの場合
                logger.info(f"[API Usage Status] Free plan expired for user: {request.user.username}, resetting usage and extending period")
                # 使用量をリセット
                current_usage = APIUsage.get_or_create_current_usage(request.user)
                current_usage.request_count = 0
                current_usage.save()
                # 期間を更新
                subscription.current_period_start = timezone.now()
                subscription.current_period_end = timezone.now() + timedelta(days=30)
                subscription.save()
        
        usage = APIUsage.get_or_create_current_usage(request.user)
        monthly_limit = subscription.plan.api_requests_per_month
        can_request = usage.can_make_request(num_tabs=1)
    except UserSubscription.DoesNotExist:
        logger.debug(f"\t[API Usage Status]Warning: No subscription found for user: {request.user.username}")
        subscription = None
        usage = APIUsage.get_or_create_current_usage(request.user)
        monthly_limit = 0
        can_request = False
    logger.debug(f"\t[API Usage Status] Subscription: {subscription}, Monthly Limit: {monthly_limit}, Can Request: {can_request}")
    
    # 使用率の計算
    usage_percentage = 0
    is_near_limit = False
    if monthly_limit > 0:
        usage_percentage = round((usage.request_count / monthly_limit) * 100, 1)
        is_near_limit = usage_percentage > 80
    
    # プログレスバーの色を決定
    if usage_percentage < 70:
        progress_color = 'progress-green'
    elif usage_percentage < 90:
        progress_color = 'progress-yellow'
    else:
        progress_color = 'progress-red'
    
    context = {
        'usage': usage,
        'subscription': subscription,
        'monthly_limit': monthly_limit,
        'remaining_requests': max(0, monthly_limit - usage.request_count),
        'can_request': can_request,
        'usage_percentage': usage_percentage,
        'progress_color': progress_color,
        'is_near_limit': is_near_limit,
        # サブスクリプション期間の情報を追加
        'subscription_period_start': subscription.current_period_start if subscription else None,
        'subscription_period_end': subscription.current_period_end if subscription else None,
    }
    
    return render(request, 'subscriptions/usage_status.html', context)


@login_required
def cancel_subscription(request):
    """サブスクリプションキャンセル"""
    if request.method == 'POST':
        try:
            subscription = UserSubscription.objects.get(user=request.user)
            # サーバ側保護: すでに無料プランの場合はキャンセル処理を行わない
            if subscription.plan.price == 0:
                logger.warning(f"[Cancel Subscription] User {request.user.username} attempted to cancel but is already on free plan; action ignored.")
                messages.info(request, '現在のプランは無料プランです。キャンセル操作は不要です。')
                return redirect('subscriptions:plans')

            # 無料プランに戻す
            free_plan = SubscriptionPlan.objects.get(name='無料')
            old_plan_name = subscription.plan.name
            subscription.plan = free_plan
            subscription.status = 'active'
            subscription.stripe_customer_id = ''
            subscription.stripe_subscription_id = ''
            subscription.current_period_start = timezone.now()
            subscription.current_period_end = timezone.now() + timedelta(days=30)  # 無料プランも1ヶ月の期限
            subscription.save()

            # プラン変更時はAPI使用量をリセット
            current_usage = APIUsage.get_or_create_current_usage(request.user)
            current_usage.request_count = 0
            current_usage.save()

            logger.info(f"[Cancel Subscription] User: {request.user.username} cancelled subscription and moved to free plan, API usage reset")
            messages.success(request, 'サブスクリプションをキャンセルし、無料プランに変更しました。API使用量もリセットされました。')
            
        except UserSubscription.DoesNotExist:
            logger.error(f"[Cancel Subscription] No subscription found for user: {request.user.username}")
            messages.error(request, 'サブスクリプションが見つかりません。')
        except SubscriptionPlan.DoesNotExist:
            logger.error(f"[Cancel Subscription] Free plan not found")
            messages.error(request, '無料プランが見つかりません。管理者にお問い合わせください。')
        except Exception as e:
            logger.error(f"[Cancel Subscription] Error cancelling subscription for user {request.user.username}: {str(e)}")
            messages.error(request, 'サブスクリプションのキャンセル中にエラーが発生しました。')
    
    return redirect('subscriptions:plans')
