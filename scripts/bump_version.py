#!/usr/bin/env python3
"""Bump semântico de versão: VERSION + pyproject.toml + CHANGELOG.md.

Uso:
  uv run python scripts/bump_version.py patch --added "corrige X"
  uv run python scripts/bump_version.py minor --added "adiciona Y"
  uv run python scripts/bump_version.py major --changed "quebra API Z"
  uv run python scripts/bump_version.py minor   # só promove Unreleased
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"

SECTION_KEYS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")


def read_version() -> str:
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", raw):
        raise SystemExit(f"VERSION inválida: {raw!r}")
    return raw


def bump(version: str, level: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"Nível inválido: {level}")


def write_version(version: str) -> None:
    VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")


def sync_pyproject(version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    updated, n = re.subn(
        r'(?m)^(version\s*=\s*")([^"]+)(")',
        rf"\g<1>{version}\g<3>",
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit("Não foi possível atualizar version em pyproject.toml")
    PYPROJECT.write_text(updated, encoding="utf-8")


def _ensure_unreleased(changelog: str) -> str:
    if re.search(r"(?m)^## \[Unreleased\]\s*$", changelog):
        return changelog
    # Insere Unreleased após o preâmbulo (antes da primeira seção de versão).
    m = re.search(r"(?m)^## \[", changelog)
    block = "## [Unreleased]\n\n"
    if not m:
        return changelog.rstrip() + "\n\n" + block
    return changelog[: m.start()] + block + changelog[m.start() :]


def _append_note(changelog: str, section: str, note: str) -> str:
    note = note.strip().lstrip("- ").strip()
    if not note:
        return changelog
    changelog = _ensure_unreleased(changelog)
    unreleased = re.search(
        r"(?ms)^(## \[Unreleased\]\s*\n)(.*?)(?=^## \[|\Z)",
        changelog,
    )
    if not unreleased:
        raise SystemExit("Seção [Unreleased] não encontrada no CHANGELOG")

    head, body = unreleased.group(1), unreleased.group(2)
    section_re = re.compile(
        rf"(?ms)^(### {re.escape(section)}\s*\n)(.*?)(?=^### |\Z)",
    )
    sm = section_re.search(body)
    bullet = f"- {note}\n"
    if sm:
        sec_head, sec_body = sm.group(1), sm.group(2)
        sec_body = sec_body.rstrip("\n") + "\n"
        new_sec = sec_head + sec_body + bullet + "\n"
        body = body[: sm.start()] + new_sec + body[sm.end() :]
    else:
        # Insere seção após o cabeçalho Unreleased (antes de outras ### se possível).
        insert = f"### {section}\n\n{bullet}\n"
        body = insert + body.lstrip("\n")
        if not body.endswith("\n"):
            body += "\n"

    return changelog[: unreleased.start()] + head + body + changelog[unreleased.end() :]


def promote_unreleased(changelog: str, new_version: str, today: str) -> str:
    changelog = _ensure_unreleased(changelog)
    m = re.search(
        r"(?ms)^(## \[Unreleased\]\s*\n)(.*?)(?=^## \[|\Z)",
        changelog,
    )
    if not m:
        raise SystemExit("Seção [Unreleased] não encontrada no CHANGELOG")

    body = m.group(2).strip("\n")
    # Se Unreleased está vazio, cria seção mínima.
    if not body.strip():
        body = "### Changed\n\n- Atualização de versão\n"

    released = f"## [{new_version}] — {today}\n\n{body.strip()}\n\n"
    empty = "## [Unreleased]\n\n"
    return changelog[: m.start()] + empty + released + changelog[m.end() :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump de versão do Oficina AI")
    parser.add_argument(
        "level",
        choices=("major", "minor", "patch"),
        help="major (quebra), minor (feat), patch (fix)",
    )
    parser.add_argument("--added", action="append", default=[], help="Nota em Added")
    parser.add_argument("--changed", action="append", default=[], help="Nota em Changed")
    parser.add_argument("--fixed", action="append", default=[], help="Nota em Fixed")
    parser.add_argument("--removed", action="append", default=[], help="Nota em Removed")
    parser.add_argument("--deprecated", action="append", default=[], help="Nota em Deprecated")
    parser.add_argument("--security", action="append", default=[], help="Nota em Security")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra a nova versão sem gravar arquivos",
    )
    args = parser.parse_args(argv)

    current = read_version()
    new = bump(current, args.level)
    today = date.today().isoformat()

    changelog = CHANGELOG.read_text(encoding="utf-8")
    notes = [
        ("Added", args.added),
        ("Changed", args.changed),
        ("Fixed", args.fixed),
        ("Removed", args.removed),
        ("Deprecated", args.deprecated),
        ("Security", args.security),
    ]
    for section, items in notes:
        for item in items:
            changelog = _append_note(changelog, section, item)

    changelog = promote_unreleased(changelog, new, today)

    if args.dry_run:
        print(f"{current} → {new} (dry-run)")
        return 0

    write_version(new)
    sync_pyproject(new)
    CHANGELOG.write_text(changelog, encoding="utf-8")
    print(f"{current} → {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
