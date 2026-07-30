import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import requer_permissao
from apps.financeiro.models import Lancamento
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemItem, OrdemServico

from .models import Cliente, Compra, Fornecedor, Peca, Servico, Veiculo
from .relatorios import (
    comissoes_por_mecanico,
    conversao_orcamento_os,
    margem_operacional,
    pecas_mais_usadas,
    ticket_medio,
)
from .services import registrar_compra
from .validators import cpf_valido, formatar_cpf, formatar_telefone, maiusculo


def get_oficina(request):
    """Oficina do usuário autenticado (1 query com select_related, cache no request)."""
    cached = getattr(request, "_oficina_atual", ...)
    if cached is not ...:
        return cached

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        request._oficina_atual = None
        return None

    from apps.accounts.models import PerfilUsuario

    try:
        perfil = PerfilUsuario.objects.select_related("oficina", "papel").get(user_id=request.user.pk)
    except PerfilUsuario.DoesNotExist:
        request._oficina_atual = None
        return None

    # Evita queries extras em get_papel / templates via user.perfil
    request.user.perfil = perfil
    oficina = perfil.oficina if perfil.ativo else None
    request._oficina_atual = oficina
    return oficina


def _telefone(value: str) -> str:
    return formatar_telefone((value or "").strip())


def _dec(value, default="0"):
    try:
        return Decimal(str(value or default).replace(",", "."))
    except (InvalidOperation, TypeError):
        return Decimal(default)


