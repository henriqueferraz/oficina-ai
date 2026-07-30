from decimal import Decimal

from django.db import models
from django.db.models import Sum


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Oficina(TimeStampedModel):
    nome = models.CharField(max_length=150)
    cnpj = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    cep = models.CharField(max_length=9, blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    logo = models.ImageField(upload_to="oficinas/logos/%Y/%m/", blank=True, null=True)
    ativa = models.BooleanField(default=True)
    pix_chave = models.CharField(
        max_length=120,
        blank=True,
        help_text="Chave Pix (CPF, CNPJ, e-mail, telefone ou aleatória)",
    )
    pix_nome = models.CharField(
        max_length=25,
        blank=True,
        help_text="Nome do recebedor no Pix (máx. 25 caracteres)",
    )
    comissao_padrao_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text="Percentual padrão de comissão sobre OS entregues",
    )

    class Meta:
        verbose_name = "Oficina"
        verbose_name_plural = "Oficinas"

    def __str__(self) -> str:
        return self.nome


class Cliente(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="clientes")
    nome = models.CharField(max_length=150)
    documento = models.CharField(max_length=18, blank=True, help_text="CPF ou CNPJ")
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    endereco = models.CharField(max_length=255, blank=True)
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["oficina", "nome"]),
            models.Index(fields=["oficina", "telefone"]),
        ]

    def __str__(self) -> str:
        return self.nome


class Veiculo(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="veiculos")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="veiculos")
    placa = models.CharField(max_length=10)
    marca = models.CharField(max_length=50, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    ano = models.PositiveIntegerField(null=True, blank=True)
    cor = models.CharField(max_length=40, blank=True)
    km = models.PositiveIntegerField(null=True, blank=True)
    chassi = models.CharField(max_length=30, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["placa"]
        unique_together = [("oficina", "placa")]
        indexes = [models.Index(fields=["oficina", "placa"])]

    def __str__(self) -> str:
        return f"{self.placa} — {self.marca} {self.modelo}".strip()


class Fornecedor(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="fornecedores")
    nome = models.CharField(max_length=150)
    documento = models.CharField(max_length=18, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Servico(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="servicos")
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    preco = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tempo_estimado_min = models.PositiveIntegerField(default=60)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Serviço"
        verbose_name_plural = "Serviços"

    def __str__(self) -> str:
        return self.nome


class Peca(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="pecas")
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pecas",
    )
    codigo = models.CharField(max_length=50, blank=True)
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    custo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    preco = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estoque = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estoque_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unidade = models.CharField(max_length=10, default="UN")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Peça"
        verbose_name_plural = "Peças"
        indexes = [models.Index(fields=["oficina", "codigo"])]

    def __str__(self) -> str:
        return self.nome

    @property
    def estoque_baixo(self) -> bool:
        return self.estoque <= self.estoque_minimo


class Compra(TimeStampedModel):
    oficina = models.ForeignKey(Oficina, on_delete=models.CASCADE, related_name="compras")
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compras",
    )
    numero = models.PositiveIntegerField()
    data = models.DateField()
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["-data", "-numero"]
        unique_together = [("oficina", "numero")]
        verbose_name = "Compra"
        verbose_name_plural = "Compras"

    def __str__(self) -> str:
        return f"Compra #{self.numero}"

    @property
    def total(self) -> Decimal:
        total = self.itens.aggregate(s=Sum("total"))["s"]
        return total or Decimal("0")


class CompraItem(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="itens")
    peca = models.ForeignKey(Peca, on_delete=models.PROTECT, related_name="compras_itens")
    quantidade = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total = self.quantidade * self.custo_unitario
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.peca} x {self.quantidade}"
