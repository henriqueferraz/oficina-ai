"""Agente virtual da oficina com tools sobre OS, orçamentos e clientes."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db.models import Max, Q

from apps.agentes.models import ConversaAgente, MensagemAgente
from apps.core.models import Cliente, Peca, Servico, Veiculo
from apps.core.services import baixar_estoque_ordem
from apps.orcamentos.models import Orcamento, OrcamentoItem
from apps.ordens.models import OrdemServico

SYSTEM_PROMPT = """Você é o assistente virtual da oficina {oficina_nome}.
Ajude a equipe e clientes com status de OS, orçamentos, clientes e veículos.
Seja objetivo, em português do Brasil. Quando usar ferramentas, confirme o resultado com clareza.
Não invente números de OS ou valores — consulte as ferramentas.

Para alterar status de OS, use atualizar_status_os primeiro com confirmado=false,
mostre o preview ao usuário e só chame de novo com confirmado=true após ele confirmar (ex.: "sim").
Para orçamentos por diagnóstico, use criar_orcamento_rascunho com cliente_id e itens do catálogo.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_ordem_servico",
            "description": "Busca ordens de serviço por número, placa ou nome do cliente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Número, placa ou nome"},
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_cliente",
            "description": "Busca clientes por nome, telefone ou documento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string"},
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumo_oficina",
            "description": "Resumo operacional: OS abertas, prontas e orçamentos pendentes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_orcamento_rascunho",
            "description": (
                "Cria orçamento em rascunho a partir de um diagnóstico, "
                "vinculando itens do catálogo (serviço/peça) por nome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente_id": {"type": "integer"},
                    "veiculo_id": {"type": "integer"},
                    "diagnostico": {"type": "string"},
                    "itens": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tipo": {
                                    "type": "string",
                                    "enum": ["servico", "peca"],
                                },
                                "termo": {"type": "string"},
                                "quantidade": {"type": "number"},
                            },
                            "required": ["tipo", "termo"],
                        },
                    },
                },
                "required": ["cliente_id", "diagnostico"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "atualizar_status_os",
            "description": (
                "Atualiza o status de uma OS. Sem confirmado=true apenas retorna preview; "
                "com confirmado=true grava a alteração."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {"type": "integer"},
                    "novo_status": {
                        "type": "string",
                        "enum": [s.value for s in OrdemServico.Status],
                    },
                    "confirmado": {"type": "boolean"},
                },
                "required": ["numero", "novo_status"],
            },
        },
    },
]


def _dec(value, default="1") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default).replace(",", "."))
    except (InvalidOperation, TypeError):
        return Decimal(default)