@login_required
def dashboard(request):
    from collections import defaultdict

    from django.db.models import Case, Count, DecimalField, F, Prefetch, Q, Value, When
    from django.db.models.functions import Coalesce

    from apps.accounts.permissions import get_papel, user_pode

    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")

    status_kanban = [
        OrdemServico.Status.ABERTA,
        OrdemServico.Status.EM_ANDAMENTO,
        OrdemServico.Status.AGUARDANDO_PECA,
        OrdemServico.Status.AGUARDANDO_APROVACAO,
        OrdemServico.Status.PRONTA,
    ]
    encerradas = [OrdemServico.Status.ENTREGUE, OrdemServico.Status.CANCELADA]
    itens_prefetch = Prefetch(
        "itens",
        queryset=OrdemItem.objects.select_related("servico", "peca"),
    )

    # Contagens de OS em 1 query
    os_stats = OrdemServico.objects.filter(oficina=oficina).aggregate(
        os_abertas=Count("id", filter=~Q(status__in=encerradas)),
        os_prontas=Count("id", filter=Q(status=OrdemServico.Status.PRONTA)),
    )
    total_clientes = Cliente.objects.filter(oficina=oficina, ativo=True).count()
    orcamentos_pendentes = Orcamento.objects.filter(
        oficina=oficina, status=Orcamento.Status.ENVIADO
    ).count()

    # Caixa: receita e despesa numa única agregação
    zero = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))
    caixa_agg = Lancamento.objects.filter(oficina=oficina, pago=True).aggregate(
        receitas=Coalesce(
            Sum(
                Case(
                    When(tipo=Lancamento.Tipo.RECEITA, then=F("valor")),
                    default=zero,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            zero,
        ),
        despesas=Coalesce(
            Sum(
                Case(
                    When(tipo=Lancamento.Tipo.DESPESA, then=F("valor")),
                    default=zero,
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            zero,
        ),
    )
    receitas = caixa_agg["receitas"]
    despesas = caixa_agg["despesas"]

    conversao = None
    margem = None
    if user_pode(request.user, "relatorios"):
        conversao = conversao_orcamento_os(oficina)
        margem = margem_operacional(oficina, receitas=receitas, despesas=despesas)

    # Uma query cobre recentes + kanban; Prefetch com select_related evita N+1 de itens
    ordens_pool = list(
        OrdemServico.objects.filter(oficina=oficina)
        .select_related("cliente", "veiculo")
        .prefetch_related(itens_prefetch)
        .order_by("-atualizado_em")[:80]
    )
    ordens_recentes = ordens_pool[:8]
    por_status: dict[str, list] = defaultdict(list)
    for ordem in ordens_pool:
        if ordem.status not in status_kanban:
            continue
        col = por_status[ordem.status]
        if len(col) < 10:
            col.append(ordem)

    status_labels = dict(OrdemServico.Status.choices)
    kanban = [
        {
            "status": status,
            "label": status_labels[status],
            "ordens": por_status.get(status, []),
        }
        for status in status_kanban
    ]

    pecas_estoque_baixo = list(
        Peca.objects.filter(
            oficina=oficina,
            ativo=True,
        )
        .filter(estoque__lte=F("estoque_minimo"))
        .order_by("nome")[:10]
    )

    return render(
        request,
        "core/dashboard.html",
        {
            "oficina": oficina,
            "total_clientes": total_clientes,
            "os_abertas": os_stats["os_abertas"],
            "os_prontas": os_stats["os_prontas"],
            "orcamentos_pendentes": orcamentos_pendentes,
            "pecas_estoque_baixo": pecas_estoque_baixo,
            "ordens_recentes": ordens_recentes,
            "kanban": kanban,
            "caixa": receitas - despesas,
            "conversao": conversao,
            "margem": margem,
        },
    )


@login_required
def busca(request):
    """Busca em linguagem natural no painel (OS, clientes, orçamentos, veículos)."""
    from agents.assistente import busca_operacional, extrair_termo_busca

    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")

    frase = request.GET.get("q", "").strip()
    termo = extrair_termo_busca(frase) if frase else ""
    resultados = (
        busca_operacional(oficina, termo)
        if termo
        else {
            "ordens": [],
            "clientes": [],
            "orcamentos": [],
            "veiculos": [],
        }
    )
    return render(
        request,
        "core/busca.html",
        {
            "oficina": oficina,
            "frase": frase,
            "termo": termo,
            "resultados": resultados,
        },
    )


# ── Clientes ──────────────────────────────────────────────────────────────────


@login_required
@requer_permissao("clientes")
def cliente_list(request):
    oficina = get_oficina(request)
    q = request.GET.get("q", "").strip()
    clientes = Cliente.objects.filter(oficina=oficina, ativo=True)
    if q:
        clientes = clientes.filter(
            Q(nome__icontains=q) | Q(telefone__icontains=q) | Q(documento__icontains=q)
        )
    template = "core/partials/cliente_rows.html" if request.htmx else "core/clientes.html"
    return render(request, template, {"clientes": clientes[:50], "q": q})


@login_required
@requer_permissao("clientes")
@require_http_methods(["GET", "POST"])
def cliente_create(request):
    oficina = get_oficina(request)
    if request.method == "POST":
        nome = maiusculo(request.POST.get("nome", ""))
        cpf_raw = request.POST.get("documento", "").strip()
        endereco = maiusculo(request.POST.get("endereco", ""))
        email = request.POST.get("email", "").strip()
        telefone = _telefone(request.POST.get("telefone", ""))
        ctx = {
            "nome": nome,
            "documento": cpf_raw,
            "telefone": telefone,
            "email": email,
            "endereco": endereco,
        }
        if cpf_raw and not cpf_valido(cpf_raw):
            messages.error(request, "CPF inválido. Verifique os dígitos e tente novamente.")
            return render(request, "core/cliente_form.html", {"form_data": ctx})
        documento = formatar_cpf(cpf_raw) if cpf_raw else ""
        Cliente.objects.create(
            oficina=oficina,
            nome=nome,
            documento=documento,
            telefone=telefone,
            email=email,
            endereco=endereco,
        )
        if request.htmx:
            clientes = Cliente.objects.filter(oficina=oficina, ativo=True)[:50]
            return render(request, "core/partials/cliente_rows.html", {"clientes": clientes})
        messages.success(request, "Cliente cadastrado.")
        return redirect("core:clientes")
    return render(request, "core/cliente_form.html")


# ── Veículos ──────────────────────────────────────────────────────────────────


@login_required
@requer_permissao("veiculos")
def veiculo_list(request):
    oficina = get_oficina(request)
    q = request.GET.get("q", "").strip()
    veiculos = Veiculo.objects.filter(oficina=oficina).select_related("cliente")
    if q:
        veiculos = veiculos.filter(
            Q(placa__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(cliente__nome__icontains=q)
        )
    return render(request, "core/veiculos.html", {"veiculos": veiculos[:50], "q": q})


@login_required
@requer_permissao("veiculos")
@require_http_methods(["GET", "POST"])
def veiculo_create(request):
    oficina = get_oficina(request)
    clientes = Cliente.objects.filter(oficina=oficina, ativo=True)
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=request.POST.get("cliente"), oficina=oficina)
        ano = request.POST.get("ano") or None
        km = request.POST.get("km") or None
        Veiculo.objects.create(
            oficina=oficina,
            cliente=cliente,
            placa=maiusculo(request.POST.get("placa", "")),
            marca=maiusculo(request.POST.get("marca", "")),
            modelo=maiusculo(request.POST.get("modelo", "")),
            ano=int(ano) if ano else None,
            cor=maiusculo(request.POST.get("cor", "")),
            km=int(km) if km else None,
            chassi=maiusculo(request.POST.get("chassi", "")),
            observacoes=maiusculo(request.POST.get("observacoes", "")),
        )
        messages.success(request, "Veículo cadastrado.")
        return redirect("core:veiculos")
    return render(request, "core/veiculo_form.html", {"clientes": clientes, "veiculo": None})


@login_required
@requer_permissao("veiculos")
@require_http_methods(["GET", "POST"])
def veiculo_edit(request, pk):
    oficina = get_oficina(request)
    veiculo = get_object_or_404(Veiculo, pk=pk, oficina=oficina)
    clientes = Cliente.objects.filter(oficina=oficina, ativo=True)
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=request.POST.get("cliente"), oficina=oficina)
        ano = request.POST.get("ano") or None
        km = request.POST.get("km") or None
        veiculo.cliente = cliente
        veiculo.placa = maiusculo(request.POST.get("placa", ""))
        veiculo.marca = maiusculo(request.POST.get("marca", ""))
        veiculo.modelo = maiusculo(request.POST.get("modelo", ""))
        veiculo.ano = int(ano) if ano else None
        veiculo.cor = maiusculo(request.POST.get("cor", ""))
        veiculo.km = int(km) if km else None
        veiculo.chassi = maiusculo(request.POST.get("chassi", ""))
        veiculo.observacoes = maiusculo(request.POST.get("observacoes", ""))
        veiculo.save()
        messages.success(request, "Veículo atualizado.")
        return redirect("core:veiculos")
    return render(request, "core/veiculo_form.html", {"clientes": clientes, "veiculo": veiculo})


# ── Catálogo / Serviços / Peças ────────────────────────────────────────────────


@login_required
@requer_permissao("catalogo")
def catalogo(request):
    oficina = get_oficina(request)
    return render(
        request,
        "core/catalogo.html",
        {
            "servicos": Servico.objects.filter(oficina=oficina, ativo=True),
            "pecas": Peca.objects.filter(oficina=oficina, ativo=True).select_related("fornecedor"),
        },
    )


@login_required
@requer_permissao("catalogo")
@require_http_methods(["GET", "POST"])
def servico_create(request):
    oficina = get_oficina(request)
    if request.method == "POST":
        Servico.objects.create(
            oficina=oficina,
            nome=maiusculo(request.POST.get("nome", "")),
            descricao=maiusculo(request.POST.get("descricao", "")),
            preco=_dec(request.POST.get("preco")),
            tempo_estimado_min=int(request.POST.get("tempo_estimado_min") or 60),
        )
        messages.success(request, "Serviço cadastrado.")
        return redirect("core:catalogo")
    return render(request, "core/servico_form.html", {"servico": None})


@login_required
@requer_permissao("catalogo")
@require_http_methods(["GET", "POST"])
def servico_edit(request, pk):
    oficina = get_oficina(request)
    servico = get_object_or_404(Servico, pk=pk, oficina=oficina)
    if request.method == "POST":
        servico.nome = maiusculo(request.POST.get("nome", ""))
        servico.descricao = maiusculo(request.POST.get("descricao", ""))
        servico.preco = _dec(request.POST.get("preco"))
        servico.tempo_estimado_min = int(request.POST.get("tempo_estimado_min") or 60)
        servico.ativo = request.POST.get("ativo") == "on"
        servico.save()
        messages.success(request, "Serviço atualizado.")
        return redirect("core:catalogo")
    return render(request, "core/servico_form.html", {"servico": servico})


@login_required
@requer_permissao("catalogo")
@require_http_methods(["GET", "POST"])
def peca_create(request):
    oficina = get_oficina(request)
    fornecedores = Fornecedor.objects.filter(oficina=oficina, ativo=True)
    if request.method == "POST":
        fornecedor_id = request.POST.get("fornecedor") or None
        fornecedor = (
            get_object_or_404(Fornecedor, pk=fornecedor_id, oficina=oficina)
            if fornecedor_id
            else None
        )
        Peca.objects.create(
            oficina=oficina,
            fornecedor=fornecedor,
            codigo=maiusculo(request.POST.get("codigo", "")),
            nome=maiusculo(request.POST.get("nome", "")),
            descricao=maiusculo(request.POST.get("descricao", "")),
            custo=_dec(request.POST.get("custo")),
            preco=_dec(request.POST.get("preco")),
            estoque=_dec(request.POST.get("estoque")),
            estoque_minimo=_dec(request.POST.get("estoque_minimo")),
            unidade=maiusculo(request.POST.get("unidade", "UN")) or "UN",
        )
        messages.success(request, "Peça cadastrada.")
        return redirect("core:catalogo")
    return render(request, "core/peca_form.html", {"peca": None, "fornecedores": fornecedores})


@login_required
@requer_permissao("catalogo")
@require_http_methods(["GET", "POST"])
def peca_edit(request, pk):
    oficina = get_oficina(request)
    peca = get_object_or_404(Peca, pk=pk, oficina=oficina)
    fornecedores = Fornecedor.objects.filter(oficina=oficina, ativo=True)
    if request.method == "POST":
        fornecedor_id = request.POST.get("fornecedor") or None
        peca.fornecedor = (
            get_object_or_404(Fornecedor, pk=fornecedor_id, oficina=oficina)
            if fornecedor_id
            else None
        )
        peca.codigo = maiusculo(request.POST.get("codigo", ""))
        peca.nome = maiusculo(request.POST.get("nome", ""))
        peca.descricao = maiusculo(request.POST.get("descricao", ""))
        peca.custo = _dec(request.POST.get("custo"))
        peca.preco = _dec(request.POST.get("preco"))
        peca.estoque = _dec(request.POST.get("estoque"))
        peca.estoque_minimo = _dec(request.POST.get("estoque_minimo"))
        peca.unidade = maiusculo(request.POST.get("unidade", "UN")) or "UN"
        peca.ativo = request.POST.get("ativo") == "on"
        peca.save()
        messages.success(request, "Peça atualizada.")
        return redirect("core:catalogo")
    return render(request, "core/peca_form.html", {"peca": peca, "fornecedores": fornecedores})


# ── Fornecedores ───────────────────────────────────────────────────────────────


@login_required
@requer_permissao("fornecedores")
def fornecedor_list(request):
    oficina = get_oficina(request)
    fornecedores = Fornecedor.objects.filter(oficina=oficina, ativo=True)
    return render(request, "core/fornecedores.html", {"fornecedores": fornecedores})


@login_required
@requer_permissao("fornecedores")
@require_http_methods(["GET", "POST"])
def fornecedor_create(request):
    oficina = get_oficina(request)
    if request.method == "POST":
        Fornecedor.objects.create(
            oficina=oficina,
            nome=maiusculo(request.POST.get("nome", "")),
            documento=request.POST.get("documento", "").strip(),
            telefone=_telefone(request.POST.get("telefone", "")),
            email=request.POST.get("email", "").strip(),
        )
        messages.success(request, "Fornecedor cadastrado.")
        return redirect("core:fornecedores")
    return render(request, "core/fornecedor_form.html", {"fornecedor": None})


@login_required
@requer_permissao("fornecedores")
@require_http_methods(["GET", "POST"])
def fornecedor_edit(request, pk):
    oficina = get_oficina(request)
    fornecedor = get_object_or_404(Fornecedor, pk=pk, oficina=oficina)
    if request.method == "POST":
        fornecedor.nome = maiusculo(request.POST.get("nome", ""))
        fornecedor.documento = request.POST.get("documento", "").strip()
        fornecedor.telefone = _telefone(request.POST.get("telefone", ""))
        fornecedor.email = request.POST.get("email", "").strip()
        fornecedor.ativo = request.POST.get("ativo") == "on"
        fornecedor.save()
        messages.success(request, "Fornecedor atualizado.")
        return redirect("core:fornecedores")
    return render(request, "core/fornecedor_form.html", {"fornecedor": fornecedor})


# ── Compras / entrada de estoque ───────────────────────────────────────────────


@login_required
@requer_permissao("compras")
def compra_list(request):
    oficina = get_oficina(request)
    compras = (
        Compra.objects.filter(oficina=oficina)
        .select_related("fornecedor")
        .prefetch_related("itens")[:50]
    )
    return render(request, "core/compras.html", {"compras": compras})


@login_required
@requer_permissao("compras")
@require_http_methods(["GET", "POST"])
def compra_create(request):
    oficina = get_oficina(request)
    pecas = Peca.objects.filter(oficina=oficina, ativo=True)
    fornecedores = Fornecedor.objects.filter(oficina=oficina, ativo=True)
    if request.method == "POST":
        peca_id = request.POST.get("peca")
        qtd = _dec(request.POST.get("quantidade"), "1")
        custo = _dec(request.POST.get("custo_unitario"))
        if not peca_id or qtd <= 0:
            messages.error(request, "Informe peça e quantidade válidas.")
            return redirect("core:compra_create")
        fornecedor_id = request.POST.get("fornecedor") or None
        fornecedor = (
            get_object_or_404(Fornecedor, pk=fornecedor_id, oficina=oficina)
            if fornecedor_id
            else None
        )
        data_str = request.POST.get("data") or date.today().isoformat()
        registrar_compra(
            oficina=oficina,
            fornecedor=fornecedor,
            data=date.fromisoformat(data_str),
            observacoes=request.POST.get("observacoes", "").strip(),
            itens=[{"peca_id": peca_id, "quantidade": qtd, "custo_unitario": custo}],
        )
        messages.success(request, "Entrada de estoque registrada.")
        return redirect("core:compras")
    return render(
        request,
        "core/compra_form.html",
        {"pecas": pecas, "fornecedores": fornecedores, "hoje": date.today().isoformat()},
    )


# ── Importação CSV ─────────────────────────────────────────────────────────────


@login_required
@requer_permissao("importar")
@require_http_methods(["GET", "POST"])
def importar_csv(request):
    oficina = get_oficina(request)
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        arquivo = request.FILES.get("arquivo")
        if not arquivo or tipo not in {"clientes", "fornecedores", "pecas"}:
            messages.error(request, "Selecione o tipo e um arquivo CSV.")
            return redirect("core:importar_csv")

        raw = arquivo.read()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            messages.error(request, "CSV vazio ou sem cabeçalho.")
            return redirect("core:importar_csv")

        criados = 0
        for row in reader:
            row = {((k or "").strip().lower()): (v or "").strip() for k, v in row.items()}
            if tipo == "clientes":
                nome = row.get("nome") or row.get("name")
                if not nome:
                    continue
                Cliente.objects.create(
                    oficina=oficina,
                    nome=nome,
                    documento=row.get("documento") or row.get("cpf") or row.get("cnpj") or "",
                    telefone=_telefone(row.get("telefone") or row.get("fone") or ""),
                    email=row.get("email") or "",
                    endereco=row.get("endereco") or row.get("endereço") or "",
                )
                criados += 1
            elif tipo == "fornecedores":
                nome = row.get("nome")
                if not nome:
                    continue
                Fornecedor.objects.create(
                    oficina=oficina,
                    nome=nome,
                    documento=row.get("documento") or row.get("cnpj") or "",
                    telefone=_telefone(row.get("telefone") or ""),
                    email=row.get("email") or "",
                )
                criados += 1
            else:
                nome = row.get("nome")
                if not nome:
                    continue
                Peca.objects.create(
                    oficina=oficina,
                    codigo=row.get("codigo") or row.get("código") or "",
                    nome=nome,
                    descricao=row.get("descricao") or row.get("descrição") or "",
                    custo=_dec(row.get("custo")),
                    preco=_dec(row.get("preco") or row.get("preço")),
                    estoque=_dec(row.get("estoque")),
                    estoque_minimo=_dec(row.get("estoque_minimo") or row.get("estoque_mínimo")),
                    unidade=row.get("unidade") or "UN",
                )
                criados += 1

        messages.success(request, f"{criados} registro(s) importado(s).")
        return redirect("core:importar_csv")

    return render(request, "core/importar_csv.html")


# ── Relatórios / comissões / oficina ───────────────────────────────────────────


@login_required
def relatorios(request):
    from apps.accounts.permissions import user_pode

    if not user_pode(request.user, "relatorios"):
        messages.error(request, "Você não tem permissão para acessar esta área.")
        return redirect("core:dashboard")
    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")
    return render(
        request,
        "core/relatorios.html",
        {
            "oficina": oficina,
            "ticket_medio": ticket_medio(oficina),
            "pecas": list(pecas_mais_usadas(oficina)),
            "conversao": conversao_orcamento_os(oficina),
            "margem": margem_operacional(oficina),
        },
    )


@login_required
def comissoes(request):
    from apps.accounts.permissions import user_pode

    if not user_pode(request.user, "relatorios"):
        messages.error(request, "Você não tem permissão para acessar esta área.")
        return redirect("core:dashboard")
    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")
    return render(
        request,
        "core/comissoes.html",
        {
            "oficina": oficina,
            "comissoes": comissoes_por_mecanico(oficina),
            "comissao_padrao": oficina.comissao_padrao_percentual,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def configuracoes(request):
    from apps.accounts.models import PapelOficina
    from apps.accounts.permissions import (
        PERMISSOES_CATALOGO,
        PERMISSOES_CODIGOS,
        TODAS_PERMISSOES,
        garantir_papeis_padrao,
        is_administrador,
        slug_papel_unico,
        user_pode,
    )
    from apps.core.validators import UF_CHOICES, cnpj_valido, formatar_cnpj

    if not user_pode(request.user, "configuracoes") and not is_administrador(request.user):
        messages.error(request, "Você não tem permissão para acessar esta área.")
        return redirect("core:dashboard")
    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")

    garantir_papeis_padrao(oficina)

    if request.method == "POST":
        acao = request.POST.get("acao") or "salvar_oficina"

        if acao == "criar_papel":
            nome = request.POST.get("nome_papel", "").strip()
            if not nome:
                messages.error(request, "Informe o nome do novo papel.")
            else:
                slug = slug_papel_unico(oficina, nome)
                perms = [
                    c
                    for c in request.POST.getlist("perm_novo")
                    if c in PERMISSOES_CODIGOS and c != "configuracoes"
                ]
                PapelOficina.objects.create(
                    oficina=oficina,
                    slug=slug,
                    nome=nome,
                    eh_administrador=False,
                    permissoes=perms,
                    ativo=True,
                )
                messages.success(request, f"Papel “{nome}” criado.")
            return redirect("core:configuracoes")

        if acao == "salvar_papeis":
            for papel in PapelOficina.objects.filter(oficina=oficina):
                if f"nome_{papel.pk}" not in request.POST and f"perm_{papel.pk}" not in request.POST:
                    continue
                if papel.eh_administrador:
                    papel.permissoes = list(TODAS_PERMISSOES)
                    papel.ativo = True
                    papel.save(update_fields=["permissoes", "ativo"])
                    continue
                perms = [
                    c
                    for c in request.POST.getlist(f"perm_{papel.pk}")
                    if c in PERMISSOES_CODIGOS
                ]
                # Só admin pode ter configurações
                perms = [c for c in perms if c != "configuracoes"]
                papel.permissoes = perms
                if papel.slug not in ("dono", "recepcao", "mecanico", "financeiro"):
                    papel.ativo = request.POST.get(f"ativo_{papel.pk}") == "on"
                papel.nome = request.POST.get(f"nome_{papel.pk}", papel.nome).strip() or papel.nome
                papel.save(update_fields=["permissoes", "ativo", "nome"])
            messages.success(request, "Papéis e permissões atualizados.")
            return redirect("core:configuracoes")

        # salvar dados da oficina
        nome = request.POST.get("nome", "").strip()
        cnpj_raw = request.POST.get("cnpj", "").strip()
        telefone = _telefone(request.POST.get("telefone", ""))
        email = request.POST.get("email", "").strip()
        cep = request.POST.get("cep", "").strip()
        endereco = request.POST.get("endereco", "").strip()
        bairro = request.POST.get("bairro", "").strip()
        cidade = request.POST.get("cidade", "").strip()
        uf = request.POST.get("uf", "").strip().upper()[:2]
        pix_chave = request.POST.get("pix_chave", "").strip()
        pix_nome = request.POST.get("pix_nome", "").strip()[:25]
        comissao = _dec(request.POST.get("comissao_padrao_percentual"), "10")

        erros = []
        if not nome:
            erros.append("Informe o nome da oficina.")
        if cnpj_raw and not cnpj_valido(cnpj_raw):
            erros.append("CNPJ inválido. Confira os dígitos verificadores.")
        if uf and uf not in {c[0] for c in UF_CHOICES if c[0]}:
            erros.append("UF inválida.")
        if email and "@" not in email:
            erros.append("E-mail inválido.")

        if erros:
            for msg in erros:
                messages.error(request, msg)
            oficina.nome = nome or oficina.nome
            oficina.cnpj = cnpj_raw
            oficina.telefone = telefone
            oficina.email = email
            oficina.cep = cep
            oficina.endereco = endereco
            oficina.bairro = bairro
            oficina.cidade = cidade
            oficina.uf = uf
            oficina.pix_chave = pix_chave
            oficina.pix_nome = pix_nome
            oficina.comissao_padrao_percentual = comissao
        else:
            oficina.nome = nome
            oficina.cnpj = formatar_cnpj(cnpj_raw) if cnpj_raw else ""
            oficina.telefone = telefone
            oficina.email = email
            oficina.cep = cep
            oficina.endereco = endereco
            oficina.bairro = bairro
            oficina.cidade = cidade
            oficina.uf = uf
            oficina.pix_chave = pix_chave
            oficina.pix_nome = pix_nome
            oficina.comissao_padrao_percentual = comissao

            if request.POST.get("remover_logo") and oficina.logo:
                oficina.logo.delete(save=False)
                oficina.logo = None
            elif request.FILES.get("logo"):
                if oficina.logo:
                    oficina.logo.delete(save=False)
                oficina.logo = request.FILES["logo"]

            oficina.save()
            messages.success(request, "Configurações da oficina atualizadas.")
            return redirect("core:configuracoes")

    papeis = list(PapelOficina.objects.filter(oficina=oficina).order_by("-eh_administrador", "nome"))
    return render(
        request,
        "core/configuracoes.html",
        {
            "oficina": oficina,
            "ufs": UF_CHOICES,
            "papeis": papeis,
            "permissoes_catalogo": PERMISSOES_CATALOGO,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def equipe(request):
    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.models import User
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    from apps.accounts.models import PapelOficina, PerfilUsuario
    from apps.accounts.permissions import garantir_papeis_padrao, is_administrador, user_pode

    oficina = get_oficina(request)
    if not oficina:
        return render(request, "core/sem_oficina.html")

    if not user_pode(request.user, "equipe") and not is_administrador(request.user):
        messages.error(request, "Você não tem permissão para acessar esta área.")
        return redirect("core:dashboard")

    garantir_papeis_padrao(oficina)
    is_admin = is_administrador(request.user)
    papeis_qs = PapelOficina.objects.filter(oficina=oficina, ativo=True)

    if request.method == "POST":
        acao = request.POST.get("acao") or "criar"

        if acao == "atualizar":
            perfil = get_object_or_404(
                PerfilUsuario, pk=request.POST.get("perfil_id"), oficina=oficina
            )
            eh_proprio = perfil.user_id == request.user.id
            if not is_admin and not eh_proprio:
                messages.error(request, "Você só pode editar o seu próprio perfil.")
                return redirect("core:equipe")

            username = request.POST.get("username", "").strip()
            telefone = _telefone(request.POST.get("telefone", ""))
            nova_senha = request.POST.get("nova_senha", "")
            confirma = request.POST.get("nova_senha_confirma", "")

            if not username:
                messages.error(request, "Informe o nome de usuário.")
                return redirect("core:equipe")
            if (
                User.objects.filter(username__iexact=username)
                .exclude(pk=perfil.user_id)
                .exists()
            ):
                messages.error(request, "Este nome de usuário já está em uso.")
                return redirect("core:equipe")

            user = perfil.user
            user.username = username
            user.save(update_fields=["username"])
            perfil.telefone = telefone

            if is_admin:
                papel_id = request.POST.get("papel")
                novo_papel = get_object_or_404(PapelOficina, pk=papel_id, oficina=oficina, ativo=True)
                perfil.papel = novo_papel
                comissao = request.POST.get("comissao_percentual")
                if comissao is not None and str(comissao).strip() != "":
                    perfil.comissao_percentual = _dec(comissao)
                else:
                    perfil.comissao_percentual = None
                perfil.ativo = request.POST.get("ativo") == "on"

            perfil.save()

            if nova_senha or confirma:
                if not nova_senha:
                    messages.error(request, "Informe a nova senha.")
                    return redirect("core:equipe")
                if nova_senha != confirma:
                    messages.error(request, "A confirmação da senha não confere.")
                    return redirect("core:equipe")
                try:
                    validate_password(nova_senha, user=user)
                except ValidationError as exc:
                    for msg in exc.messages:
                        messages.error(request, msg)
                    return redirect("core:equipe")
                user.set_password(nova_senha)
                user.save()
                if eh_proprio:
                    update_session_auth_hash(request, user)
                messages.success(
                    request, f"Dados de “{user.get_username()}” atualizados (incluindo senha)."
                )
            else:
                messages.success(request, f"Dados de “{user.get_username()}” atualizados.")
            return redirect("core:equipe")

        if acao == "criar":
            if not is_admin:
                messages.error(request, "Somente o administrador pode criar usuários.")
                return redirect("core:equipe")

            username = request.POST.get("username", "").strip()
            password = request.POST.get("password", "")
            papel_id = request.POST.get("papel")
            telefone = _telefone(request.POST.get("telefone", ""))
            comissao = request.POST.get("comissao_percentual")

            if not username or not password:
                messages.error(request, "Informe usuário e senha.")
            elif User.objects.filter(username__iexact=username).exists():
                messages.error(request, "Este usuário já existe.")
            else:
                try:
                    novo_papel = PapelOficina.objects.get(pk=papel_id, oficina=oficina, ativo=True)
                except (PapelOficina.DoesNotExist, ValueError, TypeError):
                    messages.error(request, "Papel inválido.")
                else:
                    try:
                        validate_password(password)
                    except ValidationError as exc:
                        for msg in exc.messages:
                            messages.error(request, msg)
                    else:
                        user = User.objects.create_user(username=username, password=password)
                        perfil = PerfilUsuario.objects.create(
                            user=user,
                            oficina=oficina,
                            papel=novo_papel,
                            telefone=telefone,
                        )
                        if comissao is not None and str(comissao).strip() != "":
                            perfil.comissao_percentual = _dec(comissao)
                            perfil.save(update_fields=["comissao_percentual"])
                        messages.success(
                            request,
                            f"Usuário {username} criado ({perfil.get_papel_display()}).",
                        )
                        return redirect("core:equipe")
        else:
            messages.error(request, "Ação inválida.")
            return redirect("core:equipe")

    membros = (
        PerfilUsuario.objects.filter(oficina=oficina)
        .select_related("user", "papel")
        .order_by("papel__nome", "user__username")
    )
    papel_mecanico = papeis_qs.filter(slug="mecanico").first()
    return render(
        request,
        "core/equipe.html",
        {
            "oficina": oficina,
            "membros": membros,
            "papeis": [(p.pk, p.nome) for p in papeis_qs],
            "papel_padrao_id": papel_mecanico.pk if papel_mecanico else None,
            "is_admin": is_admin,
            "user_id": request.user.id,
        },
    )


def pwa_manifest(request):
    from django.http import JsonResponse

    return JsonResponse(
        {
            "name": "Oficina AI",
            "short_name": "Oficina AI",
            "description": "Gestão de oficina com fotos no celular",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f1412",
            "theme_color": "#3dcf8e",
            "lang": "pt-BR",
            "icons": [
                {
                    "src": "/static/img/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
                {
                    "src": "/static/img/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        },
        content_type="application/manifest+json",
    )


def pwa_service_worker(request):
    from django.http import HttpResponse

    # Network-first em tudo (HTML + CSS/JS). Cache só como fallback offline.
    # Cache-first em /static/css/app.css fazia o layout “voltar” ao antigo
    # ao navegar entre páginas (SW servia CSS desatualizado).
    js = """
const CACHE = 'oficina-ai-v3';
const ASSETS = ['/static/img/icon-192.png', '/static/img/icon-512.png'];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  event.respondWith(
    fetch(req).then((res) => {
      const url = new URL(req.url);
      if (res.ok && url.pathname.startsWith('/static/')) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req))
  );
});
""".strip()
    response = HttpResponse(js, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
