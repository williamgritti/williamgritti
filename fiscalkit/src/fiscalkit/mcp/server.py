"""An MCP server exposing fiscalkit to AI agents.

Run it over stdio::

    fiscalkit-mcp

Or register it with a client such as Claude Desktop or Claude Code::

    {
      "mcpServers": {
        "fiscalkit": {"command": "fiscalkit-mcp"}
      }
    }

Every tool returns plain JSON-friendly data and reports failure as a payload with
``"valido": false`` and a reason, rather than raising. An agent that gets a
structured "no" can explain the problem to the user; an agent that gets an
exception usually just retries.
"""

from __future__ import annotations

from typing import Any

from ..codes.cfop import classify_cfop
from ..codes.uf import UFS, by_acronym, by_code
from ..documents.cnpj import CNPJ, check_digits_for, strip_cnpj
from ..documents.cpf import CPF
from ..exceptions import FiscalKitError, ValidationError
from ..nfe.chave import AccessKey
from ..nfe.models import Party
from ..nfe.parser import parse_nfe

__all__ = ["TOOL_FUNCTIONS", "build_server", "main"]


# ---------------------------------------------------------------------------
# Tool implementations, kept free of any MCP types so they stay unit-testable
# ---------------------------------------------------------------------------


def validar_cpf(cpf: str) -> dict[str, Any]:
    """Validate a CPF and return its canonical formatting."""
    try:
        parsed = CPF.parse(cpf)
    except ValidationError as exc:
        return {"valido": False, "motivo": exc.reason, "detalhe": str(exc)}
    return {"valido": True, "cpf": parsed.digits, "formatado": parsed.formatted}


def validar_cnpj(cnpj: str) -> dict[str, Any]:
    """Validate a CNPJ, numeric or alphanumeric, and describe its structure."""
    try:
        parsed = CNPJ.parse(cnpj)
    except ValidationError as exc:
        return {"valido": False, "motivo": exc.reason, "detalhe": str(exc)}
    return {
        "valido": True,
        "cnpj": parsed.value,
        "formatado": parsed.formatted,
        "alfanumerico": parsed.is_alphanumeric,
        "raiz": parsed.raiz,
        "ordem": parsed.ordem,
        "matriz": parsed.is_matriz,
    }


def calcular_dv_cnpj(base: str) -> dict[str, Any]:
    """Compute the two check digits for a 12-character CNPJ base."""
    try:
        digits = check_digits_for(base)
    except ValidationError as exc:
        return {"ok": False, "motivo": exc.reason, "detalhe": str(exc)}
    # strip_cnpj, not str.isalnum(): isalnum() is True for non-ASCII letters such
    # as "Ç", which would be carried into a value that is not a CNPJ at all.
    completo = strip_cnpj(base) + digits
    return {"ok": True, "digitos_verificadores": digits, "cnpj_completo": completo}


def decodificar_chave(chave: str) -> dict[str, Any]:
    """Decode a 44-digit access key into every field it packs.

    This answers who issued a document, when, in which state, and under which
    model and series, with no network call to SEFAZ.
    """
    try:
        return {"valido": True, **AccessKey.parse(chave).to_dict()}
    except ValidationError as exc:
        return {"valido": False, "motivo": exc.reason, "detalhe": str(exc)}


def analisar_nfe(xml: str | bytes) -> dict[str, Any]:
    """Parse NF-e XML and summarize issuer, recipient, items and totals.

    Accepts bytes so a caller can hand over raw file content and let the XML
    declaration pick the encoding; NF-e files are frequently ISO-8859-1.
    """
    try:
        nfe = parse_nfe(xml)
    except FiscalKitError as exc:
        return {"ok": False, "detalhe": str(exc)}

    def party(p: Party | None) -> dict[str, Any] | None:
        if p is None:
            return None
        return {
            "nome": p.name,
            "documento": p.tax_id,
            "tipo": "PJ" if p.is_company else "PF",
            "ie": p.ie,
            "uf": p.address.uf if p.address else "",
            "municipio": p.address.city if p.address else "",
        }

    return {
        "ok": True,
        "chave": nfe.access_key,
        "numero": nfe.number,
        "serie": nfe.series,
        "modelo": nfe.model,
        "natureza_operacao": nfe.operation_nature,
        "emissao": nfe.issued_at.isoformat() if nfe.issued_at else None,
        "autorizada": nfe.is_authorized,
        "protocolo": nfe.protocol,
        "status": nfe.status_code,
        "status_motivo": nfe.status_reason,
        "emitente": party(nfe.issuer),
        "destinatario": party(nfe.recipient),
        "quantidade_itens": nfe.item_count,
        "itens": [
            {
                "numero": item.number,
                "descricao": item.product.description,
                "ncm": item.product.ncm,
                "cfop": item.product.cfop,
                "quantidade": str(item.product.quantity),
                "valor_unitario": str(item.product.unit_price),
                "valor_total": str(item.product.total),
                "icms": str(item.icms),
                "ipi": str(item.ipi),
                "pis": str(item.pis),
                "cofins": str(item.cofins),
            }
            for item in nfe.items
        ],
        "totais": {
            "produtos": str(nfe.totals.products),
            "icms": str(nfe.totals.icms),
            "ipi": str(nfe.totals.ipi),
            "pis": str(nfe.totals.pis),
            "cofins": str(nfe.totals.cofins),
            "frete": str(nfe.totals.freight),
            "desconto": str(nfe.totals.discount),
            "total_nota": str(nfe.totals.invoice_total),
        },
        "soma_itens": str(nfe.computed_products_total),
        "totais_conferem": nfe.totals_reconcile(),
    }


