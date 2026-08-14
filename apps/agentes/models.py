from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class ConversaAgente(TimeStampedModel):
    class Canal(models.TextChoices):
        PAINEL = "painel", "Painel"
        WHATSAPP = "whatsapp", "WhatsApp"
        PORTAL = "portal", "Portal do cliente"

    class Etapa(models.TextChoices):
        INICIAL = "inicial", "Inicial"
        IDENTIFICANDO_CLIENTE = "identificando_cliente", "Identificando cliente"
        IDENTIFICANDO_VEICULO = "identificando_veiculo", "Identificando veículo"
        MONTANDO_ORCAMENTO = "montando_orcamento", "Montando orçamento"
        AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao", "Aguardando confirmação"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDA = "concluida", "Concluída"
        ERRO = "erro", "Erro"

    oficina = models.ForeignKey("core.Oficina", on_delete=models.CASCADE, related_name="conversas")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversas_agente",
    )
    cliente = models.ForeignKey(
        "core.Cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversas_agente",
    )
    canal = models.CharField(max_length=20, choices=Canal.choices, default=Canal.PAINEL)
    titulo = models.CharField(max_length=120, blank=True)
    telefone_externo = models.CharField(max_length=20, blank=True)
    ativa = models.BooleanField(default=True)
    etapa = models.CharField(max_length=32, choices=Etapa.choices, default=Etapa.INICIAL)
    contexto_json = models.JSONField(default=dict, blank=True)
    veiculo = models.ForeignKey(
        "core.Veiculo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversas_agente",
    )
    orcamento = models.ForeignKey(
        "orcamentos.Orcamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversas_agente",
    )
    ultima_mensagem_em = models.DateTimeField(null=True, blank=True)
    expira_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-atualizado_em"]
        verbose_name = "Conversa do agente"
        verbose_name_plural = "Conversas do agente"

    def __str__(self) -> str:
        return self.titulo or f"Conversa #{self.pk}"

    def contexto_expirado(self) -> bool:
        return bool(self.expira_em and self.expira_em <= timezone.now())


class MensagemAgente(TimeStampedModel):
    class Papel(models.TextChoices):
        USER = "user", "Usuário"
        ASSISTANT = "assistant", "Assistente"
        SYSTEM = "system", "Sistema"
        TOOL = "tool", "Ferramenta"

    class Tipo(models.TextChoices):
        TEXTO = "texto", "Texto"
        AUDIO = "audio", "Áudio"
        IMAGEM = "imagem", "Imagem"
        ARQUIVO = "arquivo", "Arquivo"

    class StatusProcessamento(models.TextChoices):
        RECEBIDA = "recebida", "Recebida"
        PROCESSANDO = "processando", "Processando"
        PROCESSADA = "processada", "Processada"
        ERRO = "erro", "Erro"

    conversa = models.ForeignKey(ConversaAgente, on_delete=models.CASCADE, related_name="mensagens")
    papel = models.CharField(max_length=20, choices=Papel.choices)
    conteudo = models.TextField()
    tool_name = models.CharField(max_length=80, blank=True)
    metadados = models.JSONField(default=dict, blank=True)
    audio = models.FileField(upload_to="agentes/audio/%Y/%m/", blank=True, null=True)
    whatsapp_message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.TEXTO)
    status = models.CharField(
        max_length=20,
        choices=StatusProcessamento.choices,
        default=StatusProcessamento.PROCESSADA,
    )
    erro_processamento = models.TextField(blank=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Mensagem do agente"
        verbose_name_plural = "Mensagens do agente"

    def __str__(self) -> str:
        return f"{self.papel}: {self.conteudo[:40]}"

    def delete(self, using=None, keep_parents=False):
        nome = self.audio.name if self.audio else ""
        storage = self.audio.storage if self.audio else None
        result = super().delete(using=using, keep_parents=keep_parents)
        if nome and storage is not None:
            storage.delete(nome)
        return result
