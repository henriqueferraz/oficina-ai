"""
Semana 2 — Operação do dia a dia
CRUD veículos/catálogo/fornecedores, compras, baixa estoque,
checklist, conversão orçamento→OS, PDF, CSV, seed.
"""

from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Compra, Fornecedor, Peca, Servico, Veiculo
from apps.core.services import baixar_estoque_ordem, registrar_compra
from apps.orcamentos.models import Orcamento, OrcamentoItem
from apps.ordens.models import ChecklistItem, OrdemItem, OrdemServico
from tests.helpers import (
    criar_cliente,
    criar_fornecedor,
    criar_oficina_com_usuario,
    criar_orcamento,
    criar_ordem,
    criar_peca,
    criar_servico,
    criar_veiculo,
)


class Semana2CrudTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_criar_e_editar_veiculo(self):
        r = self.client.post(
            reverse("core:veiculo_create"),
            {
                "cliente": self.cliente.pk,
                "placa": "xyz9k88",
                "marca": "Fiat",
                "modelo": "Argo",
                "ano": "2022",
                "cor": "Branco",
                "km": "10000",
                "chassi": "",
                "observacoes": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        v = Veiculo.objects.get(placa="XYZ9K88")
        r = self.client.post(
            reverse("core:veiculo_edit", args=[v.pk]),
            {
                "cliente": self.cliente.pk,
                "placa": "XYZ9K88",
                "marca": "Fiat",
                "modelo": "Argo Trekking",
                "ano": "2022",
                "cor": "Branco",
                "km": "12000",
                "chassi": "",
                "observacoes": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.modelo, "Argo Trekking")

    def test_criar_servico_e_peca(self):
        self.client.post(
            reverse("core:servico_create"),
            {"nome": "Pintura porta", "descricao": "", "preco": "500", "tempo_estimado_min": "120"},
        )
        self.assertTrue(Servico.objects.filter(oficina=self.oficina, nome="Pintura porta").exists())

        self.client.post(
            reverse("core:peca_create"),
            {
                "codigo": "P1",
                "nome": "Retrovisor",
                "descricao": "",
                "fornecedor": "",
                "custo": "40",
                "preco": "80",
                "estoque": "5",
                "estoque_minimo": "1",
                "unidade": "UN",
            },
        )
        self.assertTrue(Peca.objects.filter(oficina=self.oficina, nome="Retrovisor").exists())

    def test_fornecedor_crud(self):
        self.client.post(
            reverse("core:fornecedor_create"),
            {"nome": "Peças Brasil", "documento": "", "telefone": "113333", "email": ""},
        )
        f = Fornecedor.objects.get(oficina=self.oficina, nome="Peças Brasil")
        self.client.post(
            reverse("core:fornecedor_edit", args=[f.pk]),
            {
                "nome": "Peças Brasil Ltda",
                "documento": "11.111.111/0001-11",
                "telefone": "113333",
                "email": "",
                "ativo": "on",
            },
        )
        f.refresh_from_db()
        self.assertEqual(f.nome, "Peças Brasil Ltda")


class Semana2EstoqueTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.fornecedor = criar_fornecedor(self.oficina)
        self.peca = criar_peca(self.oficina, estoque="5")
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_compra_entra_estoque(self):
        compra = registrar_compra(
            oficina=self.oficina,
            fornecedor=self.fornecedor,
            data=date.today(),
            observacoes="",
            itens=[
                {
                    "peca_id": self.peca.pk,
                    "quantidade": Decimal("3"),
                    "custo_unitario": Decimal("25"),
                }
            ],
        )
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.estoque, Decimal("8"))
        self.assertEqual(compra.numero, 1)

    def test_compra_via_ui(self):
        r = self.client.post(
            reverse("core:compra_create"),
            {
                "peca": self.peca.pk,
                "fornecedor": self.fornecedor.pk,
                "quantidade": "2",
                "custo_unitario": "30",
                "data": date.today().isoformat(),
                "observacoes": "teste",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.estoque, Decimal("7"))
        self.assertEqual(Compra.objects.filter(oficina=self.oficina).count(), 1)

    def test_baixa_estoque_ao_marcar_pronta(self):
        ordem = criar_ordem(self.oficina, self.cliente)
        OrdemItem.objects.create(
            ordem=ordem,
            tipo=OrdemItem.Tipo.PECA,
            descricao=self.peca.nome,
            quantidade=Decimal("2"),
            valor_unitario=self.peca.preco,
            peca=self.peca,
        )
        r = self.client.post(
            reverse("ordens:atualizar_status", args=[ordem.pk]),
            {"status": OrdemServico.Status.PRONTA},
        )
        self.assertEqual(r.status_code, 302)
        self.peca.refresh_from_db()
        ordem.refresh_from_db()
        self.assertEqual(self.peca.estoque, Decimal("3"))
        self.assertTrue(ordem.estoque_baixado)

    def test_baixa_nao_duplica(self):
        ordem = criar_ordem(self.oficina, self.cliente, status=OrdemServico.Status.PRONTA)
        OrdemItem.objects.create(
            ordem=ordem,
            tipo=OrdemItem.Tipo.PECA,
            descricao=self.peca.nome,
            quantidade=Decimal("1"),
            valor_unitario=self.peca.preco,
            peca=self.peca,
        )
        baixar_estoque_ordem(ordem)
        baixar_estoque_ordem(ordem)
        self.peca.refresh_from_db()
        self.assertEqual(self.peca.estoque, Decimal("4"))


class Semana2OsOrcamentoTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.veiculo = criar_veiculo(self.oficina, self.cliente)
        self.servico = criar_servico(self.oficina)
        self.peca = criar_peca(self.oficina)
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_checklist_padrao_na_criacao_os(self):
        self.client.post(
            reverse("ordens:criar"),
            {
                "cliente": self.cliente.pk,
                "veiculo": self.veiculo.pk,
                "prioridade": "normal",
                "diagnostico": "",
                "observacoes": "",
            },
        )
        ordem = OrdemServico.objects.get(oficina=self.oficina)
        self.assertGreaterEqual(ordem.checklist.count(), 6)

    def test_checklist_toggle(self):
        ordem = criar_ordem(self.oficina, self.cliente)
        item = ChecklistItem.objects.create(ordem=ordem, momento="entrada", item="Faróis", ok=False)
        self.client.post(reverse("ordens:checklist_toggle", args=[ordem.pk, item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.ok)

    def test_converter_orcamento_em_os(self):
        orc = criar_orcamento(self.oficina, self.cliente, self.veiculo)
        OrcamentoItem.objects.create(
            orcamento=orc,
            tipo="servico",
            descricao=self.servico.nome,
            quantidade=1,
            valor_unitario=self.servico.preco,
            servico=self.servico,
        )
        OrcamentoItem.objects.create(
            orcamento=orc,
            tipo="peca",
            descricao=self.peca.nome,
            quantidade=1,
            valor_unitario=self.peca.preco,
            peca=self.peca,
        )
        r = self.client.post(reverse("orcamentos:converter_os", args=[orc.pk]))
        self.assertEqual(r.status_code, 302)
        orc.refresh_from_db()
        self.assertEqual(orc.status, Orcamento.Status.CONVERTIDO)
        ordem = orc.ordens.first()
        self.assertIsNotNone(ordem)
        self.assertEqual(ordem.itens.count(), 2)

    def test_pdf_ordem_e_orcamento(self):
        ordem = criar_ordem(self.oficina, self.cliente, self.veiculo)
        orc = criar_orcamento(self.oficina, self.cliente, self.veiculo)
        r_os = self.client.get(reverse("ordens:pdf", args=[ordem.pk]))
        r_orc = self.client.get(reverse("orcamentos:pdf", args=[orc.pk]))
        self.assertEqual(r_os.status_code, 200)
        self.assertEqual(r_os["Content-Type"], "application/pdf")
        self.assertEqual(r_orc.status_code, 200)
        self.assertEqual(r_orc["Content-Type"], "application/pdf")


class Semana2ImportCsvESeedTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_importar_csv_clientes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_data = b"nome,telefone,documento\nJoao,11999,111\nMaria,11888,222\n"
        arquivo = SimpleUploadedFile("clientes.csv", csv_data, content_type="text/csv")
        r = self.client.post(
            reverse("core:importar_csv"),
            {"tipo": "clientes", "arquivo": arquivo},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.oficina.clientes.filter(nome="Joao").count(), 1)
        self.assertEqual(self.oficina.clientes.filter(nome="Maria").count(), 1)

    def test_seed_demo(self):
        out = StringIO()
        call_command("seed_demo", username="seeduser", password="seedpass", stdout=out)
        self.assertIn("Seed OK", out.getvalue())
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.get(username="seeduser")
        self.assertTrue(user.perfil.oficina.clientes.exists())
        self.assertTrue(user.perfil.oficina.pecas.exists())
