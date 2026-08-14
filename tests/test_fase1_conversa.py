"""Testes do estado e registro de mensagens da Fase 1."""

from django.db import IntegrityError
from django.test import TestCase

from apps.agentes.models import ConversaAgente, MensagemAgente
from tests.helpers import criar_oficina_com_usuario


class MensagemAgenteTests(TestCase):
    def setUp(self):
        _, oficina = criar_oficina_com_usuario()
        self.conversa = ConversaAgente.objects.create(
            oficina=oficina,
            canal=ConversaAgente.Canal.WHATSAPP,
            telefone_externo="5511999999999",
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
