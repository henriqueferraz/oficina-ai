"""Consulta à base FIPE local (SQLite em data/fipe.db)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

_ANO_RE = re.compile(r"^(\d{4})")


@dataclass(frozen=True)
class FipeMarca:
    id: int
    nome: str


@dataclass(frozen=True)
class FipeModelo:
    id: int
    nome: str
    marca_id: int


@dataclass(frozen=True)
class FipeAno:
    id: int
    codigo: str
    descricao: str
    ano: int | None
    modelo_id: int


def fipe_db_path() -> Path:
    configured = getattr(settings, "FIPE_DB_PATH", None) or ""
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "data" / "fipe.db"


def fipe_disponivel() -> bool:
    path = fipe_db_path()
    return path.is_file() and path.stat().st_size > 0


def _connect() -> sqlite3.Connection:
    path = fipe_db_path()
    if not path.is_file():
        raise FileNotFoundError(f"Base FIPE não encontrada: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def extrair_ano(descricao: str, codigo: str = "") -> int | None:
    """Extrai o ano (ex.: 2018) de '2018 Gasolina' ou código '2018-1'."""
    for raw in (descricao or "", codigo or ""):
        m = _ANO_RE.match(raw.strip())
        if m:
            ano = int(m.group(1))
            # FIPE usa 32000 para "Zero KM" em alguns registros
            if 1950 <= ano <= 2100:
                return ano
    return None


@lru_cache(maxsize=1)
def listar_marcas() -> tuple[FipeMarca, ...]:
    if not fipe_disponivel():
        return ()
    with _connect() as con:
        rows = con.execute("SELECT id, nome FROM marcas ORDER BY nome COLLATE NOCASE").fetchall()
    return tuple(FipeMarca(id=int(r["id"]), nome=r["nome"]) for r in rows)


def listar_modelos(marca_id: int) -> list[FipeModelo]:
    if not fipe_disponivel() or not marca_id:
        return []
    with _connect() as con:
        rows = con.execute(
            "SELECT id, nome, marca_id FROM modelos WHERE marca_id = ? ORDER BY nome COLLATE NOCASE",
            (marca_id,),
        ).fetchall()
    return [FipeModelo(id=int(r["id"]), nome=r["nome"], marca_id=int(r["marca_id"])) for r in rows]


def listar_anos(modelo_id: int) -> list[FipeAno]:
    if not fipe_disponivel() or not modelo_id:
        return []
    with _connect() as con:
        rows = con.execute(
            """
            SELECT id, codigo, descricao, modelo_id
            FROM anos
            WHERE modelo_id = ?
            ORDER BY codigo DESC
            """,
            (modelo_id,),
        ).fetchall()
    result: list[FipeAno] = []
    for r in rows:
        result.append(
            FipeAno(
                id=int(r["id"]),
                codigo=r["codigo"] or "",
                descricao=r["descricao"] or "",
                ano=extrair_ano(r["descricao"] or "", r["codigo"] or ""),
                modelo_id=int(r["modelo_id"]),
            )
        )
    return result


def encontrar_marca_por_nome(nome: str) -> FipeMarca | None:
    nome_n = (nome or "").strip().casefold()
    if not nome_n:
        return None
    for m in listar_marcas():
        if m.nome.casefold() == nome_n:
            return m
    return None


def encontrar_modelo_por_nome(marca_id: int, nome: str) -> FipeModelo | None:
    nome_n = (nome or "").strip().casefold()
    if not nome_n:
        return None
    for m in listar_modelos(marca_id):
        if m.nome.casefold() == nome_n:
            return m
    return None


def limpar_cache_fipe() -> None:
    listar_marcas.cache_clear()
