from django.urls import path

from . import views

urlpatterns = [
    path("callback/", views.callback, name="line_callback"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("checkout1/", views.create_checkout_session1, name="checkout_1"),
    path("checkout2/", views.create_checkout_session2, name="checkout_2"),
    path("checkout3/", views.create_checkout_session3, name="checkout_3"),
    path("checkout4/", views.create_checkout_session4, name="checkout_4"),
    path("success/", views.success, name="success"),
    path("cancel/", views.cancel, name="cancel"),
]
