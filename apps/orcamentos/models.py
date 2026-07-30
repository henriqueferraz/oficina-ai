import re
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.core.models import TimeStampedModel

MAX_FOTOS_ORCAMENTO = 10


class Orcamento(TimeStampedModel):
    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        ENVIADO = "enviado", "Enviado"
        APROVADO = "aprovado", "Aprovado"
        RECUSADO = "recusado", "Recusado"
        CONVERTIDO = "convertido", "Convertido em OS"
        CANCELADO = "cancelado", "Cancelado"

    oficina = models.ForeignKey("core.Oficina", on_delete=models.CASCADE, related_name="orcamentos")
    cliente = models.ForeignKey("core.Cliente", on_delete=models.PROTECT, related_name="orcamentos")
    veiculo = models.ForeignKey(
        "core.Veiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orcamentos",
    )
    numero = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    validade = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gerado_por_ia = models.BooleanField(default=False)
    token_publico = models.CharField(max_length=64, blank=True, db_index=True)
    video_url = models.URLField(
        blank=True,
        help_text="Link do vídeo (YouTube, Vimeo ou outro stream).",
    )
    video_titulo = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        unique_together = [("oficina", "numero")]
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    def __str__(self) -> str:
        return f"Orçamento #{self.numero} — {self.cliente}"

    def save(self, *args, **kwargs):
        if not self.token_publico:
            from apps.core.tokens import gerar_token

            self.token_publico = gerar_token()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "token_publico"}
        super().save(*args, **kwargs)

    @property
    def subtotal(self) -> Decimal:
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "itens" in cache:
            return sum((i.total for i in self.itens.all()), Decimal("0"))
        total = self.itens.aggregate(s=Sum("total"))["s"]
        return total or Decimal("0")

    @property
    def total(self) -> Decimal:
        return max(self.subtotal - self.desconto, Decimal("0"))

    @property
    def fotos_restantes(self) -> int:
        return max(MAX_FOTOS_ORCAMENTO - self.fotos.count(), 0)

    @property
    def video_embed_url(self) -> str:
        """URL de embed para YouTube/Vimeo; vazio se for link genérico."""
        if not self.video_url:
            return ""
        url = self.video_url.strip()
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower().removeprefix("www.")

        if host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
            qs = parse_qs(parsed.query)
            vid = qs.get("v", [None])[0]
            if not vid and parsed.path.startswith("/embed/"):
                vid = parsed.path.split("/embed/")[-1].split("/")[0]
            if not vid and parsed.path.startswith("/shorts/"):
                vid = parsed.path.split("/shorts/")[-1].split("/")[0]
            if vid:
                return f"https://www.youtube.com/embed/{vid}"
        if host == "youtu.be":
            vid = parsed.path.strip("/").split("/")[0]
            if vid:
                return f"https://www.youtube.com/embed/{vid}"
        if host in {"vimeo.com", "player.vimeo.com"}:
            match = re.search(r"/(\d+)", parsed.path)
            if match:
                return f"https://player.vimeo.com/video/{match.group(1)}"
        return ""


class OrcamentoItem(models.Model):
    class Tipo(models.TextChoices):
        SERVICO = "servico", "Serviço"
        PECA = "peca", "Peça"

    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name="itens")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(max_length=200)
    quantidade = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    servico = models.ForeignKey("core.Servico", on_delete=models.SET_NULL, null=True, blank=True)
    peca = models.ForeignKey("core.Peca", on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        self.total = self.quantidade * self.valor_unitario
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.descricao


class OrcamentoFoto(TimeStampedModel):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name="fotos")
    imagem = models.ImageField(upload_to="orcamentos/%Y/%m/")
    legenda = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Foto do orçamento"
        verbose_name_plural = "Fotos do orçamento"

    def __str__(self) -> str:
        return self.legenda or f"Foto orçamento #{self.orcamento.numero}"

    def clean(self):
        if self.orcamento_id and not self.pk:
            if self.orcamento.fotos.count() >= MAX_FOTOS_ORCAMENTO:
                raise ValidationError(f"Limite de {MAX_FOTOS_ORCAMENTO} fotos por orçamento.")

    def delete(self, *args, **kwargs):
        storage = self.imagem.storage
        name = self.imagem.name
        super().delete(*args, **kwargs)
        if name:
            storage.delete(name)
