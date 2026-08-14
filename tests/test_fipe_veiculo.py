"""Testes da consulta FIPE local e endpoints de cascata."""

from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.fipe import (
    extrair_ano,
    limpar_cache_fipe,
    listar_anos,
    listar_marcas,
    listar_modelos,
)
from tests.helpers import criar_oficina_com_usuario

FIPE_PATH = Path(__file__).resolve().parents[1] / "data" / "fipe.db"


@override_settings(FIPE_DB_PATH=str(FIPE_PATH))
class FipeServiceTests(TestCase):
    def setUp(self):
        limpar_cache_fipe()

    def test_extrair_ano(self):
        self.assertEqual(extrair_ano("2018 Gasolina"), 2018)
        self.assertEqual(extrair_ano("1999 Diesel", "1999-3"), 1999)
        self.assertIsNone(extrair_ano("32000 Gasolina", "32000-1"))

    def test_listar_cascata(self):
        if not FIPE_PATH.is_file():
            self.skipTest("data/fipe.db ausente")
        marcas = listar_marcas()
        self.assertGreater(len(marcas), 0)
        modelos = listar_modelos(marcas[0].id)
        self.assertGreater(len(modelos), 0)
        anos = listar_anos(modelos[0].id)
        self.assertGreater(len(anos), 0)
        self.assertTrue(any(a.ano for a in anos))


@override_settings(FIPE_DB_PATH=str(FIPE_PATH))
class FipeEndpointsTests(TestCase):
    def setUp(self):
        limpar_cache_fipe()
        self.user, self.oficina = criar_oficina_com_usuario()
        self.client.login(username="dono", password="senha123")

    def test_modelos_e_anos(self):
        if not FIPE_PATH.is_file():
            self.skipTest("data/fipe.db ausente")
        marcas = listar_marcas()
        marca = marcas[0]
        r = self.client.get(reverse("core:fipe_modelos"), {"marca_id": marca.id})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Selecione o modelo")
        modelos = listar_modelos(marca.id)
        self.assertContains(r, modelos[0].nome)
        r2 = self.client.get(reverse("core:fipe_anos"), {"modelo_id": modelos[0].id})
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "Selecione o ano")
