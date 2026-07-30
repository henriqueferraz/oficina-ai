from django.db import models

from apps.core.models import TimeStampedModel


class Lancamento(TimeStampedModel):
    class Tipo(models.TextChoices):
        RECEITA = "receita", "Receita"
        DESPESA = "despesa", "Despesa"

    class Forma(models.TextChoices):
        DINHEIRO = "dinheiro", "Dinheiro"
        PIX = "pix", "Pix"
        CARTAO = "cartao", "Cartão"
        BOLETO = "boleto", "Boleto"
        TRANSFERENCIA = "transferencia", "Transferência"
        OUTRO = "outro", "Outro"

    oficina = models.ForeignKey(
        "core.Oficina", on_delete=models.CASCADE, related_name="lancamentos"
    )
    ordem = models.ForeignKey(
        "ordens.OrdemServico",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lancamentos",
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    forma = models.CharField(max_length=20, choices=Forma.choices, default=Forma.PIX)
    data = models.DateField()
    pago = models.BooleanField(default=True)

    class Meta:
        ordering = ["-data", "-criado_em"]
        verbose_name = "Lançamento"
        verbose_name_plural = "Lançamentos"

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} — {self.descricao} ({self.valor})"
