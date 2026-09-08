"""Command line interface for fiscalkit.

Examples::

    fiscalkit chave 43240311222333000181550010000001231000000010
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
import textwrap
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
from .scan.fixer import apply_patches, build_patches, unified_diff
from .scan.sarif import to_sarif
from .scan.scanner import scan_path

__all__ = ["main"]


#: ``ValidationError.reason`` is documented as a machine-readable code intended
#: for i18n on the caller's side. This CLI is that caller: it addresses Brazilian
#: users, so it renders the code in Portuguese rather than printing the library's
#: English exception message. ``test_every_reason_code_has_a_translation`` fails
#: if a new code is ever raised without an entry here.
_REASON_PT = {
    "length": "tamanho inválido",
    "repeated_digits": "todos os dígitos são iguais",
    "non_numeric_check_digits": "os dois dígitos verificadores precisam ser numéricos",
    "check_digit": "dígitos verificadores não conferem",
    "year_month": "mês de emissão fora do intervalo 01-12",
}


def _reason_text(payload: dict[str, Any]) -> str:
    """Render the failure reason in Portuguese, falling back to the raw detail."""
    code = payload.get("motivo")
    if isinstance(code, str) and code in _REASON_PT:
        return _REASON_PT[code]
    detail = payload.get("detalhe") or payload.get("motivo")
    return str(detail)


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
            print(f"  motivo: {_reason_text(payload)}", file=sys.stderr)
    return 0 if ok else 1


def _cmd_chave(args: argparse.Namespace) -> int:
    payload = decodificar_chave(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["chave inválida"])
    lines = [
        f"chave      {payload['chave_formatada']}",
        f"uf         {payload['uf_sigla']} ({payload['uf_nome']})",
        f"emissão    {payload['emissao_ano_mes']}  ({payload['emissao_data']})",
        f"cnpj       {payload['cnpj_emitente']}",
        f"modelo     {payload['modelo']} - {payload['modelo_nome']}",
        f"série      {payload['serie']}",
        f"número     {payload['numero']}",
        f"emissão    {payload['tipo_emissao_nome']}",
    ]
    return _emit(payload, args.json, lines)


def _cmd_cnpj(args: argparse.Namespace) -> int:
    payload = validar_cnpj(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CNPJ inválido"])
    kind = "alfanumérico" if payload["alfanumerico"] else "numérico"
    place = "matriz" if payload["matriz"] else f"filial {payload['ordem']}"
    return _emit(payload, args.json, [f"{payload['formatado']}  válido  ({kind}, {place})"])


def _cmd_cpf(args: argparse.Namespace) -> int:
    payload = validar_cpf(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CPF inválido"])
    return _emit(payload, args.json, [f"{payload['formatado']}  válido"])


def _cmd_cfop(args: argparse.Namespace) -> int:
    payload = classificar_cfop(args.valor)
    if not payload.get("valido"):
        return _emit(payload, args.json, ["CFOP inválido"])
    lines = [
        f"{payload['cfop']}  {payload['sentido']} / {payload['abrangencia']}",
        f"  {payload['descricao']}",
    ]
    return _emit(payload, args.json, lines)


def _cmd_nfe(args: argparse.Namespace) -> int:
    path = Path(args.arquivo)
    if not path.is_file():
        print(f"arquivo não encontrado: {path}", file=sys.stderr)
        return 2
    # Hand over raw bytes: decoding as UTF-8 here would mangle the ISO-8859-1
    # files the parser itself reads correctly from the XML declaration.
    payload = analisar_nfe(path.read_bytes())
    if not payload.get("ok"):
        return _emit(payload, args.json, ["não foi possível ler a NF-e"])
    emit = payload["emitente"] or {}
    dest = payload["destinatario"] or {}
    lines = [
        f"nota       {payload['numero']}/{payload['serie']}  modelo {payload['modelo']}",
        f"chave      {payload['chave']}",
        f"emitente   {emit.get('nome', '')} ({emit.get('documento', '')})",
        f"destino    {dest.get('nome', '')} ({dest.get('documento', '')})",
        f"itens      {payload['quantidade_itens']}",
        f"total      R$ {payload['totais']['total_nota']}",
        f"autorizada {'sim' if payload['autorizada'] else 'não'}  {payload['status_motivo']}",
        f"confere    {'sim' if payload['totais_conferem'] else 'NÃO - soma dos itens diverge'}",
    ]
    return _emit(payload, args.json, lines)


_SEVERITY_LABEL = {"breaks": "QUEBRA", "risky": "RISCO ", "review": "REVER "}

#: Width the wrapped remediation text is fitted to. Narrow enough to survive a
#: split terminal, wide enough not to fragment a sentence into scraps.
_FIX_WIDTH = 92
_FIX_LABEL = "       correção: "


def _wrap_fix(fix: str) -> str:
    """Render a rule's fix as a hanging-indented block under its label."""
    return textwrap.fill(
        fix,
        width=_FIX_WIDTH,
        initial_indent=_FIX_LABEL,
        subsequent_indent=" " * len(_FIX_LABEL),
    )


