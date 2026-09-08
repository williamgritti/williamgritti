"""Command line interface for fiscalkit.

Examples::

    fiscalkit chave 43240311222333000181550010000001231000000018
    fiscalkit cnpj 11.222.333/0001-81
    fiscalkit cpf 111.444.777-35
    fiscalkit nfe nota.xml
    fiscalkit cfop 6102

Add ``--json`` to any command for machine-readable output, which is what makes
this usable from a shell pipeline or a CI check.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .exceptions import FiscalKitError
from .mcp.server import (
    analisar_nfe,
    classificar_cfop,
    decodificar_chave,
    validar_cnpj,
    validar_cpf,
)

__all__ = ["main"]


def _emit(payload: dict[str, Any], as_json: bool, lines: list[str]) -> int:
    """Print either the JSON payload or the human-readable *lines*.

    Returns the process exit code: 0 when the payload reports success.
    """
    ok = bool(payload.get("valido", payload.get("ok", True)))
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in lines:
            print(line)
        if not ok:
            print(f"  motivo: {payload.get('detalhe') or payload.get('motivo')}", file=sys.stderr)
    return 0 if ok else 1


def _cmd_chave(args: argparse.Namespace) -> int:
    payload = decodificar_chave(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["chave invalida"])
    lines = [
        f"chave      {payload['chave_formatada']}",
        f"uf         {payload['uf_sigla']} ({payload['uf_nome']})",
        f"emissao    {payload['emissao_ano_mes']}  ({payload['emissao_data']})",
        f"cnpj       {payload['cnpj_emitente']}",
        f"modelo     {payload['modelo']} - {payload['modelo_nome']}",
        f"serie      {payload['serie']}",
        f"numero     {payload['numero']}",
        f"emissao    {payload['tipo_emissao_nome']}",
    ]
    return _emit(payload, args.json, lines)


def _cmd_cnpj(args: argparse.Namespace) -> int:
    payload = validar_cnpj(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CNPJ invalido"])
    kind = "alfanumerico" if payload["alfanumerico"] else "numerico"
    place = "matriz" if payload["matriz"] else f"filial {payload['ordem']}"
    return _emit(payload, args.json, [f"{payload['formatado']}  valido  ({kind}, {place})"])


def _cmd_cpf(args: argparse.Namespace) -> int:
    payload = validar_cpf(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CPF invalido"])
    return _emit(payload, args.json, [f"{payload['formatado']}  valido"])


def _cmd_cfop(args: argparse.Namespace) -> int:
    payload = classificar_cfop(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CFOP invalido"])
    lines = [
        f"{payload['cfop']}  {payload['sentido']} / {payload['abrangencia']}",
        f"  {payload['descricao']}",
    ]
    return _emit(payload, args.json, lines)


def _cmd_nfe(args: argparse.Namespace) -> int:
    path = Path(args.arquivo)
    if not path.is_file():
        print(f"arquivo nao encontrado: {path}", file=sys.stderr)
        return 2
    payload = analisar_nfe(path.read_bytes().decode("utf-8", errors="replace"))
    if not payload.get("ok"):
        return _emit(payload, args.json, ["nao foi possivel ler a NF-e"])
    emit = payload["emitente"] or {}
    dest = payload["destinatario"] or {}
    lines = [
        f"nota       {payload['numero']}/{payload['serie']}  modelo {payload['modelo']}",
        f"chave      {payload['chave']}",
        f"emitente   {emit.get('nome', '')} ({emit.get('documento', '')})",
        f"destino    {dest.get('nome', '')} ({dest.get('documento', '')})",
        f"itens      {payload['quantidade_itens']}",
        f"total      R$ {payload['totais']['total_nota']}",
        f"autorizada {'sim' if payload['autorizada'] else 'nao'}  {payload['status_motivo']}",
        f"confere    {'sim' if payload['totais_conferem'] else 'NAO - soma dos itens diverge'}",
    ]
    return _emit(payload, args.json, lines)


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``fiscalkit`` command."""
    parser = argparse.ArgumentParser(
        prog="fiscalkit",
        description="Documentos fiscais brasileiros na linha de comando.",
    )
    parser.add_argument("--version", action="version", version=f"fiscalkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(
        name: str,
        help_text: str,
        arg: str,
        arg_help: str,
        handler: Callable[[argparse.Namespace], int],
    ) -> None:
        p = sub.add_parser(name, help=help_text)
        p.add_argument(arg, help=arg_help)
        p.add_argument("--json", action="store_true", help="saida em JSON")
        p.set_defaults(func=handler)

    add("chave", "decodifica uma chave de acesso de 44 digitos", "valor", "a chave", _cmd_chave)
    add("cnpj", "valida um CNPJ (numerico ou alfanumerico)", "valor", "o CNPJ", _cmd_cnpj)
    add("cpf", "valida um CPF", "valor", "o CPF", _cmd_cpf)
    add("cfop", "classifica um CFOP", "valor", "o CFOP", _cmd_cfop)
    add("nfe", "analisa um XML de NF-e", "arquivo", "caminho do XML", _cmd_nfe)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except FiscalKitError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
