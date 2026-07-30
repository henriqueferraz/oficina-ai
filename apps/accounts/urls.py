from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.http import require_http_methods

from apps.accounts.models import PerfilUsuario
from apps.accounts.permissions import garantir_papeis_padrao
from apps.core.models import Oficina


class OficinaLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    error = None
    if request.method == "POST":
        from django.contrib.auth.models import User

        nome_oficina = request.POST.get("oficina", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not all([nome_oficina, username, password]):
            error = "Preencha oficina, usuário e senha."
        elif User.objects.filter(username=username).exists():
            error = "Este usuário já existe."
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            oficina = Oficina.objects.create(nome=nome_oficina, email=email)
            papeis = garantir_papeis_padrao(oficina)
            PerfilUsuario.objects.create(
                user=user,
                oficina=oficina,
                papel=papeis["dono"],
            )
            login(request, user)
            return redirect("core:dashboard")

    return render(request, "accounts/register.html", {"error": error})


app_name = "accounts"

urlpatterns = [
    path("entrar/", OficinaLoginView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
    path("cadastrar/", register, name="register"),
]
