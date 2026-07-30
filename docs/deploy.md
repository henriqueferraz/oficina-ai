# Deploy

## Variáveis de ambiente

Copie de `.env.example`. Principais:

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SECRET_KEY` | sim | Chave Django |
| `DEBUG` | sim | `False` em produção |
| `ALLOWED_HOSTS` | sim | Domínios separados por vírgula |
| `CSRF_TRUSTED_ORIGINS` | sim (HTTPS) | Origens com esquema, ex. `https://app.seudominio.com` |
| `DATABASE_URL` | sim | Postgres (Neon ou EasyPanel) |
| `OPENAI_API_KEY` | não | Agente IA + transcrição de áudio |
| `OPENAI_TRANSCRIPTION_MODEL` | não | Default `whisper-1` |
| `AWS_STORAGE_BUCKET_NAME` | não | Bucket R2 |
| `AWS_S3_ENDPOINT_URL` | com R2 | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | com R2 | API Token R2 |
| `AWS_S3_CUSTOM_DOMAIN` | não | Domínio público das mídias |
| `AWS_QUERYSTRING_AUTH` | não | `False` se bucket/domínio público |
| `CELERY_BROKER_URL` | não | Redis em produção |
| `CELERY_TASK_ALWAYS_EAGER` | não | `False` com worker real |
| `DEFAULT_FROM_EMAIL` | não | Remetente do resumo diário |
| `EMAIL_BACKEND` / SMTP | não | E-mail em produção (resumo diário) |
| `PUBLIC_BASE_URL` | não | Base dos links públicos (e-mail/WhatsApp) |
| `WHATSAPP_VERIFY_TOKEN` | webhook | Verificação Meta |
| `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp real | Cloud API |
| `WHATSAPP_DRY_RUN` | não | `True` = não chama Graph API |

## EasyPanel (VPS)

O repo inclui `Dockerfile` e `.dockerignore` para deploy via App Service.

1. Crie um **Project** no EasyPanel.
2. Adicione um serviço **App** → Source **GitHub** → branch de produção.
3. Build: **Dockerfile** (caminho `Dockerfile`). Porta: `8000` (ou confie em `$PORT`).
4. Configure as env vars (mínimo):

```text
SECRET_KEY=<forte>
DEBUG=False
ALLOWED_HOSTS=seu-dominio.com,www.seu-dominio.com
CSRF_TRUSTED_ORIGINS=https://seu-dominio.com,https://www.seu-dominio.com
DATABASE_URL=postgresql://...
PUBLIC_BASE_URL=https://seu-dominio.com
CELERY_TASK_ALWAYS_EAGER=True
```

5. Aba **Domains**: domínio + HTTPS (Let’s Encrypt). DNS **A** → IP da VPS.
6. **Deploy**. O container roda `migrate`, `collectstatic` e Gunicorn.

Opcional no mesmo projeto: serviço **Postgres** (monte o `DATABASE_URL`) e **Redis** + worker Celery se for sair do modo eager.

Fotos: configure R2 (`AWS_*`) ou monte um volume persistente em `/app/media`.

## Cloudflare R2

1. Crie um bucket no R2.
2. Gere API Token (Object Read & Write).
3. Em Overview do R2, copie o **S3 API** endpoint (`…r2.cloudflarestorage.com`).
4. (Recomendado) Configure Custom Domain ou r2.dev e use `AWS_S3_CUSTOM_DOMAIN`.
5. Preencha as vars `AWS_*` no ambiente de produção.

## Checklist de produção

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` forte
- [ ] `ALLOWED_HOSTS` correto
- [ ] `CSRF_TRUSTED_ORIGINS` com `https://...`
- [ ] Postgres Neon (ou EasyPanel) com SSL
- [ ] `collectstatic` + WhiteNoise (Dockerfile já executa)
- [ ] R2 configurado para fotos (ou volume em `media/`)
- [ ] HTTPS no reverse proxy
- [ ] (Opcional) Redis + Celery worker + beat (resumo diário 07:00)
- [ ] (Opcional) SMTP / `DEFAULT_FROM_EMAIL` para e-mails

## Processo sugerido (sem EasyPanel)

```bash
uv sync --no-dev
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput
uv run gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Ajuste plataforma (Railway, Render, Fly.io, VPS) conforme o host escolhido. O CI atual valida lint e testes; o deploy em si fica a cargo da plataforma conectada ao `main`.