def _cmd_scan(args: argparse.Namespace) -> int:
    """Scan a path for code that will not survive the alphanumeric CNPJ."""
    target = Path(args.caminho)
    if not target.exists():
        print(f"caminho nao encontrado: {target}", file=sys.stderr)
        return 2
    result = scan_path(target, prune=not args.incluir_tudo)
    fmt = getattr(args, "format", "text")

    if args.diff or args.fix:
        root = target if target.is_dir() else target.parent
        patches = build_patches(result.findings, root)
        if not patches:
            print("nenhuma correção automática disponível para os achados", file=sys.stderr)
            return 1 if result.breaks else 0
        if args.diff:
            print(unified_diff(patches, root), end="")
            # A diff is a report, not a change; keep the gate semantics.
            return 1 if result.breaks else 0
        changed = apply_patches(patches)
        for path in changed:
            print(f"corrigido {path}")
        remaining = scan_path(target, prune=not args.incluir_tudo)
        print(
            f"{len(changed)} arquivo(s) alterado(s); "
            f"{len(remaining.findings)} ocorrência(s) restante(s) para revisão humana"
        )
        return 1 if remaining.breaks else 0

    if fmt == "sarif":
        # SARIF is consumed by GitHub code scanning, which needs the upload to
        # succeed even when the scan found problems, so this always exits 0.
        print(json.dumps(to_sarif(result), ensure_ascii=False, indent=2))
        return 0
    if args.json or fmt == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 1 if result.breaks else 0

    for finding in result.sorted_findings():
        label = _SEVERITY_LABEL.get(finding.severity, finding.severity)
        print(f"{label} {finding.path}:{finding.line}  [{finding.rule_id}] {finding.title}")
        print(f"       {finding.excerpt}")
        print(_wrap_fix(finding.fix))
        print()

    counts = result.counts()
    print(
        f"{result.files_scanned} arquivo(s) analisado(s), "
        f"{len(result.findings)} ocorrência(s): "
        f"{counts.get('breaks', 0)} quebra, {counts.get('risky', 0)} risco, "
        f"{counts.get('review', 0)} rever"
    )
    if result.files_minified:
        print(
            f"aviso: {result.files_minified} arquivo(s) minificado(s)/empacotado(s) "
            f"ignorado(s) -- corrija no código-fonte, não no bundle.",
            file=sys.stderr,
        )
    if result.files_pruned:
        which = ", ".join(f"{name} ({n})" for name, n in sorted(result.pruned.items()))
        print(
            f"aviso: {result.files_pruned} arquivo(s) ignorado(s) em diretórios "
            f"podados: {which}. use --incluir-tudo para analisá-los.",
            file=sys.stderr,
        )
    if result.scanned_nothing:
        print(
            "nenhum arquivo analisado -- verifique o caminho ou a extensão dos arquivos",
            file=sys.stderr,
        )
    elif result.is_clean:
        print("nenhum padrão incompatível com o CNPJ alfanumérico encontrado")
    # Non-zero only for certain breakage, so this can gate a build without
    # failing it on advisory findings. An empty scan is also non-zero: silence
    # from a tool that looked at nothing must not read as a pass.
    if result.scanned_nothing:
        return 2
    return 1 if result.breaks else 0


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
        p.add_argument("--json", action="store_true", help="saída em JSON")
        p.set_defaults(func=handler)

    add("chave", "decodifica uma chave de acesso de 44 dígitos", "valor", "a chave", _cmd_chave)
    add("cnpj", "valida um CNPJ (numerico ou alfanumerico)", "valor", "o CNPJ", _cmd_cnpj)
    add("cpf", "valida um CPF", "valor", "o CPF", _cmd_cpf)
    add("cfop", "classifica um CFOP", "valor", "o CFOP", _cmd_cfop)
    add("nfe", "analisa um XML de NF-e", "arquivo", "caminho do XML", _cmd_nfe)
    add(
        "scan",
        "procura código que quebra com o CNPJ alfanumérico de 2026",
        "caminho",
        "arquivo ou diretório",
        _cmd_scan,
    )
    # Only `scan` produces SARIF, so the flag lives on that subparser alone.
    scan_parser = sub.choices["scan"]
    scan_parser.add_argument(
        "--diff",
        action="store_true",
        help="mostra o patch sugerido em vez de aplicar (formato de git apply)",
    )
    scan_parser.add_argument(
        "--fix",
        action="store_true",
        help="aplica as correções mecânicas; o resto fica para revisão humana",
    )
    scan_parser.add_argument(
        "--incluir-tudo",
        action="store_true",
        help="analisa também dist/, build/, vendor/ e afins (útil para pacotes publicados)",
    )
    scan_parser.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="formato de saída (sarif alimenta o GitHub code scanning)",
    )
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
