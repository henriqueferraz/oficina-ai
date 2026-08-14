# Oficina AI

Sistema de gestão para oficinas de funilaria, pintura e mecânica — com agentes de IA.

## Stack

- Django 6 + HTMX
- PostgreSQL (Neon)
- OpenAI (agentes com tools)
- Celery (fila; eager em dev)
- Cloudflare R2 (fotos de orçamento)
- GitHub Actions (CI) + Conventional Commits

## Início rápido

```bash
git clone https://github.com/henriqueferraz/oficina-ai.git
cd oficina-ai
cp .env.example .env   # edite DATABASE_URL, SECRET_KEY, etc.

uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed_demo   # opcional: demo / demo1234
uv run python manage.py test tests
uv run python manage.py runserver
```

Abra http://127.0.0.1:8000/contas/cadastrar/ (ou login `demo` / `demo1234` após o seed).

## Módulos

| App | Função |
|-----|--------|
| `apps.core` | Oficina, clientes, veículos, catálogo, compras, CSV, relatórios, comissões, PWA |
| `apps.orcamentos` | Orçamentos + itens + fotos/vídeo + conversão para OS + PDF |
| `apps.ordens` | OS, checklist, fotos, baixa de estoque, PDF, recibo, Pix QR |
| `apps.financeiro` | Lançamentos (vínculo opcional com OS) |
| `apps.accounts` | Auth + papéis (dono/recepção/mecânico/financeiro) |
| `apps.agentes` | Conversas do atendente virtual + WhatsApp |
| `apps.portal` | Links públicos OS/orçamento |
| `agents/` | Lógica LLM + tools |

## Documentação

| Recurso | Link |
|---------|------|
| Índice docs | [docs/README.md](docs/README.md) |
| Arquitetura | [docs/arquitetura.md](docs/arquitetura.md) |
| Desenvolvimento | [docs/desenvolvimento.md](docs/desenvolvimento.md) |
| Deploy / R2 | [docs/deploy.md](docs/deploy.md) |
| Conventional Commits | [docs/conventional-commits.md](docs/conventional-commits.md) |
| Contribuir | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Roadmap | [ROADMAP.md](ROADMAP.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

## Qualidade

```bash
uv run ruff check .
uv run ruff format .
uv run python manage.py test tests
```

Pull requests exigem título e commits no padrão Conventional Commits. A validação
local de lint e testes deve ser executada antes de abrir um PR.

## Neon / R2 / Deploy

- **Neon:** `DATABASE_URL` no `.env`
- **Cloudflare R2:** vars `AWS_*` no `.env` (ver [.env.example](.env.example) e [docs/deploy.md](docs/deploy.md))
- **EasyPanel / Docker:** `Dockerfile` na raiz — ver [docs/deploy.md](docs/deploy.md)
