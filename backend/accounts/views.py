import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.exceptions import ServiceError
from core.throttles import AuthThrottle

from . import serializers as s

User = get_user_model()
logger = logging.getLogger(__name__)


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def revoke_all_tokens(user):
    """Sign the user out everywhere by blacklisting every refresh token we ever issued to them."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(request=s.RegisterSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = s.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"user": s.public_user(user), **issue_tokens(user)}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(request=s.LoginSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None or not user.is_active:
            # Same message for "no such user" and "wrong password" so accounts cannot be guessed.
            raise ServiceError("Incorrect email or password.", code="invalid_credentials", status_code=401)
        return Response({"user": s.public_user(user), **issue_tokens(user)})


class LogoutView(APIView):
    @extend_schema(request=s.LogoutSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass  # already invalid or expired: nothing to revoke
        return Response({"detail": "Signed out."})


class LogoutAllView(APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        revoke_all_tokens(request.user)
        return Response({"detail": "Signed out of all devices."})


class MeView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(s.public_user(request.user))

    @extend_schema(request=s.ProfileSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        serializer = s.ProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(request.user, field, value)
        request.user.save(update_fields=list(serializer.validated_data) or None)
        return Response(s.public_user(request.user))

    @extend_schema(request=s.DeleteAccountSerializer, responses={204: None})
    def delete(self, request):
        """Delete the account and everything linked to it (needs the password)."""
        serializer = s.DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["password"]):
            raise ServiceError("Password is incorrect.", code="invalid_password", details={"password": ["Password is incorrect."]})
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    throttle_classes = [AuthThrottle]

    @extend_schema(request=s.ChangePasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not request.user.check_password(data["current_password"]):
            raise ServiceError(
                "Current password is incorrect.", code="invalid_password",
                details={"current_password": ["Current password is incorrect."]},
            )
        try:
            validate_password(data["new_password"], request.user)
        except DjangoValidationError as exc:
            raise ServiceError(exc.messages[0], code="weak_password", details={"new_password": exc.messages})
        request.user.set_password(data["new_password"])
        request.user.save()
        revoke_all_tokens(request.user)  # other devices must sign in again with the new password
        return Response({"detail": "Password changed.", **issue_tokens(request.user)})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(request=s.PasswordResetRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(username=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            try:
                send_mail(
                    "Reset your WebPuente password",
                    f"Use this link to choose a new password (valid for one hour):\n\n{link}\n\n"
                    "If you did not ask for this, you can ignore this email.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception:  # noqa: BLE001 - email trouble must not reveal whether the account exists
                logger.exception("Password reset email could not be sent")
        # Always the same answer, whether or not the account exists.
        return Response({"detail": "If an account exists for that email, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(request=s.PasswordResetConfirmSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise ServiceError("This reset link is invalid or has expired.", code="invalid_reset_link")
        try:
            validate_password(data["new_password"], user)
        except DjangoValidationError as exc:
            raise ServiceError(exc.messages[0], code="weak_password", details={"new_password": exc.messages})
        user.set_password(data["new_password"])
        user.save()
        revoke_all_tokens(user)
        return Response({"detail": "Password updated. You can sign in now."})