def busca_operacional(oficina, termo: str) -> dict[str, list[dict[str, Any]]]:
    """Busca multi-entidade por palavra-chave (OS, clientes, orçamentos, veículos)."""
    termo = (termo or "").strip()
    if not termo:
        return {"ordens": [], "clientes": [], "orcamentos": [], "veiculos": []}

    ordens_qs = OrdemServico.objects.filter(oficina=oficina).select_related("cliente", "veiculo")
    if termo.isdigit():
        ordens_qs = ordens_qs.filter(numero=int(termo))
    else:
        ordens_qs = ordens_qs.filter(
            Q(cliente__nome__icontains=termo)
            | Q(veiculo__placa__icontains=termo)
            | Q(diagnostico__icontains=termo)
        )

    clientes_qs = Cliente.objects.filter(oficina=oficina, ativo=True).filter(
        Q(nome__icontains=termo) | Q(telefone__icontains=termo) | Q(documento__icontains=termo)
    )

    orcamentos_qs = Orcamento.objects.filter(oficina=oficina).select_related("cliente", "veiculo")
    if termo.isdigit():
        orcamentos_qs = orcamentos_qs.filter(numero=int(termo))
    else:
        orcamentos_qs = orcamentos_qs.filter(
            Q(cliente__nome__icontains=termo)
            | Q(veiculo__placa__icontains=termo)
            | Q(observacoes__icontains=termo)
        )

    veiculos_qs = (
        Veiculo.objects.filter(oficina=oficina)
        .select_related("cliente")
        .filter(
            Q(placa__icontains=termo)
            | Q(marca__icontains=termo)
            | Q(modelo__icontains=termo)
            | Q(cliente__nome__icontains=termo)
        )
    )

    ordens = list(ordens_qs.prefetch_related("itens")[:10])
    orcamentos = list(orcamentos_qs.prefetch_related("itens")[:10])
    clientes = list(clientes_qs[:10])
    veiculos = list(veiculos_qs[:10])

    return {
        "ordens": [
            {
                "id": o.id,
                "numero": o.numero,
                "status": o.get_status_display(),
                "cliente": o.cliente.nome,
                "veiculo": str(o.veiculo) if o.veiculo else None,
                "total": str(o.total),
            }
            for o in ordens
        ],
        "clientes": [
            {
                "id": c.id,
                "nome": c.nome,
                "telefone": c.telefone,
                "documento": c.documento,
            }
            for c in clientes
        ],
        "orcamentos": [
            {
                "id": o.id,
                "numero": o.numero,
                "status": o.get_status_display(),
                "cliente": o.cliente.nome,
                "total": str(o.total),
            }
            for o in orcamentos
        ],
        "veiculos": [
            {
                "id": v.id,
                "placa": v.placa,
                "marca": v.marca,
                "modelo": v.modelo,
                "cliente": v.cliente.nome,
            }
            for v in veiculos
        ],
    }


def extrair_termo_busca(frase: str) -> str:
    """Com LLM, reduz frase NL a um termo de busca; sem LLM, devolve a frase."""
    frase = (frase or "").strip()
    if not frase or not settings.LLM_ENABLED:
        return frase
    # Buscas curtas (placa, nome, número) não precisam de LLM — evita 1–3s de latência
    if len(frase) <= 40 and len(frase.split()) <= 3:
        return frase
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extraia o termo de busca principal (nome, placa, número de OS "
                        "ou documento) da frase do usuário. Responda só com o termo, "
                        "sem pontuação extra."
                    ),
                },
                {"role": "user", "content": frase},
            ],
            max_tokens=40,
        )
        termo = (response.choices[0].message.content or "").strip()
        return termo or frase
    except Exception:
        return frase


def _tool_buscar_ordem(oficina, termo: str) -> list[dict[str, Any]]:
    return busca_operacional(oficina, termo)["ordens"]


def _tool_buscar_cliente(oficina, termo: str) -> list[dict[str, Any]]:
    return busca_operacional(oficina, termo)["clientes"]


def _tool_resumo(oficina) -> dict[str, Any]:
    ordens = OrdemServico.objects.filter(oficina=oficina)
    return {
        "os_abertas": ordens.exclude(
            status__in=[OrdemServico.Status.ENTREGUE, OrdemServico.Status.CANCELADA]
        ).count(),
        "os_prontas": ordens.filter(status=OrdemServico.Status.PRONTA).count(),
        "orcamentos_enviados": Orcamento.objects.filter(
            oficina=oficina, status=Orcamento.Status.ENVIADO
        ).count(),
        "orcamentos_rascunho": Orcamento.objects.filter(
            oficina=oficina, status=Orcamento.Status.RASCUNHO
        ).count(),
        "clientes_ativos": Cliente.objects.filter(oficina=oficina, ativo=True).count(),
        "veiculos": Veiculo.objects.filter(oficina=oficina).count(),
    }


