from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.throttles import AuthThrottle

from . import views


class ThrottledRefreshView(TokenRefreshView):
    throttle_classes = [AuthThrottle]


urlpatterns = [
    path("register/", views.RegisterView.as_view()),
    path("login/", views.LoginView.as_view()),
    path("refresh/", ThrottledRefreshView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("logout-all/", views.LogoutAllView.as_view()),
    path("me/", views.MeView.as_view()),
    path("change-password/", views.ChangePasswordView.as_view()),
    path("password-reset/", views.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
]
