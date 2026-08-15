import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.agentes.models import ConversaAgente, MensagemAgente
from apps.agentes.whatsapp import enviar_whatsapp, processar_mensagem_entrada
from tests.helpers import criar_cliente, criar_oficina_com_usuario


class MensagemAgenteTests(TestCase):
    def setUp(self):
        _, oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(oficina, telefone="11999999999")
        self.conversa = ConversaAgente.objects.create(
            oficina=oficina,
            canal=ConversaAgente.Canal.WHATSAPP,
            telefone_externo=self.cliente.telefone,
            cliente=self.cliente,
        )

    def test_registra_tipo_status_erro_e_id_whatsapp(self):
        mensagem = MensagemAgente.objects.create(
            conversa=self.conversa,
            papel=MensagemAgente.Papel.USER,
            conteudo="Preciso de um orçamento",
            whatsapp_message_id="wamid.001",
            tipo=MensagemAgente.Tipo.TEXTO,
            status=MensagemAgente.StatusProcessamento.ERRO,
            erro_processamento="Falha temporária no agente",
        )

        mensagem.refresh_from_db()
        self.assertEqual(mensagem.whatsapp_message_id, "wamid.001")
        self.assertEqual(mensagem.tipo, MensagemAgente.Tipo.TEXTO)
        self.assertEqual(
            mensagem.status,
            MensagemAgente.StatusProcessamento.ERRO,
        )
        self.assertEqual(mensagem.erro_processamento, "Falha temporária no agente")

    def test_id_whatsapp_nao_pode_ser_duplicado(self):
        dados = {
            "conversa": self.conversa,
            "papel": MensagemAgente.Papel.USER,
            "conteudo": "Mensagem repetida",
            "whatsapp_message_id": "wamid.duplicado",
        }
        MensagemAgente.objects.create(**dados)

        with self.assertRaises(IntegrityError):
            MensagemAgente.objects.create(**dados)

    def test_reenvio_nao_processa_novamente_a_mensagem(self):
        kwargs = {
            "telefone": self.cliente.telefone,
            "texto": "Preciso de um orçamento",
            "message_id": "wamid.reenvio",
        }

        self.assertIsNotNone(processar_mensagem_entrada(**kwargs))
        self.assertIsNone(processar_mensagem_entrada(**kwargs))
        self.assertEqual(
            MensagemAgente.objects.filter(whatsapp_message_id="wamid.reenvio").count(),
            1,
        )

    def test_contexto_expirado_reinicia_identificacao(self):
        self.conversa.etapa = ConversaAgente.Etapa.AGUARDANDO_CONFIRMACAO
        self.conversa.contexto_json = {"preview_id": "preview-antigo"}
        self.conversa.expira_em = timezone.now() - timedelta(minutes=1)
        self.conversa.save(update_fields=["etapa", "contexto_json", "expira_em"])

        processar_mensagem_entrada(
            telefone=self.cliente.telefone,
            texto="Olá novamente",
            message_id="wamid.expirado",
        )

        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.etapa, ConversaAgente.Etapa.INICIAL)
        self.assertEqual(self.conversa.contexto_json, {})
        self.assertIsNone(self.conversa.expira_em)

    def test_audio_normalizado_pelo_n8n_nao_baixa_midia_do_provedor(self):
        with (
            patch("agents.entrada.transcrever_audio", return_value="Avaliar funilaria"),
            patch("apps.agentes.whatsapp.baixar_midia_whatsapp") as baixar_midia,
        ):
            resposta = processar_mensagem_entrada(
                telefone=self.cliente.telefone,
                tipo="audio",
                mime="audio/ogg",
                message_id="evo-audio-1",
                media_content=b"OggS\x00audio-n8n",
                metadados_origem={"origem": "n8n", "evento_id": "evt-audio-1"},
            )

        self.assertIsNotNone(resposta)
        baixar_midia.assert_not_called()
        mensagem = MensagemAgente.objects.get(whatsapp_message_id="evo-audio-1")
        self.assertEqual(mensagem.metadados["origem"], "n8n")
        self.assertEqual(mensagem.metadados["evento_id"], "evt-audio-1")

    def test_confirmacao_fora_do_preview_mais_recente_e_rejeitada(self):
        self.conversa.etapa = ConversaAgente.Etapa.AGUARDANDO_CONFIRMACAO
        self.conversa.contexto_json = {"preview_id": "preview-atual"}
        self.conversa.save(update_fields=["etapa", "contexto_json"])

        self.assertTrue(self.conversa.preview_valido("preview-atual"))
        self.assertFalse(self.conversa.preview_valido("preview-antigo"))


