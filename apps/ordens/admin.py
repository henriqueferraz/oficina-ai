from django.contrib import admin

from .models import ChecklistItem, OrdemFoto, OrdemItem, OrdemServico


class ItemInline(admin.TabularInline):
    model = OrdemItem
    extra = 0


class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(OrdemServico)
class OrdemServicoAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "status", "prioridade", "pagamento_status")
    list_filter = ("status", "prioridade")
    inlines = [ItemInline, ChecklistInline]


admin.site.register(OrdemFoto)
