"""Carrega a base FIPE local (data/fipe.db) a partir da API pública da FIPE.

Idempotente e retomável: só busca o que falta, então pode ser interrompido e
rodado de novo. Ao final sai do modo WAL e compacta o arquivo, porque a base é
distribuída junto do código e aberta em modo somente-leitura em produção.

Exemplos:
    uv run python manage.py carregar_fipe
    uv run python manage.py carregar_fipe --marca Fiat --marca 59
    uv run python manage.py carregar_fipe --tipo motos --db data/fipe_motos.db
"""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.fipe import fipe_db_path

API_BASE = "https://parallelum.com.br/fipe/api/v1"
TIPOS = ("carros", "motos", "caminhoes")

DDL = (
    """
    CREATE TABLE IF NOT EXISTS marcas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo INTEGER UNIQUE NOT NULL,
        nome TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS modelos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo INTEGER NOT NULL,
        marca_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        UNIQUE(codigo, marca_id),
        FOREIGN KEY(marca_id) REFERENCES marcas(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS anos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        modelo_id INTEGER NOT NULL,
        UNIQUE(codigo, modelo_id),
        FOREIGN KEY(modelo_id) REFERENCES modelos(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_marca ON modelos(marca_id)",
    "CREATE INDEX IF NOT EXISTS idx_modelo ON anos(modelo_id)",
)


class Command(BaseCommand):
    help = "Carrega marcas, modelos e anos da FIPE em data/fipe.db (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tipo",
            default="carros",
            choices=TIPOS,
            help="Tipo de veículo na API FIPE (default: carros).",
        )
        parser.add_argument(
            "--db",
            default="",
            help="Caminho do SQLite de saída (default: settings.FIPE_DB_PATH).",
        )
        parser.add_argument(
            "--marca",
            action="append",
            default=[],
            help="Limita a uma marca (código ou nome). Pode repetir.",
        )
        parser.add_argument(
            "--paralelo",
            type=int,
            default=4,
            help="Requisições simultâneas na busca de anos (default: 4).",
        )
        parser.add_argument(
            "--pausa",
            type=float,
            default=0.05,
            help="Pausa em segundos entre requisições (default: 0.05).",
        )
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Rebusca anos de modelos que já têm registros.",
        )
        parser.add_argument(
            "--manter-wal",
            action="store_true",
            help="Não converte o arquivo final para journal_mode=DELETE.",
        )

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, url: str, *, tentativas: int = 5):
        """GET com backoff em 429/5xx. Retorna JSON ou None."""
        import httpx

        espera = 1.0
        for tentativa in range(1, tentativas + 1):
            try:
                resp = self.http.get(url, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 500, 502, 503, 504):
                    if tentativa == tentativas:
                        self.stderr.write(f"  ! {resp.status_code} em {url} (desisti)")
                        return None
                    time.sleep(espera)
                    espera = min(espera * 2, 30)
                    continue
                self.stderr.write(f"  ! HTTP {resp.status_code} em {url}")
                return None
            except (httpx.HTTPError, ValueError) as exc:
                if tentativa == tentativas:
                    self.stderr.write(f"  ! falha em {url}: {exc}")
                    return None
                time.sleep(espera)
                espera = min(espera * 2, 30)
        return None

    # ── Comando ───────────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        import httpx

        tipo = opts["tipo"]
        destino = Path(opts["db"]) if opts["db"] else fipe_db_path()
        destino.parent.mkdir(parents=True, exist_ok=True)
        self.pausa = max(opts["pausa"], 0.0)
        paralelo = max(opts["paralelo"], 1)

        with (
            httpx.Client(headers={"User-Agent": "oficina-ai/fipe-loader"}) as http,
            closing(sqlite3.connect(destino)) as con,
        ):
            self.http = http
            con.row_factory = sqlite3.Row
            for stmt in DDL:
                con.execute(stmt)
            con.commit()

            marcas = self._sincronizar_marcas(con, tipo, opts["marca"])
            if not marcas:
                raise CommandError("Nenhuma marca para processar.")

            total_modelos = 0
            total_anos = 0
            for i, marca in enumerate(marcas, start=1):
                self.stdout.write(f"[{i}/{len(marcas)}] {marca['nome']} (código {marca['codigo']})")
                modelos = self._sincronizar_modelos(con, tipo, marca)
                total_modelos += len(modelos)
                pendentes = self._modelos_pendentes(con, modelos, forcar=opts["forcar"])
                if pendentes:
                    total_anos += self._sincronizar_anos(con, tipo, marca, pendentes, paralelo)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Marcas: {len(marcas)} · modelos vistos: {total_modelos} "
                    f"· anos novos: {total_anos}"
                )
            )
            self._resumo(con)
            if not opts["manter_wal"]:
                self._compactar(con, destino)

    # ── Etapas ────────────────────────────────────────────────────────────────

    def _sincronizar_marcas(self, con, tipo: str, filtros: list[str]) -> list[dict]:
        dados = self._get(f"{API_BASE}/{tipo}/marcas")
        if not dados:
            raise CommandError("Não foi possível listar as marcas na API FIPE.")

        if filtros:
            alvos = {f.strip().casefold() for f in filtros if f.strip()}
            dados = [
                m
                for m in dados
                if str(m["codigo"]).casefold() in alvos or m["nome"].casefold() in alvos
            ]
            if not dados:
                raise CommandError(f"Marca(s) não encontrada(s): {', '.join(filtros)}")

        con.executemany(
            "INSERT INTO marcas (codigo, nome) VALUES (?, ?) "
            "ON CONFLICT(codigo) DO UPDATE SET nome = excluded.nome",
            [(int(m["codigo"]), m["nome"]) for m in dados],
        )
        con.commit()

        codigos = [int(m["codigo"]) for m in dados]
        placeholders = ",".join("?" * len(codigos))
        rows = con.execute(
            f"SELECT id, codigo, nome FROM marcas WHERE codigo IN ({placeholders}) ORDER BY nome",
            codigos,
        ).fetchall()
        return [dict(r) for r in rows]

    def _sincronizar_modelos(self, con, tipo: str, marca: dict) -> list[dict]:
        url = f"{API_BASE}/{tipo}/marcas/{marca['codigo']}/modelos"
        dados = self._get(url)
        time.sleep(self.pausa)
        if not dados:
            return []

        modelos = dados.get("modelos") if isinstance(dados, dict) else dados
        if not modelos:
            return []

        con.executemany(
            "INSERT INTO modelos (codigo, marca_id, nome) VALUES (?, ?, ?) "
            "ON CONFLICT(codigo, marca_id) DO UPDATE SET nome = excluded.nome",
            [(int(m["codigo"]), marca["id"], m["nome"]) for m in modelos],
        )
        con.commit()

        rows = con.execute(
            "SELECT id, codigo, nome FROM modelos WHERE marca_id = ?",
            (marca["id"],),
        ).fetchall()
        return [dict(r) for r in rows]

    def _modelos_pendentes(self, con, modelos: list[dict], *, forcar: bool) -> list[dict]:
        if forcar or not modelos:
            return modelos
        com_anos = {
            r[0]
            for r in con.execute(
                "SELECT DISTINCT modelo_id FROM anos WHERE modelo_id IN "
                f"({','.join('?' * len(modelos))})",
                [m["id"] for m in modelos],
            )
        }
        return [m for m in modelos if m["id"] not in com_anos]

    def _sincronizar_anos(
        self, con, tipo: str, marca: dict, modelos: list[dict], paralelo: int
    ) -> int:
        def buscar(modelo: dict):
            url = f"{API_BASE}/{tipo}/marcas/{marca['codigo']}/modelos/{modelo['codigo']}/anos"
            dados = self._get(url)
            time.sleep(self.pausa)
            return modelo, dados or []

        inseridos = 0
        with ThreadPoolExecutor(max_workers=paralelo) as pool:
            for modelo, anos in pool.map(buscar, modelos):
                if not anos:
                    continue
                cur = con.executemany(
                    "INSERT OR IGNORE INTO anos (codigo, descricao, modelo_id) VALUES (?, ?, ?)",
                    [(str(a["codigo"]), a["nome"], modelo["id"]) for a in anos],
                )
                inseridos += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        con.commit()
        self.stdout.write(f"    modelos pendentes: {len(modelos)} · anos gravados: {inseridos}")
        return inseridos

    def _resumo(self, con) -> None:
        for tabela in ("marcas", "modelos", "anos"):
            total = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            self.stdout.write(f"  {tabela}: {total}")
        sem_anos = con.execute(
            "SELECT COUNT(*) FROM modelos WHERE id NOT IN (SELECT DISTINCT modelo_id FROM anos)"
        ).fetchone()[0]
        if sem_anos:
            self.stdout.write(
                self.style.WARNING(f"  modelos sem anos: {sem_anos} (rode o comando de novo)")
            )

    def _compactar(self, con, destino: Path) -> None:
        """Sai do WAL e compacta: o arquivo é aberto com mode=ro&immutable=1 em produção."""
        modo = con.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        con.execute("VACUUM")
        con.commit()
        tamanho = destino.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"  journal_mode={modo} · {tamanho:.0f} KB"))
