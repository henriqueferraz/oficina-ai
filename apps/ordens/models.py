from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum

from apps.core.models import TimeStampedModel
from apps.core.video import video_embed_url as embed_url_from

CHECKLIST_PADRAO = [
    "Faróis / lanternas",
    "Espelhos",
    "Pneus / estepe",
    "Documentos do veículo",
    "Objetos pessoais no interior",
    "Nível de combustível",
]

MAX_FOTOS_ORDEM = 10


class OrdemServico(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        EM_ANDAMENTO = "em_andamento", "Em andamento"
        AGUARDANDO_PECA = "aguardando_peca", "Aguardando peça"
        AGUARDANDO_APROVACAO = "aguardando_aprovacao", "Aguardando aprovação"
        PRONTA = "pronta", "Pronta"
        ENTREGUE = "entregue", "Entregue"
        CANCELADA = "cancelada", "Cancelada"

    class Prioridade(models.TextChoices):
        BAIXA = "baixa", "Baixa"
        NORMAL = "normal", "Normal"
        ALTA = "alta", "Alta"
        URGENTE = "urgente", "Urgente"

    class Pagamento(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PARCIAL = "parcial", "Parcial"
        PAGO = "pago", "Pago"

    oficina = models.ForeignKey("core.Oficina", on_delete=models.CASCADE, related_name="ordens")
    cliente = models.ForeignKey("core.Cliente", on_delete=models.PROTECT, related_name="ordens")
    veiculo = models.ForeignKey(
        "core.Veiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordens",
    )
    orcamento = models.ForeignKey(
        "orcamentos.Orcamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordens",
    )
    numero = models.PositiveIntegerField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ABERTA)
    prioridade = models.CharField(
        max_length=10, choices=Prioridade.choices, default=Prioridade.NORMAL
    )
    pagamento_status = models.CharField(
        max_length=10, choices=Pagamento.choices, default=Pagamento.PENDENTE
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ordens_responsavel",
    )
    previsao_entrega = models.DateTimeField(null=True, blank=True)
    entregue_em = models.DateTimeField(null=True, blank=True)
    diagnostico = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    token_publico = models.CharField(max_length=64, blank=True, db_index=True)
    estoque_baixado = models.BooleanField(
        default=False,
        help_text="Indica se as peças desta OS já foram debitadas do estoque.",
    )
    video_url = models.URLField(
        blank=True,
        default="",
        help_text="Link do vídeo (YouTube, Vimeo ou outro stream).",
    )
    video_titulo = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["-criado_em"]
        unique_together = [("oficina", "numero")]
        verbose_name = "Ordem de serviço"
        verbose_name_plural = "Ordens de serviço"
        indexes = [
            models.Index(fields=["oficina", "status"]),
            models.Index(fields=["oficina", "prioridade"]),
        ]

    def __str__(self) -> str:
        return f"OS #{self.numero} — {self.cliente}"

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
        # Prefetch: soma em memória (evita N+1 com .aggregate)
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
        return max(MAX_FOTOS_ORDEM - self.fotos.count(), 0)

    @property
    def video_embed_url(self) -> str:
        return embed_url_from(self.video_url)


class OrdemItem(models.Model):
    class Tipo(models.TextChoices):
        SERVICO = "servico", "Serviço"
        PECA = "peca", "Peça"

    ordem = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="itens")
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


class ChecklistItem(models.Model):
    class Momento(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"

    ordem = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="checklist")
    momento = models.CharField(max_length=10, choices=Momento.choices, default=Momento.ENTRADA)
    item = models.CharField(max_length=120)
    ok = models.BooleanField(default=False)
    observacao = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.item


class OrdemFoto(TimeStampedModel):
    ordem = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name="fotos")
    imagem = models.ImageField(upload_to="ordens/%Y/%m/")
    legenda = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Foto da OS"
        verbose_name_plural = "Fotos da OS"

    def __str__(self) -> str:
        return self.legenda or f"Foto OS #{self.ordem.numero}"

    def clean(self):
        if self.ordem_id and not self.pk:
            if self.ordem.fotos.count() >= MAX_FOTOS_ORDEM:
                raise ValidationError(f"Limite de {MAX_FOTOS_ORDEM} fotos por OS.")

    def delete(self, *args, **kwargs):
        storage = self.imagem.storage
        name = self.imagem.name
        super().delete(*args, **kwargs)
        if name:
            storage.delete(name)
