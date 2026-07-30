# Guia de contribuição

Obrigado por contribuir com o **Oficina AI**.

## Antes de começar

1. Leia a [documentação](docs/README.md) e o [ROADMAP](ROADMAP.md).
2. Configure o ambiente em [Desenvolvimento](docs/desenvolvimento.md).
3. Use [Conventional Commits](docs/conventional-commits.md).

## Regra de ouro: responsividade

Toda mudança de interface **deve** ser mobile-first e utilizável em celular, tablet e desktop.

- Stack UI: **Bootstrap 5.3.8** + `static/css/app.css` (tema escuro).
- Botões/forms/painéis: `btn-primary` / `btn-outline-secondary`, `form-control`/`form-select`, `card`.
- Mobile: menu hamburger (offcanvas); desktop (`lg+`): sidebar fixa.
- Use `row`/`col-*`, `table-responsive` e formulários que empilham no mobile.
- Evite grids/larguras fixas inline que quebrem o viewport.
- Detalhes e exemplos: `.cursor/rules/responsividade.mdc`.

## Fluxo

1. Crie uma branch a partir de `main`:
   ```bash
   git checkout -b feat/minha-feature
   ```
2. Implemente com testes na fase correspondente (`tests/test_semana*.py`).
3. Rode localmente:
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run python manage.py test tests
   ```
4. Abra um PR com título no formato Conventional Commits, por exemplo:
   ```text
   feat(core): adiciona importação CSV de fornecedores
   ```
5. Aguarde o CI (lint + testes + commitlint).

## Escopo do PR

- Prefira PRs pequenos e focados.
- Não commite `.env`, chaves ou mídia local.
- Versionamento: o agente (ou você) roda `uv run python scripts/bump_version.py …` ao entregar feat/fix — atualiza `VERSION`, `pyproject.toml` e `CHANGELOG.md`.
- Se a feature estiver no roadmap, marque o item em `ROADMAP.md`.

## Reportar bugs / ideias

Abra uma issue descrevendo:

- O que aconteceu vs. o esperado
- Passos para reproduzir
- Ambiente (OS, Python, branch)

## Código de conduta (resumo)

Seja respeitoso, objetivo e colaborativo. Discussões técnicas > preferências pessoais.
