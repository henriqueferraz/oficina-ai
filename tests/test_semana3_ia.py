"""
Semana 3 — IA que age
Tools do agente, busca NL no painel e resumo diário via Celery.
"""

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from agents.assistente import executar_tool
from apps.agentes.tasks import enviar_resumo_diario
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemServico
from tests.helpers import (
    criar_cliente,
    criar_oficina_com_usuario,
    criar_ordem,
    criar_peca,
    criar_servico,
    criar_veiculo,
)


class Semana3IaTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina, nome="João Silva")
        self.veiculo = criar_veiculo(self.oficina, self.cliente, placa="ABC1D23")
        self.servico = criar_servico(self.oficina, nome="Funilaria", preco="150.00")
        self.peca = criar_peca(self.oficina, nome="Parachoque", preco="80.00")
        self.ordem = criar_ordem(
            self.oficina,
            self.cliente,
            veiculo=self.veiculo,
            numero=1,
            diagnostico="Batida leve no para-choque",
        )
        self.client.login(username="dono", password="senha123")

    def test_tool_criar_orcamento_por_diagnostico(self):
        """Tool do agente gera rascunho de orçamento a partir do diagnóstico."""
        result = executar_tool(
            self.oficina,
            "criar_orcamento_rascunho",
            {
                "cliente_id": self.cliente.id,
                "veiculo_id": self.veiculo.id,
                "diagnostico": "Troca de parachoque e funilaria",
                "itens": [
                    {"tipo": "servico", "termo": "Funilaria", "quantidade": 1},
                    {"tipo": "peca", "termo": "Parachoque", "quantidade": 1},
                    {"tipo": "peca", "termo": "ItemInexistenteXYZ", "quantidade": 1},
                ],
            },
        )
        self.assertNotIn("erro", result)
        self.assertTrue(result["gerado_por_ia"])
        self.assertEqual(result["status"], Orcamento.Status.RASCUNHO)
        self.assertEqual(len(result["itens_criados"]), 2)
        self.assertTrue(any("ItemInexistenteXYZ" in a for a in result["avisos"]))

        orc = Orcamento.objects.get(pk=result["id"])
        self.assertTrue(orc.gerado_por_ia)
        self.assertEqual(orc.status, Orcamento.Status.RASCUNHO)
        self.assertEqual(orc.itens.count(), 2)
        self.assertIn("Troca de parachoque", orc.observacoes)

    def test_tool_atualizar_status_os_com_confirmacao(self):
        """Tool atualiza status da OS somente após confirmação."""
        preview = executar_tool(
            self.oficina,
            "atualizar_status_os",
            {"numero": 1, "novo_status": OrdemServico.Status.EM_ANDAMENTO},
        )
        self.assertTrue(preview["precisa_confirmacao"])
        self.ordem.refresh_from_db()
        self.assertEqual(self.ordem.status, OrdemServico.Status.ABERTA)

        ok = executar_tool(
            self.oficina,
            "atualizar_status_os",
            {
                "numero": 1,
                "novo_status": OrdemServico.Status.EM_ANDAMENTO,
                "confirmado": True,
            },
        )
        self.assertTrue(ok.get("ok"))
        self.ordem.refresh_from_db()
        self.assertEqual(self.ordem.status, OrdemServico.Status.EM_ANDAMENTO)

    def test_busca_linguagem_natural_painel(self):
        """Busca NL no painel retorna OS/clientes relevantes."""
        url = reverse("core:busca")
        resp = self.client.get(url, {"q": "João"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "João Silva")
        self.assertContains(resp, f"#{self.ordem.numero}")

        resp_placa = self.client.get(url, {"q": "ABC1D23"})
        self.assertEqual(resp_placa.status_code, 200)
        self.assertContains(resp_placa, "ABC1D23")

    def test_resumo_diario_celery_beat(self):
        """Task periódica gera resumo diário para o dono."""
        mail.outbox.clear()
        result = enviar_resumo_diario.delay()
        payload = result.get() if hasattr(result, "get") else result
        self.assertEqual(payload["oficinas_enviadas"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Resumo diário", mail.outbox[0].subject)
        self.assertIn(self.oficina.nome, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("OS abertas", mail.outbox[0].body)
