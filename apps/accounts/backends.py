"""Backends de autenticação."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    """Login com usuário ignorando maiúsculas/minúsculas (Maria == maria)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        field = UserModel.USERNAME_FIELD
        try:
            user = UserModel._default_manager.get(**{f"{field}__iexact": username})
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            user = (
                UserModel._default_manager.filter(**{f"{field}__iexact": username})
                .order_by("pk")
                .first()
            )
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
