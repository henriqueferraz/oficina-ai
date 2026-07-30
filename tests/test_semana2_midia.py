"""
Semana 2 (extensão) — Mídia do orçamento
Até 10 fotos + 1 vídeo (YouTube/Vimeo/stream).
"""

from django.test import Client, TestCase
from django.urls import reverse

from apps.orcamentos.models import MAX_FOTOS_ORCAMENTO, OrcamentoFoto
from tests.helpers import (
    criar_cliente,
    criar_oficina_com_usuario,
    criar_orcamento,
    png_minima,
)


class Semana2MidiaOrcamentoTests(TestCase):
    def setUp(self):
        self.user, self.oficina = criar_oficina_com_usuario()
        self.cliente = criar_cliente(self.oficina)
        self.orc = criar_orcamento(self.oficina, self.cliente)
        self.client = Client()
        self.client.login(username="dono", password="senha123")

    def test_upload_foto(self):
        r = self.client.post(
            reverse("orcamentos:foto_upload", args=[self.orc.pk]),
            {"imagens": png_minima(), "legenda": "Porta direita"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.orc.fotos.count(), 1)
        self.assertEqual(self.orc.fotos.first().legenda, "Porta direita")

    def test_limite_10_fotos(self):
        for i in range(MAX_FOTOS_ORCAMENTO):
            OrcamentoFoto.objects.create(
                orcamento=self.orc, imagem=png_minima(f"f{i}.png"), legenda=str(i)
            )
        self.assertEqual(self.orc.fotos_restantes, 0)
        r = self.client.post(
            reverse("orcamentos:foto_upload", args=[self.orc.pk]),
            {"imagens": png_minima("extra.png")},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.orc.fotos.count(), MAX_FOTOS_ORCAMENTO)

    def test_remover_foto(self):
        foto = OrcamentoFoto.objects.create(orcamento=self.orc, imagem=png_minima(), legenda="x")
        r = self.client.post(reverse("orcamentos:foto_delete", args=[self.orc.pk, foto.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.orc.fotos.count(), 0)

    def test_salvar_video_youtube_embed(self):
        r = self.client.post(
            reverse("orcamentos:video_salvar", args=[self.orc.pk]),
            {
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "video_titulo": "Inspeção",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.orc.refresh_from_db()
        self.assertIn("embed/dQw4w9WgXcQ", self.orc.video_embed_url)
        self.assertEqual(self.orc.video_titulo, "Inspeção")

    def test_video_vimeo_e_stream_generico(self):
        self.orc.video_url = "https://vimeo.com/987654321"
        self.assertIn("player.vimeo.com/video/987654321", self.orc.video_embed_url)

        self.orc.video_url = "https://cdn.exemplo.com/video.m3u8"
        self.assertEqual(self.orc.video_embed_url, "")

    def test_remover_video(self):
        self.orc.video_url = "https://youtu.be/abc123"
        self.orc.video_titulo = "x"
        self.orc.save()
        r = self.client.post(
            reverse("orcamentos:video_salvar", args=[self.orc.pk]),
            {"video_url": "", "video_titulo": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.orc.refresh_from_db()
        self.assertEqual(self.orc.video_url, "")
