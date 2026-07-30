# Roadmap MVP — Oficina AI (4–6 semanas)

## Stack

- Python + Django 6 + HTMX + Neon Postgres
- Celery (eager no início) + Redis depois
- Agentes LLM em `agents/` com tools (OS, clientes, resumo)
- Cloudflare R2 (S3-compatible) para fotos de orçamento
- CI/CD (GitHub Actions) + Conventional Commits + docs em `docs/`

## Testes

Rodar toda a suíte (organizada por fase em `tests/`):

```bash
uv run python manage.py test tests
```

Lint:

```bash
uv run ruff check .
uv run ruff format --check .
```

Por fase:

```bash
uv run python manage.py test tests.test_semana1_fundacao
uv run python manage.py test tests.test_semana2_operacao tests.test_semana2_midia
uv run python manage.py test tests.test_semana3_ia
uv run python manage.py test tests.test_semana4_cliente
uv run python manage.py test tests.test_semana5_6_diferenciacao
uv run python manage.py test tests.test_audio_agentes
```

## Semana 1 — Fundação ✅

- [x] Projeto Django + Neon
- [x] Modelos: oficina, clientes, veículos, serviços, peças
- [x] Orçamentos e OS com itens/status/prioridade
- [x] Financeiro básico
- [x] Auth + cadastro de oficina
- [x] Painel + kanban
- [x] Agente IA no painel (tools)
- [x] Testes (`tests/test_semana1_fundacao.py`)

## Semana 2 — Operação do dia a dia ✅

- [x] CRUD completo de veículos no UI
- [x] CRUD serviços/peças no UI (sem admin)
- [x] Fornecedores na UI
- [x] Compras / entrada de estoque
- [x] Baixa automática de estoque ao concluir OS
- [x] Checklist de entrada/saída + upload de fotos
- [x] Converter orçamento → OS em 1 clique
- [x] Impressão PDF de OS/orçamento
- [x] Importação CSV (clientes, fornecedores, peças)
- [x] Seed de dados demo (`python manage.py seed_demo`)
- [x] Fotos (até 10, R2/S3) + 1 vídeo stream no orçamento
- [x] Testes (`tests/test_semana2_operacao.py`, `tests/test_semana2_midia.py`)

## Semana 3 — IA que age ✅

- [x] Configurar OPENAI_API_KEY
- [x] Tool: criar rascunho de orçamento por diagnóstico
- [x] Tool: atualizar status de OS (com confirmação)
- [x] Busca em linguagem natural no painel
- [x] Resumo diário automático para o dono (Celery beat)
- [x] Testes (`tests/test_semana3_ia.py`)

## Semana 4 — Cliente final ✅

- [x] Link público da OS (token)
- [x] Aprovação de orçamento pelo cliente
- [x] Integração WhatsApp (webhook + agente)
- [x] Notificações de status “pronta / entregue”
- [x] Testes (`tests/test_semana4_cliente.py`)

## Semanas 5–6 — Diferenciação ✅

- [x] Pix na OS (QR)
- [x] Recibo / cupom simples (não fiscal)
- [x] Vínculo lançamento financeiro ↔ OS
- [x] Relatórios operacionais (ticket médio, peças mais usadas, conversão)
- [x] Comissões por mecânico
- [x] Dashboard de margem / conversão orçamento→OS
- [x] PWA básico (fotos no celular)
- [x] Multi-usuário com papéis (dono/recepção/mecânico)
- [x] Testes (`tests/test_semana5_6_diferenciacao.py`)

## Próxima fase — Áudio nos agentes ✅

Agentes passam a receber áudio (além de texto). Escopo deliberadamente enxuto: sem hub de pagamento 12x, billing SaaS ou gateway — só o diferencial de atendimento por voz.

- [x] Receber áudio no chat do painel (`/agentes/`)
- [x] Receber áudio no webhook WhatsApp (mensagem de mídia)
- [x] Transcrição automática (ex.: OpenAI Whisper / API de áudio)
- [x] Injetar a transcrição na conversa e seguir o fluxo atual do agente (mesmas tools: rascunho de orçamento, busca de OS/cliente, status, etc.)
- [x] Persistência da mensagem de áudio (arquivo + texto transcrito) em `MensagemAgente`
- [x] Fallback claro quando a transcrição falhar ou o áudio for inválido/muito longo
- [x] Testes (`tests/test_audio_agentes.py`)

Fluxo: atendente grava áudio (peças, serviços, placa) → transcrição → agente monta/atualiza orçamento como já faz com texto.

## Fora do MVP (atualização futura)

- NF-e / NFS-e / NFC-e
- PDV de varejo genérico
- Variações de produto estilo e-commerce
- Conciliação bancária e plano de contas
- Emissão de boletos
- Multi-oficina / franquia
- Offline sync completo
- App nativo
- Hub de pagamento com parcelamento (ex.: até 12x) — fora do escopo desta fase
