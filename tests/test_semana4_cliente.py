"""
Semana 4 — Cliente final
Portal público, aprovação, WhatsApp e notificações.
"""

import json

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.agentes.models import ConversaAgente, MensagemAgente
from apps.agentes.whatsapp import OUTBOX, normalizar_telefone
from apps.core.notifications import notificar_status_ordem
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemServico
from tests.helpers import (
    criar_cliente,
    criar_oficina_com_usuario,
    criar_orcamento,
    criar_ordem,
    criar_veiculo,
)


class Semana4ClienteFinalTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(
            self.oficina,
            nome="Maria Cliente",
            telefone="11988887777",
            email="maria@cliente.test",
        )
        self.veiculo = criar_veiculo(self.oficina, self.cliente)
        self.ordem = criar_ordem(
            self.oficina,
            self.cliente,
            veiculo=self.veiculo,
            numero=1,
            diagnostico="Revisão geral",
        )
        self.orcamento = criar_orcamento(
            self.oficina,
            self.cliente,
            veiculo=self.veiculo,
            numero=1,
            status=Orcamento.Status.ENVIADO,
        )
        OUTBOX.clear()
        mail.outbox.clear()

    def test_link_publico_os_por_token(self):
        """Cliente acessa OS via token_publico sem login."""
        self.assertTrue(self.ordem.token_publico)
        url = reverse("portal:os_publica", kwargs={"token": self.ordem.token_publico})
        anon = Client()
        resp = anon.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"#{self.ordem.numero}")
        self.assertContains(resp, "Maria Cliente")
        self.assertContains(resp, self.oficina.nome)

    def test_aprovacao_orcamento_pelo_cliente(self):
        """Cliente aprova orçamento pelo link público."""
        self.assertTrue(self.orcamento.token_publico)
        anon = Client()
        url = reverse("portal:orcamento_publico", kwargs={"token": self.orcamento.token_publico})
        resp = anon.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Aprovar")

        aprovar = reverse(
            "portal:orcamento_aprovar", kwargs={"token": self.orcamento.token_publico}
        )
        resp = anon.post(aprovar)
        self.assertEqual(resp.status_code, 302)
        self.orcamento.refresh_from_db()
        self.assertEqual(self.orcamento.status, Orcamento.Status.APROVADO)

    def test_webhook_whatsapp(self):
        """Webhook WhatsApp recebe mensagem e responde via agente."""
        verify = reverse("agentes:whatsapp_webhook")
        resp = self.client.get(
            verify,
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "oficina-ai-verify",
                "hub.challenge": "desafio123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), "desafio123")

        telefone = normalizar_telefone(self.cliente.telefone)
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": telefone,
                                        "id": "wamid.TEST",
                                        "type": "text",
                                        "text": {"body": "Qual o status da minha OS?"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        resp = self.client.post(
            verify,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["respostas"], 1)

        conversa = ConversaAgente.objects.get(
            canal=ConversaAgente.Canal.WHATSAPP, telefone_externo=telefone
        )
        self.assertEqual(conversa.oficina_id, self.oficina.id)
        self.assertTrue(
            MensagemAgente.objects.filter(
                conversa=conversa, papel=MensagemAgente.Papel.ASSISTANT
            ).exists()
        )
        self.assertTrue(OUTBOX)  # resposta enviada (dry-run)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_notificacao_status_pronta_entregue(self):
        """Notifica cliente quando OS fica pronta/entregue."""
        mail.outbox.clear()
        OUTBOX.clear()
        self.ordem.status = OrdemServico.Status.PRONTA
        self.ordem.save(update_fields=["status", "atualizado_em"])
        result = notificar_status_ordem(self.ordem)
        self.assertTrue(result["email"])
        self.assertTrue(result["whatsapp"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f"OS #{self.ordem.numero}", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.cliente.email])
        self.assertTrue(any(self.ordem.token_publico in m["texto"] for m in OUTBOX))
