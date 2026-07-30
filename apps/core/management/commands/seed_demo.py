from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import PerfilUsuario
from apps.accounts.permissions import garantir_papeis_padrao
from apps.core.models import Cliente, Fornecedor, Oficina, Peca, Servico, Veiculo
from apps.core.services import registrar_compra
from apps.financeiro.models import Lancamento
from apps.orcamentos.models import Orcamento, OrcamentoItem
from apps.ordens.models import CHECKLIST_PADRAO, ChecklistItem, OrdemItem, OrdemServico


class Command(BaseCommand):
    help = "Popula dados demo para a oficina do usuário (ou cria oficina demo)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="demo",
            help="Usuário dono da oficina (criado se não existir). Default: demo",
        )
        parser.add_argument(
            "--password",
            default="demo1234",
            help="Senha do usuário demo. Default: demo1234",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Apaga dados operacionais da oficina antes de popular.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@oficina.ai"},
        )
        if created or options["reset"]:
            user.set_password(password)
            user.save()

        perfil, _ = PerfilUsuario.objects.get_or_create(user=user, defaults={})
        if not perfil.oficina:
            oficina = Oficina.objects.create(
                nome="Oficina Demo Funilaria",
                telefone="11999990000",
                cidade="São Paulo",
                uf="SP",
            )
            perfil.oficina = oficina
            perfil.save(update_fields=["oficina"])
        oficina = perfil.oficina
        papeis = garantir_papeis_padrao(oficina)
        if perfil.papel_id != papeis["dono"].id:
            perfil.papel = papeis["dono"]
            perfil.save(update_fields=["papel"])

        if options["reset"]:
            OrdemServico.objects.filter(oficina=oficina).delete()
            Orcamento.objects.filter(oficina=oficina).delete()
            Lancamento.objects.filter(oficina=oficina).delete()
            Veiculo.objects.filter(oficina=oficina).delete()
            Cliente.objects.filter(oficina=oficina).delete()
            Peca.objects.filter(oficina=oficina).delete()
            Servico.objects.filter(oficina=oficina).delete()
            Fornecedor.objects.filter(oficina=oficina).delete()

        if Cliente.objects.filter(oficina=oficina).exists() and not options["reset"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Oficina '{oficina.nome}' já tem dados. Use --reset para repovoar."
                )
            )
            self.stdout.write(f"Login: {username} / {password}")
            return

        fornecedor = Fornecedor.objects.create(
            oficina=oficina,
            nome="Auto Peças Brasil",
            telefone="1133334444",
            documento="12.345.678/0001-90",
        )
        clientes = [
            Cliente.objects.create(
                oficina=oficina,
                nome="Maria Souza",
                telefone="11988887777",
                documento="123.456.789-00",
                email="maria@email.com",
            ),
            Cliente.objects.create(
                oficina=oficina,
                nome="José Oliveira",
                telefone="11977776666",
                documento="987.654.321-00",
            ),
            Cliente.objects.create(
                oficina=oficina,
                nome="Transportadora Norte",
                telefone="1144445555",
                documento="98.765.432/0001-10",
            ),
        ]
        veiculos = [
            Veiculo.objects.create(
                oficina=oficina,
                cliente=clientes[0],
                placa="ABC1D23",
                marca="VW",
                modelo="Gol",
                ano=2018,
                cor="Prata",
                km=62000,
            ),
            Veiculo.objects.create(
                oficina=oficina,
                cliente=clientes[1],
                placa="EFG4H56",
                marca="Fiat",
                modelo="Argo",
                ano=2021,
                cor="Branco",
                km=28000,
            ),
            Veiculo.objects.create(
                oficina=oficina,
                cliente=clientes[2],
                placa="XYZ9K87",
                marca="Ford",
                modelo="Ranger",
                ano=2019,
                cor="Preto",
                km=91000,
            ),
        ]

        servicos = [
            Servico.objects.create(
                oficina=oficina,
                nome="Funilaria — porta dianteira",
                preco=Decimal("450.00"),
                tempo_estimado_min=180,
            ),
            Servico.objects.create(
                oficina=oficina,
                nome="Pintura — para-lama",
                preco=Decimal("680.00"),
                tempo_estimado_min=240,
            ),
            Servico.objects.create(
                oficina=oficina,
                nome="Polimento técnico",
                preco=Decimal("220.00"),
                tempo_estimado_min=90,
            ),
        ]
        pecas = [
            Peca.objects.create(
                oficina=oficina,
                fornecedor=fornecedor,
                codigo="PRT-01",
                nome="Parachoque dianteiro Gol",
                custo=Decimal("280.00"),
                preco=Decimal("420.00"),
                estoque=Decimal("2"),
                estoque_minimo=Decimal("1"),
            ),
            Peca.objects.create(
                oficina=oficina,
                fornecedor=fornecedor,
                codigo="TNT-AZ",
                nome="Tinta automotiva prata (L)",
                custo=Decimal("95.00"),
                preco=Decimal("160.00"),
                estoque=Decimal("5"),
                estoque_minimo=Decimal("2"),
            ),
            Peca.objects.create(
                oficina=oficina,
                fornecedor=fornecedor,
                codigo="MAS-01",
                nome="Massa plástica 1kg",
                custo=Decimal("35.00"),
                preco=Decimal("55.00"),
                estoque=Decimal("8"),
                estoque_minimo=Decimal("3"),
            ),
        ]

        registrar_compra(
            oficina=oficina,
            fornecedor=fornecedor,
            data=date.today(),
            observacoes="Reposição inicial demo",
            itens=[
                {
                    "peca_id": pecas[1].pk,
                    "quantidade": Decimal("3"),
                    "custo_unitario": Decimal("95.00"),
                }
            ],
        )

        orc = Orcamento.objects.create(
            oficina=oficina,
            cliente=clientes[0],
            veiculo=veiculos[0],
            numero=1,
            status=Orcamento.Status.APROVADO,
            observacoes="Batida leve na porta direita",
        )
        OrcamentoItem.objects.create(
            orcamento=orc,
            tipo=OrcamentoItem.Tipo.SERVICO,
            descricao=servicos[0].nome,
            quantidade=1,
            valor_unitario=servicos[0].preco,
            servico=servicos[0],
        )
        OrcamentoItem.objects.create(
            orcamento=orc,
            tipo=OrcamentoItem.Tipo.PECA,
            descricao=pecas[2].nome,
            quantidade=1,
            valor_unitario=pecas[2].preco,
            peca=pecas[2],
        )

        ordem = OrdemServico.objects.create(
            oficina=oficina,
            cliente=clientes[1],
            veiculo=veiculos[1],
            numero=1,
            status=OrdemServico.Status.EM_ANDAMENTO,
            prioridade=OrdemServico.Prioridade.ALTA,
            diagnostico="Risco no para-lama esquerdo",
        )
        OrdemItem.objects.create(
            ordem=ordem,
            tipo=OrdemItem.Tipo.SERVICO,
            descricao=servicos[1].nome,
            quantidade=1,
            valor_unitario=servicos[1].preco,
            servico=servicos[1],
        )
        OrdemItem.objects.create(
            ordem=ordem,
            tipo=OrdemItem.Tipo.PECA,
            descricao=pecas[1].nome,
            quantidade=1,
            valor_unitario=pecas[1].preco,
            peca=pecas[1],
        )
        ChecklistItem.objects.bulk_create(
            [
                ChecklistItem(
                    ordem=ordem,
                    momento=ChecklistItem.Momento.ENTRADA,
                    item=nome,
                )
                for nome in CHECKLIST_PADRAO
            ]
        )

        Lancamento.objects.create(
            oficina=oficina,
            tipo=Lancamento.Tipo.RECEITA,
            descricao="Entrada parcial OS #1",
            valor=Decimal("300.00"),
            forma=Lancamento.Forma.PIX,
            data=date.today(),
            pago=True,
            ordem=ordem,
        )
        Lancamento.objects.create(
            oficina=oficina,
            tipo=Lancamento.Tipo.DESPESA,
            descricao="Compra tinta",
            valor=Decimal("285.00"),
            forma=Lancamento.Forma.PIX,
            data=date.today(),
            pago=True,
        )

        self.stdout.write(self.style.SUCCESS(f"Seed OK — oficina '{oficina.nome}'"))
        self.stdout.write(f"Login: {username} / {password}")