@override_settings(N8N_INBOUND_SECRET="segredo-n8n")
class N8nWebhookTests(TestCase):
    def setUp(self):
        _, self.oficina = criar_oficina_com_usuario(username="dono_n8n")
        self.cliente = criar_cliente(self.oficina, telefone="11977776666")

    def _post_assinado(self, url, payload, *, timestamp=None):
        corpo = json.dumps(payload).encode()
        timestamp = str(timestamp or int(time.time()))
        assinatura = hmac.new(
            b"segredo-n8n", timestamp.encode() + b"." + corpo, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            url,
            data=corpo,
            content_type="application/json",
            HTTP_X_N8N_TIMESTAMP=timestamp,
            HTTP_X_N8N_SIGNATURE=f"sha256={assinatura}",
        )

    @patch("apps.agentes.webhook.processar_mensagem_n8n.delay")
    def test_evento_n8n_assinado_e_normalizado(self, delay):
        payload = {
            "evento_id": "evt-1",
            "mensagem_id_provedor": "evo-1",
            "telefone": self.cliente.telefone,
            "tipo": "text",
            "texto": "Olá",
            "instancia": "oficina-principal",
        }
        resposta = self._post_assinado(reverse("agentes:n8n_whatsapp_webhook"), payload)

        self.assertEqual(resposta.status_code, 202)
        delay.assert_called_once_with(
            telefone=self.cliente.telefone,
            texto="Olá",
            mime="",
            tipo="text",
            message_id="evo-1",
            evento_id="evt-1",
            instancia="oficina-principal",
            media_base64="",
        )

    def test_evento_n8n_com_assinatura_invalida_e_rejeitado(self):
        resposta = self.client.post(
            reverse("agentes:n8n_whatsapp_webhook"),
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_N8N_TIMESTAMP=str(int(time.time())),
            HTTP_X_N8N_SIGNATURE="sha256=invalida",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_evento_n8n_expirado_e_rejeitado(self):
        payload = {
            "evento_id": "evt-antigo",
            "mensagem_id_provedor": "evo-antigo",
            "telefone": self.cliente.telefone,
            "tipo": "text",
        }
        resposta = self._post_assinado(
            reverse("agentes:n8n_whatsapp_webhook"),
            payload,
            timestamp=int(time.time()) - 301,
        )
        self.assertEqual(resposta.status_code, 403)

    def test_midia_base64_acima_do_limite_e_rejeitada(self):
        payload = {
            "evento_id": "evt-midia-grande",
            "mensagem_id_provedor": "evo-midia-grande",
            "telefone": self.cliente.telefone,
            "tipo": "audio",
            "midia_base64": "YQ==",
        }
        with self.settings(N8N_MAX_MEDIA_BYTES=0):
            resposta = self._post_assinado(reverse("agentes:n8n_whatsapp_webhook"), payload)
        self.assertEqual(resposta.status_code, 413)


@override_settings(
    WHATSAPP_DRY_RUN=False,
    N8N_OUTBOUND_URL="https://n8n.example.test/webhook/saida",
    N8N_OUTBOUND_SECRET="segredo-saida",
    N8N_EVOLUTION_INSTANCE="oficina-principal",
)
class N8nOutboundTests(TestCase):
    @patch("httpx.post")
    def test_envio_ao_n8n_e_assinado(self, post):
        post.return_value.raise_for_status.return_value = None

        self.assertTrue(enviar_whatsapp(telefone="(11) 99999-9999", texto="Olá"))

        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertTrue(kwargs["headers"]["X-N8N-Signature"].startswith("sha256="))
        self.assertIn(b'"instancia":"oficina-principal"', kwargs["content"])
