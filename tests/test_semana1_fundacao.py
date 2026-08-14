"""
Semana 1 — Fundação
Auth, modelos básicos, painel, OS/orçamento/financeiro mínimos.
"""

from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.financeiro.models import Lancamento
from apps.orcamentos.models import OrcamentoItem
from apps.ordens.models import OrdemItem, OrdemServico
from tests.helpers import (
    criar_cliente,
    criar_oficina_com_usuario,
    criar_orcamento,
    criar_ordem,
    criar_veiculo,
)


class Semana1AuthTests(TestCase):
    def test_cadastro_cria_oficina_e_perfil_dono(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "oficina": "Funilaria Nova",
                "username": "novo_dono",
                "email": "dono@teste.com",
                "password": "senhaforte123",
            },
        )
        self.assertEqual(response.status_code, 302)
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(username="novo_dono")
        self.assertEqual(user.perfil.oficina.nome, "Funilaria Nova")
        self.assertEqual(user.perfil.papel.slug, "dono")
        self.assertTrue(user.perfil.papel.eh_administrador)

    def test_login_redireciona_ao_painel(self):
        criar_oficina_com_usuario("login_user", "senha123")
        ok = self.client.login(username="login_user", password="senha123")
        self.assertTrue(ok)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)


class Semana1ModelosTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.veiculo = criar_veiculo(self.oficina, self.cliente)

    def test_placa_unica_por_oficina(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            criar_veiculo(self.oficina, self.cliente, placa="ABC1D23")

    def test_orcamento_total_com_desconto(self):
        orc = criar_orcamento(self.oficina, self.cliente, self.veiculo, desconto=Decimal("10"))
        OrcamentoItem.objects.create(
            orcamento=orc,
            tipo="servico",
            descricao="Pintura",
            quantidade=1,
            valor_unitario=Decimal("100"),
        )
        self.assertEqual(orc.total, Decimal("90"))

    def test_ordem_total_e_status(self):
        ordem = criar_ordem(self.oficina, self.cliente, self.veiculo)
        OrdemItem.objects.create(
            ordem=ordem,
            tipo="servico",
            descricao="Funilaria",
            quantidade=2,
            valor_unitario=Decimal("50"),
        )
        self.assertEqual(ordem.total, Decimal("100"))
        self.assertEqual(ordem.status, OrdemServico.Status.ABERTA)


class Semana1PainelEFluxosTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.veiculo = criar_veiculo(self.oficina, self.cliente)
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_dashboard_ok(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Painel")

    def test_criar_cliente(self):
        response = self.client.post(
            reverse("core:cliente_create"),
            {
                "nome": "Ana",
                "telefone": "11888888888",
                "documento": "",
                "email": "",
                "endereco": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        # Cadastros são normalizados para maiúsculas (apps.core.validators.maiusculo)
        self.assertTrue(self.oficina.clientes.filter(nome="ANA").exists())

    def test_criar_ordem_via_ui(self):
        response = self.client.post(
            reverse("ordens:criar"),
            {
                "cliente": self.cliente.pk,
                "veiculo": self.veiculo.pk,
                "prioridade": "alta",
                "diagnostico": "Batida",
                "observacoes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        ordem = OrdemServico.objects.get(oficina=self.oficina, numero=1)
        self.assertEqual(ordem.prioridade, "alta")

    def test_criar_orcamento_e_item(self):
        response = self.client.post(
            reverse("orcamentos:criar"),
            {"cliente": self.cliente.pk, "veiculo": self.veiculo.pk, "observacoes": "ok"},
        )
        self.assertEqual(response.status_code, 302)
        orc = self.oficina.orcamentos.get(numero=1)
        self.client.post(
            reverse("orcamentos:adicionar_item", args=[orc.pk]),
            {
                "tipo": "servico",
                "descricao": "Polimento",
                "quantidade": "1",
                "valor_unitario": "80",
            },
        )
        self.assertEqual(orc.itens.count(), 1)

    def test_lancamento_financeiro(self):
        from datetime import date

        response = self.client.post(
            reverse("financeiro:criar"),
            {
                "tipo": "receita",
                "descricao": "Entrada",
                "valor": "150.00",
                "forma": "pix",
                "data": date.today().isoformat(),
                "pago": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Lancamento.objects.filter(oficina=self.oficina).count(), 1)

    def test_agente_painel_acessivel(self):
        response = self.client.get(reverse("agentes:painel"))
        self.assertEqual(response.status_code, 200)
