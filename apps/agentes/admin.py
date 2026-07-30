from django.contrib import admin

from .models import ConversaAgente, MensagemAgente


class MensagemInline(admin.TabularInline):
    model = MensagemAgente
    extra = 0
    readonly_fields = ("papel", "conteudo", "tool_name", "audio", "criado_em")


@admin.register(ConversaAgente)
class ConversaAgenteAdmin(admin.ModelAdmin):
    list_display = ("titulo", "canal", "oficina", "ativa", "atualizado_em")
    inlines = [MensagemInline]
