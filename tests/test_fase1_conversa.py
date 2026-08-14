"""Testes do estado e registro de mensagens da Fase 1."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.agentes.models import ConversaAgente, MensagemAgente
from apps.agentes.whatsapp import processar_mensagem_entrada
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

    def test_confirmacao_fora_do_preview_mais_recente_e_rejeitada(self):
        self.conversa.etapa = ConversaAgente.Etapa.AGUARDANDO_CONFIRMACAO
        self.conversa.contexto_json = {"preview_id": "preview-atual"}
        self.conversa.save(update_fields=["etapa", "contexto_json"])

        self.assertTrue(self.conversa.preview_valido("preview-atual"))
        self.assertFalse(self.conversa.preview_valido("preview-antigo"))
