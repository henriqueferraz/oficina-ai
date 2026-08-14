# Changelog

Todas as mudanças notáveis deste projeto serão documentadas aqui.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/)
e [Conventional Commits](https://www.conventionalcommits.org/).

## [Unreleased]

## [0.9.0] — 2026-08-14

### Changed

- feat(docs): atualizar instruções sobre o calendário de melhorias e corrigir formatação de links

chore: atualizar versão do pacote oficina-ai para 0.7.1

## [0.8.0] — 2026-08-14

### Changed

- feat(agentes): modelar contexto das conversas

## [0.7.1] — 2026-08-14

### Changed

- docs(planejamento): conclui fase 0

## [0.7.0] — 2026-08-14

### Changed

- feat(portal): converte orçamento aprovado em OS

## [0.6.1] — 2026-08-14

### Changed

- chore(ci): automatiza versionamento

## [0.6.0] — 2026-07-30

### Fixed

- migração de vídeo compatível com SQLite nos testes

### Added

- cascata FIPE (marca → modelo → ano) no cadastro de veículo

## [0.5.1] — 2026-07-30

### Fixed

- deriva CSRF_TRUSTED_ORIGINS dos hosts em produção (evita 403 no login)

## [0.5.0] — 2026-07-30

### Added

- Dockerfile e suporte a deploy no EasyPanel (CSRF/proxy HTTPS)

## [0.4.1] — 2026-07-30

### Changed

- fotos de OS/orçamento normalizadas (1280², WebP/JPEG ≤500KB, extensões jpg/png/webp)

## [0.4.0] — 2026-07-30

### Fixed

- limpa descrição ao trocar serviço/peça
- valida tamanho e qualidade das fotos da OS

### Added

- CPF com validação no cadastro de clientes
- vídeo e limite de fotos na OS
- cadastros em maiúsculas

## [0.3.3] — 2026-07-30

### Fixed

- criação de OS: default vazio em video_url/video_titulo (evita NotNullViolation no Postgres)

## [0.3.2] — 2026-07-30

### Fixed

- btn-primary usa verde do tema (--bs-btn-bg) em vez do azul padrão do Bootstrap

## [0.3.1] — 2026-07-30

### Fixed

- padroniza altura, hierarquia e links-botão do Bootstrap na UI

## [0.3.0] — 2026-07-30

### Changed

- UI migrada para componentes Bootstrap (btn, form-control, card, table)

## [0.2.0] — 2026-07-30

### Added

- Badge de versão (`vX.Y.Z`) no canto inferior direito de todas as telas
- Script `scripts/bump_version.py` sincroniza `VERSION`, `pyproject.toml` e `CHANGELOG.md`
- Regra Cursor de versionamento automático (`.cursor/rules/versionamento.mdc`)
- Áudio nos agentes: upload/gravação no painel, mídia no WhatsApp, transcrição Whisper,
  persistência em `MensagemAgente.audio` e fallbacks (`tests/test_audio_agentes.py`)
- Bootstrap 5.3.8 + layout responsivo (hamburger/offcanvas no mobile)
- Regra de ouro de responsividade (`.cursor/rules/responsividade.mdc`, CONTRIBUTING)
- Semanas 5–6: Pix QR na OS/portal, recibo não fiscal, vínculo lançamento↔OS,
  relatórios (ticket/peças/conversão/margem), comissões, PWA, multi-usuário com papéis
- Semana 4: portal público OS/orçamento, aprovação pelo cliente, webhook WhatsApp, notificações pronta/entregue
- Semana 3: tools IA (orçamento por diagnóstico, status OS com confirmação)
- Busca em linguagem natural no painel (`/busca/`)
- Resumo diário automático ao dono via Celery Beat
- Fotos (até 10) e 1 vídeo stream nos orçamentos (Cloudflare R2 / S3-compatible)
- Suíte de testes por fase do roadmap (`tests/`)
- CI/CD com GitHub Actions (Ruff + testes)
- Validação de Conventional Commits em PRs
- Documentação em `docs/` (arquitetura, desenvolvimento, deploy, commits)
- CONTRIBUTING e template de mensagem de commit

### Changed

- Tipo do usuário (papel) exibido ao lado do nome na barra lateral

### Fixed

- Conversão de `Decimal` ao adicionar itens em OS e orçamentos via POST

## [0.1.0] — 2026-07-28

### Added

- Fundação Django 6 + HTMX + Neon
- Módulos: clientes, veículos, catálogo, orçamentos, OS, financeiro, agente IA
- Semana 2: CRUD UI, fornecedores, compras, baixa de estoque, checklist, fotos OS,
  conversão orçamento→OS, PDF, import CSV, seed demo