def _tool_criar_orcamento_rascunho(oficina, args: dict[str, Any]) -> dict[str, Any]:
    cliente_id = args.get("cliente_id")
    diagnostico = (args.get("diagnostico") or "").strip()
    if not cliente_id or not diagnostico:
        return {"erro": "cliente_id e diagnostico são obrigatórios."}

    try:
        cliente = Cliente.objects.get(pk=cliente_id, oficina=oficina, ativo=True)
    except Cliente.DoesNotExist:
        return {"erro": f"Cliente {cliente_id} não encontrado."}

    veiculo = None
    veiculo_id = args.get("veiculo_id")
    if veiculo_id:
        try:
            veiculo = Veiculo.objects.get(pk=veiculo_id, oficina=oficina, cliente=cliente)
        except Veiculo.DoesNotExist:
            return {"erro": f"Veículo {veiculo_id} não encontrado para este cliente."}

    ultimo = Orcamento.objects.filter(oficina=oficina).aggregate(n=Max("numero"))["n"] or 0
    orcamento = Orcamento.objects.create(
        oficina=oficina,
        cliente=cliente,
        veiculo=veiculo,
        numero=ultimo + 1,
        status=Orcamento.Status.RASCUNHO,
        observacoes=diagnostico,
        gerado_por_ia=True,
    )

    itens_criados: list[dict[str, Any]] = []
    avisos: list[str] = []
    for raw in args.get("itens") or []:
        tipo = (raw.get("tipo") or "").strip().lower()
        termo = (raw.get("termo") or "").strip()
        qtd = _dec(raw.get("quantidade"), "1")
        if not termo:
            avisos.append("Item ignorado: termo vazio.")
            continue

        if tipo == OrcamentoItem.Tipo.SERVICO:
            servico = Servico.objects.filter(
                oficina=oficina, ativo=True, nome__icontains=termo
            ).first()
            if not servico:
                avisos.append(f"Serviço não encontrado: {termo}")
                continue
            item = OrcamentoItem.objects.create(
                orcamento=orcamento,
                tipo=OrcamentoItem.Tipo.SERVICO,
                descricao=servico.nome,
                quantidade=qtd,
                valor_unitario=servico.preco,
                servico=servico,
            )
            itens_criados.append(
                {"tipo": "servico", "descricao": item.descricao, "total": str(item.total)}
            )
        elif tipo == OrcamentoItem.Tipo.PECA:
            peca = Peca.objects.filter(oficina=oficina, ativo=True, nome__icontains=termo).first()
            if not peca:
                avisos.append(f"Peça não encontrada: {termo}")
                continue
            item = OrcamentoItem.objects.create(
                orcamento=orcamento,
                tipo=OrcamentoItem.Tipo.PECA,
                descricao=peca.nome,
                quantidade=qtd,
                valor_unitario=peca.preco,
                peca=peca,
            )
            itens_criados.append(
                {"tipo": "peca", "descricao": item.descricao, "total": str(item.total)}
            )
        else:
            avisos.append(f"Tipo inválido: {tipo}")

    return {
        "id": orcamento.id,
        "numero": orcamento.numero,
        "status": orcamento.status,
        "gerado_por_ia": orcamento.gerado_por_ia,
        "total": str(orcamento.total),
        "itens_criados": itens_criados,
        "avisos": avisos,
    }


