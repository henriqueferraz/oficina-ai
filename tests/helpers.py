"""Helpers compartilhados pelos testes por fase."""

from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.accounts.models import PerfilUsuario
from apps.accounts.permissions import garantir_papeis_padrao
from apps.core.models import Cliente, Fornecedor, Oficina, Peca, Servico, Veiculo
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemServico


def criar_oficina_com_usuario(username="dono", password="senha123", oficina_nome="Oficina Teste"):
    User = get_user_model()
    user = User.objects.create_user(
        username=username, password=password, email=f"{username}@test.com"
    )
    oficina = Oficina.objects.create(nome=oficina_nome, cidade="São Paulo", uf="SP")
    papeis = garantir_papeis_padrao(oficina)
    PerfilUsuario.objects.create(user=user, oficina=oficina, papel=papeis["dono"])
    return user, oficina


def papel_da_oficina(oficina, slug):
    papeis = garantir_papeis_padrao(oficina)
    return papeis[slug]


def criar_cliente(oficina, nome="Cliente Teste", **kwargs):
    defaults = {"telefone": "11999999999", "documento": "123.456.789-00"}
    defaults.update(kwargs)
    return Cliente.objects.create(oficina=oficina, nome=nome, **defaults)


def criar_veiculo(oficina, cliente, placa="ABC1D23", **kwargs):
    defaults = {"marca": "VW", "modelo": "Gol", "ano": 2020}
    defaults.update(kwargs)
    return Veiculo.objects.create(oficina=oficina, cliente=cliente, placa=placa, **defaults)


def criar_servico(oficina, nome="Funilaria", preco="100.00", **kwargs):
    return Servico.objects.create(oficina=oficina, nome=nome, preco=Decimal(preco), **kwargs)


def criar_peca(oficina, nome="Parachoque", estoque="10", preco="50.00", **kwargs):
    return Peca.objects.create(
        oficina=oficina,
        nome=nome,
        estoque=Decimal(estoque),
        preco=Decimal(preco),
        custo=Decimal(kwargs.pop("custo", "30.00")),
        estoque_minimo=Decimal(kwargs.pop("estoque_minimo", "2")),
        **kwargs,
    )


def criar_fornecedor(oficina, nome="Fornecedor X"):
    return Fornecedor.objects.create(oficina=oficina, nome=nome)


def criar_orcamento(oficina, cliente, veiculo=None, numero=1, **kwargs):
    return Orcamento.objects.create(
        oficina=oficina,
        cliente=cliente,
        veiculo=veiculo,
        numero=numero,
        **kwargs,
    )


def criar_ordem(oficina, cliente, veiculo=None, numero=1, **kwargs):
    return OrdemServico.objects.create(
        oficina=oficina,
        cliente=cliente,
        veiculo=veiculo,
        numero=numero,
        **kwargs,
    )


def png_minima(nome="foto.png"):
    """PNG 1x1 para uploads em testes."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    # PNG 1x1 transparente
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return SimpleUploadedFile(nome, data, content_type="image/png")
