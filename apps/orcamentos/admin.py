from django.contrib import admin

from .models import Orcamento, OrcamentoFoto, OrcamentoItem


class ItemInline(admin.TabularInline):
    model = OrcamentoItem
    extra = 0


class FotoInline(admin.TabularInline):
    model = OrcamentoFoto
    extra = 0


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "status", "criado_em")
    list_filter = ("status",)
    inlines = [ItemInline, FotoInline]