def _tool_atualizar_status_os(oficina, args: dict[str, Any]) -> dict[str, Any]:
    numero = args.get("numero")
    novo_status = (args.get("novo_status") or "").strip()
    confirmado = bool(args.get("confirmado", False))

    if numero is None:
        return {"erro": "numero é obrigatório."}
    if novo_status not in OrdemServico.Status.values:
        return {
            "erro": f"Status inválido: {novo_status}",
            "status_validos": list(OrdemServico.Status.values),
        }

    try:
        ordem = OrdemServico.objects.select_related("cliente", "veiculo").get(
            oficina=oficina, numero=int(numero)
        )
    except (OrdemServico.DoesNotExist, TypeError, ValueError):
        return {"erro": f"OS #{numero} não encontrada."}

    preview = {
        "precisa_confirmacao": True,
        "os": ordem.numero,
        "cliente": ordem.cliente.nome,
        "status_atual": ordem.status,
        "status_atual_label": ordem.get_status_display(),
        "status_proposto": novo_status,
        "status_proposto_label": dict(OrdemServico.Status.choices).get(novo_status, novo_status),
    }
    if not confirmado:
        return preview

    ordem.status = novo_status
    ordem.save(update_fields=["status", "atualizado_em"])
    if novo_status in {OrdemServico.Status.PRONTA, OrdemServico.Status.ENTREGUE}:
        baixar_estoque_ordem(ordem)
        ordem.refresh_from_db()
        from apps.core.notifications import notificar_status_ordem

        notificar_status_ordem(ordem)

    return {
        "ok": True,
        "os": ordem.numero,
        "status": ordem.status,
        "status_label": ordem.get_status_display(),
        "estoque_baixado": ordem.estoque_baixado,
    }


def executar_tool(oficina, name: str, args: dict[str, Any]) -> Any:
    if name == "buscar_ordem_servico":
        return _tool_buscar_ordem(oficina, args.get("termo", ""))
    if name == "buscar_cliente":
        return _tool_buscar_cliente(oficina, args.get("termo", ""))
    if name == "resumo_oficina":
        return _tool_resumo(oficina)
    if name == "criar_orcamento_rascunho":
        return _tool_criar_orcamento_rascunho(oficina, args)
    if name == "atualizar_status_os":
        return _tool_atualizar_status_os(oficina, args)
    return {"erro": f"Ferramenta desconhecida: {name}"}


def chat(
    conversa: ConversaAgente,
    mensagem_usuario: str,
    *,
    audio=None,
    metadados: dict | None = None,
) -> str:
    """Processa mensagem do usuário e retorna resposta do assistente."""
    meta = dict(metadados or {})
    msg_user = MensagemAgente(
        conversa=conversa,
        papel=MensagemAgente.Papel.USER,
        conteudo=mensagem_usuario,
        metadados=meta,
    )
    if audio is not None:
        msg_user.audio = audio
        meta.setdefault("tipo", "audio")
        msg_user.metadados = meta
    msg_user.save()

    if not settings.LLM_ENABLED:
        resposta = (
            "A IA ainda não está configurada. Defina OPENAI_API_KEY no .env.\n\n"
            f"Enquanto isso, resumo rápido: {json.dumps(_tool_resumo(conversa.oficina), ensure_ascii=False)}"
        )
        MensagemAgente.objects.create(
            conversa=conversa,
            papel=MensagemAgente.Papel.ASSISTANT,
            conteudo=resposta,
        )
        return resposta

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    historico = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(oficina_nome=conversa.oficina.nome),
        }
    ]
    for m in conversa.mensagens.order_by("criado_em")[:30]:
        if m.papel in (MensagemAgente.Papel.USER, MensagemAgente.Papel.ASSISTANT):
            historico.append({"role": m.papel, "content": m.conteudo})

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=historico,
        tools=TOOLS,
        tool_choice="auto",
    )
    message = response.choices[0].message

    # Tool calling loop (1 round for MVP)
    if message.tool_calls:
        historico.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        )
        for tc in message.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = executar_tool(conversa.oficina, tc.function.name, args)
            MensagemAgente.objects.create(
                conversa=conversa,
                papel=MensagemAgente.Papel.TOOL,
                conteudo=json.dumps(result, ensure_ascii=False),
                tool_name=tc.function.name,
            )
            historico.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=historico,
        )
        message = response.choices[0].message

    resposta = message.content or "Não consegui gerar uma resposta."
    MensagemAgente.objects.create(
        conversa=conversa,
        papel=MensagemAgente.Papel.ASSISTANT,
        conteudo=resposta,
    )
    conversa.save(update_fields=["atualizado_em"])
    return resposta
