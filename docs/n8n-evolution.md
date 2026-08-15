# n8n e Evolution API

O n8n é a fronteira entre a Evolution API e o Django. As credenciais, URL
administrativa e instância da Evolution API ficam somente no n8n.

## Variáveis Django

Configure no ambiente do Django:

```text
N8N_INBOUND_SECRET=<segredo-para-n8n-enviar-ao-django>
N8N_OUTBOUND_SECRET=<segredo-para-django-enviar-ao-n8n>
N8N_OUTBOUND_URL=https://n8n.exemplo.com/webhook/oficina-whatsapp-saida
N8N_EVOLUTION_INSTANCE=oficina-principal
N8N_WEBHOOK_MAX_AGE_SECONDS=300
N8N_MAX_MEDIA_BYTES=8388608
```

Use segredos distintos para cada sentido e faça rotação coordenada. O Django
nunca recebe token, URL privada ou chave da Evolution API.

## Workflow de entrada

1. Receba o evento da Evolution API no n8n e aceite apenas mensagens recebidas.
2. Normalize texto, áudio e imagem; descarte status, mensagens enviadas pela
   própria instância e eventos sem identificador de mensagem.
3. Baixe a mídia no n8n. Envie seu conteúdo em `midia_base64`; não envie URL ou
   token privado do provedor.
4. Faça `POST` para `/agentes/whatsapp/n8n/entrada/`.

O corpo tem este formato:

```json
{
  "evento_id": "execucao-ou-evento-n8n",
  "mensagem_id_provedor": "id-estavel-da-evolution",
  "instancia": "oficina-principal",
  "telefone": "5511999999999",
  "tipo": "text",
  "texto": "Preciso de um orcamento",
  "mime": "",
  "midia_base64": ""
}
```

Assine o corpo cru com os headers abaixo. O valor a assinar é
`<timestamp>.<corpo-cru>` e o algoritmo é HMAC-SHA256 com
`N8N_INBOUND_SECRET`.

```text
X-N8N-Timestamp: <epoch-em-segundos>
X-N8N-Signature: sha256=<assinatura-hexadecimal>
Content-Type: application/json
```

O `mensagem_id_provedor` é a chave de idempotência. O mesmo identificador pode
ser reenviado, mas não deve criar uma segunda mensagem, conversa ou operação.

## Workflow de saída

O Django envia `POST` assinado para `N8N_OUTBOUND_URL` com `telefone`, `texto` e
`instancia`. O n8n valida a assinatura usando `N8N_OUTBOUND_SECRET`, envia a
mensagem pela Evolution API e retorna HTTP 2xx apenas quando o provedor aceitar
o comando. Em caso de erro, retorne 4xx ou 5xx para que o Django registre a
falha e possa aplicar retry posteriormente.

Para callback de status, envie o mesmo esquema de assinatura de entrada para
`/agentes/whatsapp/n8n/entrega/` com, no mínimo:

```json
{"mensagem_id_provedor": "id-da-evolution", "status": "enviado"}
```

## Segurança e limites

- Rejeite eventos com timestamp fora de `N8N_WEBHOOK_MAX_AGE_SECONDS`.
- Não inclua `oficina_id`, IDs internos, permissões, valores ou segredos no
  evento de entrada.
- Configure limite de requisição no proxy e mantenha `N8N_MAX_MEDIA_BYTES`
  alinhado ao limite de upload do Django.
- Registre apenas identificadores técnicos e status; não grave tokens, URLs
  privadas ou conteúdo de mídia nos logs.
