"""
Semanas 5–6 — Diferenciação
Pix, recibo, vínculo financeiro, relatórios, comissões, papéis.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import PerfilUsuario
from apps.core.pix import montar_payload_pix, pix_para_ordem
from apps.core.relatorios import comissoes_por_mecanico, conversao_orcamento_os, ticket_medio
from apps.financeiro.models import Lancamento
from apps.orcamentos.models import Orcamento
from apps.ordens.models import OrdemItem, OrdemServico
from tests.helpers import (
    criar_cliente,
    criar_oficina_com_usuario,
    criar_orcamento,
    criar_ordem,
    criar_peca,
    criar_veiculo,
    papel_da_oficina,
)


class Semana56DiferenciacaoTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.oficina.pix_chave = "11999999999"
        self.oficina.pix_nome = "OFICINA TESTE"
        self.oficina.cidade = "Sao Paulo"
        self.oficina.comissao_padrao_percentual = Decimal("10.00")
        self.oficina.save()
        self.cliente = criar_cliente(self.oficina)
        self.veiculo = criar_veiculo(self.oficina, self.cliente)
        self.ordem = criar_ordem(
            self.oficina,
            self.cliente,
            veiculo=self.veiculo,
            numero=1,
            diagnostico="Troca de pastilha",
        )
        OrdemItem.objects.create(
            ordem=self.ordem,
            tipo=OrdemItem.Tipo.SERVICO,
            descricao="Serviço teste",
            quantidade=Decimal("1"),
            valor_unitario=Decimal("200.00"),
        )
        self.client.login(username="dono", password="senha123")

    def test_pix_qr_na_os(self):
        """OS exibe QR Code Pix para pagamento."""
        pix = pix_para_ordem(self.ordem)
        self.assertIsNotNone(pix)
        self.assertIn("br.gov.bcb.pix", pix["payload"])
        self.assertTrue(pix["qr_data_uri"].startswith("data:image/png;base64,"))

        resp = self.client.get(reverse("ordens:detalhe", kwargs={"pk": self.ordem.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pagamento Pix")
        self.assertContains(resp, "QR Code Pix")
        self.assertContains(resp, pix["payload"][:20])

        # Portal público também mostra Pix
        url = reverse("portal:os_publica", kwargs={"token": self.ordem.token_publico})
        anon = Client()
        resp = anon.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pagar com Pix")

        payload = montar_payload_pix(
            chave="email@teste.com",
            nome="TESTE",
            cidade="SAO PAULO",
            valor=Decimal("10.50"),
            txid="OS1",
        )
        self.assertTrue(payload.startswith("000201"))
        self.assertIn("6304", payload)
        self.assertEqual(len(payload[-4:]), 4)

    def test_recibo_nao_fiscal(self):
        """Gera recibo/cupom simples sem NF-e."""
        url = reverse("ordens:recibo", kwargs={"pk": self.ordem.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", resp.content[:8])
        self.assertIn("recibo", resp["Content-Disposition"].lower())

    def test_vinculo_lancamento_os(self):
        """Lançamento financeiro associa OS na UI."""
        url = reverse("financeiro:criar")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ordem de serviço")
        self.assertContains(resp, f"OS #{self.ordem.numero}")

        resp = self.client.post(
            url,
            {
                "tipo": Lancamento.Tipo.RECEITA,
                "descricao": "Pagamento OS",
                "valor": "200.00",
                "forma": Lancamento.Forma.PIX,
                "data": timezone.localdate().isoformat(),
                "pago": "on",
                "ordem": str(self.ordem.pk),
            },
        )
        self.assertEqual(resp.status_code, 302)
        lanc = Lancamento.objects.get(descricao="Pagamento OS")
        self.assertEqual(lanc.ordem_id, self.ordem.pk)

        lista = self.client.get(reverse("financeiro:lista"))
        self.assertContains(lista, f"#{self.ordem.numero}")

    def test_relatorios_operacionais(self):
        """Relatórios: ticket médio, peças mais usadas, conversão."""
        peca = criar_peca(self.oficina, nome="Pastilha", estoque="20", preco="80.00", custo="40.00")
        OrdemItem.objects.create(
            ordem=self.ordem,
            tipo=OrdemItem.Tipo.PECA,
            descricao=peca.nome,
            quantidade=Decimal("2"),
            valor_unitario=Decimal("80.00"),
            peca=peca,
        )
        self.ordem.status = OrdemServico.Status.ENTREGUE
        self.ordem.save(update_fields=["status"])

        orc = criar_orcamento(self.oficina, self.cliente, veiculo=self.veiculo, numero=1)
        orc.status = Orcamento.Status.CONVERTIDO
        orc.save(update_fields=["status"])
        criar_orcamento(
            self.oficina,
            self.cliente,
            veiculo=self.veiculo,
            numero=2,
            status=Orcamento.Status.ENVIADO,
        )

        self.assertGreater(ticket_medio(self.oficina), 0)
        conv = conversao_orcamento_os(self.oficina)
        self.assertEqual(conv["total"], 2)
        self.assertEqual(conv["convertidos"], 1)
        self.assertEqual(conv["taxa_percentual"], Decimal("50.00"))

        resp = self.client.get(reverse("core:relatorios"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ticket médio")
        self.assertContains(resp, "Pastilha")
        self.assertContains(resp, "50,00%")

        dash = self.client.get(reverse("core:dashboard"))
        self.assertContains(dash, "Conversão")
        self.assertContains(dash, "Margem")

    def test_comissoes_mecanico(self):
        """Calcula comissão por mecânico responsável."""
        User = get_user_model()
        mec = User.objects.create_user(username="mec1", password="senha123")
        PerfilUsuario.objects.create(
            user=mec,
            oficina=self.oficina,
            papel=papel_da_oficina(self.oficina, "mecanico"),
            comissao_percentual=Decimal("15.00"),
        )
        self.ordem.responsavel = mec
        self.ordem.status = OrdemServico.Status.ENTREGUE
        self.ordem.save(update_fields=["responsavel", "status"])

        comps = comissoes_por_mecanico(self.oficina)
        self.assertTrue(comps)
        alvo = next(c for c in comps if c["user"].id == mec.id)
        self.assertEqual(alvo["ordens"], 1)
        self.assertEqual(alvo["percentual"], Decimal("15.00"))
        self.assertEqual(alvo["comissao"], Decimal("30.00"))  # 15% de 200

        resp = self.client.get(reverse("core:comissoes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mec1")
        self.assertContains(resp, "30,00")

    def test_multi_usuario_papeis(self):
        """Papéis dono/recepção/mecânico restringem rotas."""
        User = get_user_model()
        mec = User.objects.create_user(username="mecanico", password="senha123")
        papel_mec = papel_da_oficina(self.oficina, "mecanico")
        papel_dono = papel_da_oficina(self.oficina, "dono")
        papel_recep = papel_da_oficina(self.oficina, "recepcao")
        PerfilUsuario.objects.create(
            user=mec,
            oficina=self.oficina,
            papel=papel_mec,
        )

        # Mecânico acessa OS
        self.client.logout()
        self.assertTrue(self.client.login(username="mecanico", password="senha123"))
        resp = self.client.get(reverse("ordens:detalhe", kwargs={"pk": self.ordem.pk}))
        self.assertEqual(resp.status_code, 200)

        # Mecânico acessa equipe (próprio perfil), mas não financeiro / relatórios / config
        resp = self.client.get(reverse("core:equipe"))
        self.assertEqual(resp.status_code, 200)
        for name in ("financeiro:lista", "core:relatorios", "core:configuracoes"):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302, msg=name)
            self.assertEqual(resp.url, reverse("core:dashboard"))

        # Mecânico não cria usuário
        resp = self.client.post(
            reverse("core:equipe"),
            {
                "acao": "criar",
                "username": "hacker",
                "password": "SenhaForte99",
                "papel": str(papel_dono.pk),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PerfilUsuario.objects.filter(user__username="hacker").exists())

        # Dono cria usuário pela UI de equipe
        self.client.logout()
        self.client.login(username="dono", password="senha123")
        resp = self.client.post(
            reverse("core:equipe"),
            {
                "acao": "criar",
                "username": "recep1",
                "password": "SenhaForte99",
                "papel": str(papel_recep.pk),
                "telefone": "11911112222",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            PerfilUsuario.objects.filter(
                user__username="recep1",
                papel=papel_recep,
                oficina=self.oficina,
            ).exists()
        )

        # PWA manifest e service worker
        manifest = self.client.get(reverse("core:pwa_manifest"))
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest["Content-Type"], "application/manifest+json")
        self.assertEqual(manifest.json()["name"], "Oficina AI")
        sw = self.client.get(reverse("core:pwa_sw"))
        self.assertEqual(sw.status_code, 200)
        self.assertIn(b"CACHE", sw.content)
        self.assertIn(b"oficina-ai-v3", sw.content)
        self.assertNotIn(b"ASSETS = ['/'", sw.content)
        self.assertNotIn(b"/static/css/app.css", sw.content)
        self.assertIn(b"fetch(req).then", sw.content)

    def test_equipe_redefinir_senha(self):
        """Dono pode redefinir senha de membro da equipe."""
        User = get_user_model()
        mec = User.objects.create_user(username="mec_senha", password="senhaantiga")
        papel_mec = papel_da_oficina(self.oficina, "mecanico")
        perfil = PerfilUsuario.objects.create(
            user=mec,
            oficina=self.oficina,
            papel=papel_mec,
        )

        resp = self.client.get(reverse("core:equipe"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Salvar alterações")
        self.assertContains(resp, "membroModal")
        self.assertContains(resp, "data-bs-toggle")

        resp = self.client.post(
            reverse("core:equipe"),
            {
                "acao": "atualizar",
                "perfil_id": perfil.pk,
                "username": "mec_senha",
                "telefone": "",
                "papel": str(papel_mec.pk),
                "nova_senha": "novaSenha99",
                "nova_senha_confirma": "novaSenha99",
                "ativo": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        mec.refresh_from_db()
        self.assertTrue(mec.check_password("novaSenha99"))
        self.assertFalse(mec.check_password("senhaantiga"))

        # Login case-insensitive
        self.client.logout()
        self.assertTrue(self.client.login(username="MEC_SENHA", password="novaSenha99"))

    def test_equipe_membro_edita_proprio_perfil(self):
        """Membro edita usuário/telefone/senha; não altera papel."""
        User = get_user_model()
        mec = User.objects.create_user(username="mec_perfil", password="senha123")
        papel_mec = papel_da_oficina(self.oficina, "mecanico")
        papel_dono = papel_da_oficina(self.oficina, "dono")
        perfil = PerfilUsuario.objects.create(
            user=mec,
            oficina=self.oficina,
            papel=papel_mec,
            telefone="11999990000",
            comissao_percentual=Decimal("10.00"),
        )
        self.client.logout()
        self.assertTrue(self.client.login(username="mec_perfil", password="senha123"))

        resp = self.client.post(
            reverse("core:equipe"),
            {
                "acao": "atualizar",
                "perfil_id": perfil.pk,
                "username": "mec_novo",
                "telefone": "11988887777",
                "papel": str(papel_dono.pk),  # deve ser ignorado
                "comissao_percentual": "99",
                "nova_senha": "OutraSenha99",
                "nova_senha_confirma": "OutraSenha99",
            },
        )
        self.assertEqual(resp.status_code, 302)
        perfil.refresh_from_db()
        mec.refresh_from_db()
        self.assertEqual(mec.username, "mec_novo")
        self.assertEqual(perfil.telefone, "(11) 98888-7777")
        self.assertEqual(perfil.papel_id, papel_mec.id)
        self.assertEqual(perfil.comissao_percentual, Decimal("10.00"))
        self.assertTrue(mec.check_password("OutraSenha99"))

    def test_configuracoes_oficina_cnpj_e_dados(self):
        """Configurações salvam dados da oficina e rejeitam CNPJ inválido."""
        from apps.core.validators import cnpj_valido

        self.assertTrue(cnpj_valido("04.252.011/0001-10"))
        self.assertFalse(cnpj_valido("11.111.111/1111-11"))

        resp = self.client.get(reverse("core:configuracoes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nome da oficina")
        self.assertContains(resp, "Logomarca")

        resp = self.client.post(
            reverse("core:configuracoes"),
            {
                "acao": "salvar_oficina",
                "nome": "Oficina Nova",
                "cnpj": "00.000.000/0000-00",
                "telefone": "11999990000",
                "email": "contato@oficina.test",
                "cep": "01001-000",
                "endereco": "Rua A, 100",
                "bairro": "Centro",
                "cidade": "Sao Paulo",
                "uf": "SP",
                "pix_chave": "contato@oficina.test",
                "pix_nome": "OFICINA NOVA",
                "comissao_padrao_percentual": "12.5",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.oficina.refresh_from_db()
        self.assertNotEqual(self.oficina.nome, "Oficina Nova")

        resp = self.client.post(
            reverse("core:configuracoes"),
            {
                "acao": "salvar_oficina",
                "nome": "Oficina Nova",
                "cnpj": "04.252.011/0001-10",
                "telefone": "11999990000",
                "email": "contato@oficina.test",
                "cep": "01001-000",
                "endereco": "Rua A, 100",
                "bairro": "Centro",
                "cidade": "Sao Paulo",
                "uf": "SP",
                "pix_chave": "contato@oficina.test",
                "pix_nome": "OFICINA NOVA",
                "comissao_padrao_percentual": "12.5",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.oficina.refresh_from_db()
        self.assertEqual(self.oficina.nome, "Oficina Nova")
        self.assertEqual(self.oficina.cnpj, "04.252.011/0001-10")
        self.assertEqual(self.oficina.bairro, "Centro")
        self.assertEqual(self.oficina.comissao_padrao_percentual, Decimal("12.50"))

    def test_configuracoes_cria_papel_e_matriz(self):
        """Admin cria papel custom e ajusta permissões; usuário herda acesso."""
        from apps.accounts.models import PapelOficina
        from apps.accounts.permissions import user_pode

        resp = self.client.get(reverse("core:configuracoes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Papéis e permissões")
        self.assertContains(resp, "Novo papel")

        resp = self.client.post(
            reverse("core:configuracoes"),
            {
                "acao": "criar_papel",
                "nome_papel": "Ajudante",
                "perm_novo": ["clientes", "ordens"],
            },
        )
        self.assertEqual(resp.status_code, 302)
        papel = PapelOficina.objects.get(oficina=self.oficina, nome="Ajudante")
        self.assertIn("clientes", papel.permissoes)
        self.assertIn("ordens", papel.permissoes)
        self.assertNotIn("configuracoes", papel.permissoes)

        # Atualiza matriz: remove clientes, adiciona agente
        resp = self.client.post(
            reverse("core:configuracoes"),
            {
                "acao": "salvar_papeis",
                f"nome_{papel.pk}": "Ajudante Jr",
                f"perm_{papel.pk}": ["ordens", "agente"],
                f"ativo_{papel.pk}": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        papel.refresh_from_db()
        self.assertEqual(papel.nome, "Ajudante Jr")
        self.assertEqual(set(papel.permissoes), {"ordens", "agente"})

        User = get_user_model()
        ajud = User.objects.create_user(username="ajud1", password="senha123")
        PerfilUsuario.objects.create(user=ajud, oficina=self.oficina, papel=papel)

        self.client.logout()
        self.assertTrue(self.client.login(username="ajud1", password="senha123"))
        self.assertTrue(user_pode(ajud, "ordens"))
        self.assertTrue(user_pode(ajud, "agente"))
        self.assertFalse(user_pode(ajud, "clientes"))
        self.assertFalse(user_pode(ajud, "financeiro"))

        resp = self.client.get(reverse("core:clientes"))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse("agentes:painel"))
        self.assertEqual(resp.status_code, 200)

        # Mecânico default: sem caixa/recentes/estoque e sem cadastros
        mec_papel = papel_da_oficina(self.oficina, "mecanico")
        mec = User.objects.create_user(username="mec_ui", password="senha123")
        PerfilUsuario.objects.create(user=mec, oficina=self.oficina, papel=mec_papel)
        self.client.logout()
        self.assertTrue(self.client.login(username="mec_ui", password="senha123"))
        dash = self.client.get(reverse("core:dashboard"))
        self.assertEqual(dash.status_code, 200)
        self.assertNotContains(dash, 'class="label">Caixa')
        self.assertNotContains(dash, "Ordens recentes")
        self.assertNotContains(dash, "Estoque baixo")
        self.assertNotContains(dash, "Agente IA")
        self.assertEqual(self.client.get(reverse("core:clientes")).status_code, 302)
        self.assertEqual(self.client.get(reverse("agentes:painel")).status_code, 302)
