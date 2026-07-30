# Desenvolvimento

## Pré-requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Conta Neon (Postgres) — ou SQLite local alterando `DATABASE_URL`
- (Opcional) Cloudflare R2, OpenAI API key

## Setup

```bash
git clone https://github.com/henriqueferraz/oficina-ai.git
cd oficina-ai
cp .env.example .env
# edite DATABASE_URL, SECRET_KEY, e opcionalmente OpenAI / R2

uv sync --group dev
uv run python manage.py migrate
uv run python manage.py seed_demo   # demo / demo1234
uv run python manage.py runserver
```

App: http://127.0.0.1:8000

Defina `OPENAI_API_KEY` no `.env` para habilitar o agente LLM, a busca NL com interpretação e a transcrição de áudio (Whisper / `OPENAI_TRANSCRIPTION_MODEL`).

## Celery (resumo diário)

Em desenvolvimento o default é `CELERY_TASK_ALWAYS_EAGER=True` (tasks síncronas, sem Redis).

Em produção (ou local com Redis):

```bash
# worker
uv run celery -A config worker -l info

# beat (agenda o resumo diário às 07:00)
uv run celery -A config beat -l info
```

E-mail do resumo: com `DEBUG=True` usa backend console (`EMAIL_BACKEND`). Em produção configure SMTP e `DEFAULT_FROM_EMAIL`.

## Comandos úteis

| Comando | Uso |
|---------|-----|
| `uv run python manage.py runserver` | Servidor local |
| `uv run python manage.py migrate` | Migrações |
| `uv run python manage.py seed_demo` | Dados demo |
| `uv run python manage.py test tests` | Suíte completa |
| `uv run python manage.py test tests.test_semana2_operacao` | Uma fase |
| `uv run python manage.py test tests.test_semana3_ia` | Fase IA |
| `uv run ruff check .` | Lint |
| `uv run ruff format .` | Formatar |
| `uv run ruff format --check .` | Checar formato (CI) |
| `uv run python scripts/bump_version.py patch --fixed "…"` | Bump patch + CHANGELOG |
| `uv run python scripts/bump_version.py minor --added "…"` | Bump minor + CHANGELOG |

## Versão do sistema

A versão exibida na UI (`vX.Y.Z`) vem do arquivo `VERSION` (sincronizado com `pyproject.toml` e `CHANGELOG.md`).

Ao entregar feat/fix, use o script — não edite os três arquivos à mão:

```bash
uv run python scripts/bump_version.py minor --added "descrição da feature"
uv run python scripts/bump_version.py patch --fixed "descrição do fix"
```

## Template de commit (local)

```bash
git config commit.template .gitmessage
```

Isso sugere o formato Conventional Commits ao rodar `git commit`.

## UI e responsividade (regra de ouro)

Toda tela deve funcionar em mobile, tablet e desktop.

- **Bootstrap 5.3.8** via CDN + tema em `static/css/app.css` (`--bs-*`)
- Componentes: `btn-primary` / `btn-outline-secondary`, `form-control`/`form-select`, `card`, `table`
- Mobile: hamburger / offcanvas; `lg+`: sidebar
- Preferir `row`/`col-*`, `table-responsive`, formulários empilhados no mobile
- Regra permanente do agente: `.cursor/rules/responsividade.mdc`

## Estrutura de testes

| Arquivo | Fase |
|---------|------|
| `tests/test_semana1_fundacao.py` | Auth, modelos, painel |
| `tests/test_semana2_operacao.py` | CRUD, estoque, PDF, CSV |
| `tests/test_semana2_midia.py` | Fotos/vídeo orçamento |
| `tests/test_semana3_ia.py` | Tools IA, busca NL, resumo diário |
| `tests/test_semana4_cliente.py` | Portal, aprovação, WhatsApp, notificações |
| `tests/test_semana5_6_diferenciacao.py` | Pix, recibo, financeiro↔OS, relatórios, comissões, papéis, PWA |
| `tests/test_audio_agentes.py` | Áudio no painel/WhatsApp, transcrição, fallbacks |

## Branching sugerido

- `main` — estável
- `feat/...`, `fix/...`, `docs/...` — trabalho curto
- PR com título Conventional Commits (ex.: `feat(ordens): ...`)
