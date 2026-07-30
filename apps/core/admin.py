from django.contrib import admin

from .models import Cliente, Compra, CompraItem, Fornecedor, Oficina, Peca, Servico, Veiculo


class CompraItemInline(admin.TabularInline):
    model = CompraItem
    extra = 0


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("numero", "oficina", "fornecedor", "data")
    inlines = [CompraItemInline]


admin.site.register(Oficina)
admin.site.register(Cliente)
admin.site.register(Veiculo)
admin.site.register(Fornecedor)
admin.site.register(Servico)
admin.site.register(Peca)
