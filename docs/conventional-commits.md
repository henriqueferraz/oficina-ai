# Conventional Commits

Este projeto usa [Conventional Commits](https://www.conventionalcommits.org/).

## Formato

```
<tipo>(escopo opcional): descrição curta

[corpo opcional]

[rodapé opcional]
```

- Descrição em **minúsculas** após o tipo
- Header ≤ 100 caracteres
- Use o imperativo: “adiciona”, “corrige”, não “adicionado”

## Tipos permitidos

| Tipo | Quando usar |
|------|-------------|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `docs` | Documentação |
| `style` | Formatação (sem mudança de lógica) |
| `refactor` | Refatoração |
| `perf` | Performance |
| `test` | Testes |
| `build` | Build / dependências |
| `ci` | CI/CD |
| `chore` | Manutenção diversa |
| `revert` | Reverte commit |

## Exemplos

```text
feat(orcamentos): permite até 10 fotos no R2 e 1 vídeo stream
fix(ordens): converte quantidade e valor para Decimal no POST
docs: adiciona guia de deploy com Cloudflare R2
test(semana2): cobre conversão de orçamento em OS
ci: adiciona workflow de lint e testes
chore: atualiza .env.example com variáveis R2
```

## Validação automática

Em todo Pull Request, o workflow **Conventional Commits**:

1. Valida mensagens dos commits (`commitlint`)
2. Valida o título do PR (`action-semantic-pull-request`)

## Setup local (opcional)

```bash
git config commit.template .gitmessage
```

Para validar um commit localmente (requer Node):

```bash
npx commitlint --from HEAD~1 --to HEAD --verbose
```