def classificar_cfop(cfop: str) -> dict[str, Any]:
    """Classify a CFOP into direction (inbound/outbound) and scope."""
    info = classify_cfop(cfop)
    if info is None:
        return {"valido": False, "detalhe": "CFOP deve ter 4 digitos e comecar com 1,2,3,5,6 ou 7"}
    return {
        "valido": True,
        "cfop": info.code,
        "sentido": info.direction,
        "abrangencia": info.scope,
        "descricao": info.description,
        "operacao_exterior": info.crosses_border,
    }


def consultar_uf(consulta: str) -> dict[str, Any]:
    """Look up a federative unit by IBGE code or two-letter acronym."""
    uf = by_code(consulta) or by_acronym(consulta)
    if uf is None:
        return {"encontrado": False, "detalhe": f"UF nao encontrada para '{consulta}'"}
    return {
        "encontrado": True,
        "codigo": uf.code,
        "sigla": uf.acronym,
        "nome": uf.name,
        "regiao": uf.region,
    }


def listar_ufs() -> dict[str, Any]:
    """List all 27 federative units with their IBGE codes."""
    return {
        "total": len(UFS),
        "ufs": [
            {"codigo": uf.code, "sigla": uf.acronym, "nome": uf.name, "regiao": uf.region}
            for uf in UFS
        ],
    }


#: Every tool exposed over MCP, by the name the agent calls.
TOOL_FUNCTIONS = {
    "validar_cpf": validar_cpf,
    "validar_cnpj": validar_cnpj,
    "calcular_dv_cnpj": calcular_dv_cnpj,
    "decodificar_chave": decodificar_chave,
    "analisar_nfe": analisar_nfe,
    "classificar_cfop": classificar_cfop,
    "consultar_uf": consultar_uf,
    "listar_ufs": listar_ufs,
}


# ---------------------------------------------------------------------------
# MCP wiring
# ---------------------------------------------------------------------------


def _server_class() -> type[Any]:
    """Return the server class from whichever generation of the SDK is installed.

    The SDK renamed ``FastMCP`` to ``MCPServer`` in 2.0 and moved it to a new
    module. Both generations expose the same constructor keywords, ``.tool()``
    decorator and ``.run()`` signature that this module relies on, so supporting
    both costs one import fallback and spares every user a pin.

    Raises:
        ImportError: If ``mcp`` is missing, or is installed but exposes neither
            class. The two cases get different messages because they need
            different fixes.
    """
    try:
        import mcp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ImportError(
            "The MCP server needs the 'mcp' package. Install it with:\n"
            "    pip install 'fiscalkit[mcp]'"
        ) from exc

    try:  # mcp >= 2.0
        from mcp.server.mcpserver import MCPServer

        modern: type[Any] = MCPServer
        return modern
    except ImportError:
        pass

    try:  # mcp 1.x
        # Under an installed 2.x SDK this module exists but no longer exports
        # FastMCP, so the attribute is resolved at runtime rather than statically.
        from mcp.server.fastmcp import FastMCP  # type: ignore[attr-defined]

        legacy: type[Any] = FastMCP
        return legacy
    except ImportError as exc:  # pragma: no cover - unreleased SDK layout
        raise ImportError(
            "The installed 'mcp' package exposes neither MCPServer (2.x) nor "
            "FastMCP (1.x). Reinstall a supported version with:\n"
            "    pip install --upgrade 'fiscalkit[mcp]'"
        ) from exc


def build_server() -> Any:
    """Construct the MCP server with every tool registered.

    Works with both ``mcp`` 1.x and 2.x.

    Raises:
        ImportError: If the optional ``mcp`` dependency is unavailable or
            unsupported.
    """
    server_class = _server_class()
    server = server_class(
        "fiscalkit",
        instructions=(
            "Ferramentas para documentos fiscais brasileiros: valida CPF e CNPJ "
            "(inclusive o CNPJ alfanumerico obrigatorio a partir de julho de 2026), "
            "decodifica chaves de acesso de 44 digitos e analisa XML de NF-e. "
            "Tudo roda localmente, sem consultar a SEFAZ."
        ),
    )
    for name, func in TOOL_FUNCTIONS.items():
        server.tool(name=name, description=(func.__doc__ or "").strip())(func)
    return server


def main() -> None:
    """Entry point for the ``fiscalkit-mcp`` console script."""
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
