from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.accounts.permissions import TODAS_PERMISSOES


class PapelOficina(models.Model):
    """Papel configurável por oficina, com lista de permissões."""

    oficina = models.ForeignKey(
        "core.Oficina",
        on_delete=models.CASCADE,
        related_name="papeis",
    )
    slug = models.SlugField(max_length=50)
    nome = models.CharField(max_length=80)
    eh_administrador = models.BooleanField(default=False)
    permissoes = models.JSONField(default=list, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Papel da oficina"
        verbose_name_plural = "Papéis da oficina"
        constraints = [
            models.UniqueConstraint(
                fields=["oficina", "slug"],
                name="uniq_papel_oficina_slug",
            ),
        ]
        ordering = ["-eh_administrador", "nome"]

    def __str__(self) -> str:
        return f"{self.nome} ({self.oficina_id})"

    def tem_permissao(self, codigo: str) -> bool:
        if self.eh_administrador:
            return True
        return codigo in (self.permissoes or [])

    def normalizar_permissoes(self) -> list[str]:
        if self.eh_administrador:
            return list(TODAS_PERMISSOES)
        return [c for c in (self.permissoes or []) if c in set(TODAS_PERMISSOES)]


class PerfilUsuario(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil",
    )
    oficina = models.ForeignKey(
        "core.Oficina",
        on_delete=models.CASCADE,
        related_name="usuarios",
        null=True,
        blank=True,
    )
    papel = models.ForeignKey(
        PapelOficina,
        on_delete=models.PROTECT,
        related_name="perfis",
        null=True,
        blank=True,
    )
    telefone = models.CharField(max_length=20, blank=True)
    comissao_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Se vazio, usa o percentual padrão da oficina",
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perfil de usuário"
        verbose_name_plural = "Perfis de usuários"

    def __str__(self) -> str:
        return f"{self.user.get_username()} ({self.get_papel_display()})"

    def get_papel_display(self) -> str:
        if self.papel_id:
            return self.papel.nome
        return ""

    def percentual_comissao(self) -> Decimal:
        if self.comissao_percentual is not None:
            return self.comissao_percentual
        if self.oficina_id:
            return self.oficina.comissao_padrao_percentual
        return Decimal("0")

    @property
    def is_dono(self) -> bool:
        return bool(self.papel_id and self.papel.eh_administrador)
