"""Áudio nos agentes: painel + WhatsApp + transcrição."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.agentes.models import ConversaAgente, MensagemAgente
from apps.agentes.whatsapp import OUTBOX, extrair_mensagens_webhook, normalizar_telefone
from tests.helpers import criar_cliente, criar_oficina_com_usuario


def ogg_minimo(nome="audio.ogg"):
    """Arquivo de áudio mínimo para upload em testes (não precisa ser OGG válido)."""
    return SimpleUploadedFile(nome, b"OggS\x00fake-audio-bytes", content_type="audio/ogg")


class AudioAgentesTests(TestCase):
    def setUp(self):
        OUTBOX.clear()
        self.user, self.oficina = criar_oficina_com_usuario(username="dono_audio")
        self.cliente = criar_cliente(self.oficina, telefone="11988887777")
        self.client.login(username="dono_audio", password="senha123")
        self.conversa = ConversaAgente.objects.create(
            oficina=self.oficina,
            usuario=self.user,
            canal=ConversaAgente.Canal.PAINEL,
            titulo="Teste áudio",
        )

    def test_extrair_audio_webhook(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5511988887777",
                                        "id": "wamid.AUDIO",
                                        "type": "audio",
                                        "audio": {
                                            "id": "media123",
                                            "mime_type": "audio/ogg; codecs=opus",
                                            "voice": True,
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        msgs = extrair_mensagens_webhook(payload)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["type"], "audio")
        self.assertEqual(msgs[0]["media_id"], "media123")
        self.assertIn("audio/ogg", msgs[0]["mime"])

    @patch("agents.entrada.transcrever_audio", return_value="Resumo da oficina por favor")
    def test_painel_envia_audio(self, _mock_tr):
        url = reverse("agentes:conversa", kwargs={"pk": self.conversa.pk})
        resp = self.client.post(url, {"audio": ogg_minimo()}, follow=True)
        self.assertEqual(resp.status_code, 200)
        user_msgs = MensagemAgente.objects.filter(
            conversa=self.conversa, papel=MensagemAgente.Papel.USER
        )
        self.assertEqual(user_msgs.count(), 1)
        msg = user_msgs.get()
        self.assertTrue(msg.audio)
        self.assertEqual(msg.conteudo, "Resumo da oficina por favor")
        self.assertTrue(msg.metadados.get("transcricao_ok"))
        self.assertTrue(
            MensagemAgente.objects.filter(
                conversa=self.conversa, papel=MensagemAgente.Papel.ASSISTANT
            ).exists()
        )

    @patch("agents.entrada.transcrever_audio", return_value="placa ABC1D23 funilaria")
    def test_painel_htmx_audio(self, _mock_tr):
        url = reverse("agentes:conversa", kwargs={"pk": self.conversa.pk})
        resp = self.client.post(
            url,
            {"audio": ogg_minimo()},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "placa ABC1D23 funilaria")
        self.assertContains(resp, "chat-audio-player")

    def test_painel_audio_sem_api_key(self):
        """Sem OPENAI_API_KEY: persiste áudio e responde fallback de transcrição."""
        url = reverse("agentes:conversa", kwargs={"pk": self.conversa.pk})
        resp = self.client.post(url, {"audio": ogg_minimo()}, follow=True)
        self.assertEqual(resp.status_code, 200)
        msg = MensagemAgente.objects.get(
            conversa=self.conversa, papel=MensagemAgente.Papel.USER
        )
        self.assertTrue(msg.audio)
        self.assertFalse(msg.metadados.get("transcricao_ok"))
        assistente = MensagemAgente.objects.filter(
            conversa=self.conversa, papel=MensagemAgente.Papel.ASSISTANT
        ).latest("criado_em")
        self.assertIn("OPENAI_API_KEY", assistente.conteudo)

    def test_painel_audio_invalido(self):
        ruim = SimpleUploadedFile("x.txt", b"not-audio", content_type="text/plain")
        url = reverse("agentes:conversa", kwargs={"pk": self.conversa.pk})
        resp = self.client.post(url, {"audio": ruim}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            MensagemAgente.objects.filter(
                conversa=self.conversa, papel=MensagemAgente.Papel.USER
            ).exists()
        )
        assistente = MensagemAgente.objects.get(
            conversa=self.conversa, papel=MensagemAgente.Papel.ASSISTANT
        )
        self.assertIn("áudio", assistente.conteudo.lower())

    @patch(
        "apps.agentes.whatsapp.baixar_midia_whatsapp",
        return_value=(b"OggS\x00wa-audio", "audio/ogg"),
    )
    @patch("agents.entrada.transcrever_audio", return_value="Qual o status da OS?")
    def test_webhook_whatsapp_audio(self, _mock_tr, _mock_dl):
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
                                        "id": "wamid.AUDIO2",
                                        "type": "audio",
                                        "audio": {
                                            "id": "media999",
                                            "mime_type": "audio/ogg; codecs=opus",
                                            "voice": True,
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        url = reverse("agentes:whatsapp_webhook")
        resp = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["respostas"], 1)

        conversa = ConversaAgente.objects.get(
            canal=ConversaAgente.Canal.WHATSAPP, telefone_externo=telefone
        )
        user_msg = MensagemAgente.objects.get(
            conversa=conversa, papel=MensagemAgente.Papel.USER
        )
        self.assertEqual(user_msg.conteudo, "Qual o status da OS?")
        self.assertTrue(user_msg.audio)
        self.assertTrue(OUTBOX)

    @override_settings(WHATSAPP_ACCESS_TOKEN="")
    def test_webhook_whatsapp_audio_falha_download(self):
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
                                        "id": "wamid.AUDIO3",
                                        "type": "audio",
                                        "audio": {
                                            "id": "media-fail",
                                            "mime_type": "audio/ogg",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        url = reverse("agentes:whatsapp_webhook")
        resp = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["respostas"], 1)
        conversa = ConversaAgente.objects.get(
            canal=ConversaAgente.Canal.WHATSAPP, telefone_externo=telefone
        )
        assistente = MensagemAgente.objects.get(
            conversa=conversa, papel=MensagemAgente.Papel.ASSISTANT
        )
        self.assertIn("baixá", assistente.conteudo.lower())
