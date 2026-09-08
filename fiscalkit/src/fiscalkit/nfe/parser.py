"""Parse NF-e XML (layout 4.00) into the typed models in :mod:`fiscalkit.nfe.models`.

The parser accepts the three shapes that arrive in practice:

* ``nfeProc``  -- the authorized document bundled with its SEFAZ protocol
* ``NFe``      -- the signed document on its own
* ``infNFe``   -- a bare payload, which some ERPs emit

Namespaces are matched by local name. Real-world files disagree about prefixes and
some tools strip the namespace entirely, so binding to a fixed URI rejects
documents that are otherwise perfectly readable.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET

from ..exceptions import ParseError, UnsupportedDocumentError
from .models import ZERO, Address, Item, NFe, Party, Product, Totals

__all__ = ["parse_nfe", "parse_nfe_file"]


def _local(tag: str) -> str:
    """Strip any ``{namespace}`` prefix from *tag*."""
    return tag.rsplit("}", 1)[-1]


def _find(node: ET.Element | None, *path: str) -> ET.Element | None:
    """Walk *path* by local element name, returning ``None`` if any step is absent."""
    current = node
    for name in path:
        if current is None:
            return None
        current = next((c for c in current if _local(c.tag) == name), None)
    return current


def _find_all(node: ET.Element | None, name: str) -> list[ET.Element]:
    """Return every direct child of *node* whose local name is *name*."""
    if node is None:
        return []
    return [c for c in node if _local(c.tag) == name]


def _text(node: ET.Element | None, *path: str) -> str:
    """Return the stripped text at *path*, or an empty string when absent."""
    found = _find(node, *path) if path else node
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _decimal(node: ET.Element | None, *path: str) -> Decimal:
    """Return the value at *path* as a :class:`Decimal`, or zero when absent.

    Malformed numbers degrade to zero rather than raising: a single unreadable tax
    field should not make an otherwise valid document unparseable.
    """
    raw = _text(node, *path)
    if not raw:
        return ZERO
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return ZERO


def _sum_tax(imposto: ET.Element | None, group: str, tag: str) -> Decimal:
    """Sum *tag* across every variant inside the *group* tax block.

    Each tax group wraps a variant element whose name encodes the tax situation --
    ``ICMS00``, ``ICMS20``, ``PISAliq``, ``PISNT`` and so on. Summing across the
    variants avoids enumerating every CST in the layout.
    """
    block = _find(imposto, group)
    if block is None:
        return ZERO
    return sum((_decimal(variant, tag) for variant in block), ZERO)


def _first_tax_field(imposto: ET.Element | None, group: str, tag: str) -> str:
    """Return *tag* from the first variant inside *group*, or an empty string."""
    block = _find(imposto, group)
    if block is None:
        return ""
    for variant in block:
        value = _text(variant, tag)
        if value:
            return value
    return ""


def _parse_datetime(raw: str) -> datetime | None:
    """Parse an NF-e timestamp, tolerating both offset-aware and naive forms."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        # Layout 3.10 used separate dEmi/hEmi fields; a bare date still parses.
        try:
            return datetime.fromisoformat(raw[:10])
        except ValueError:
            return None


def _parse_address(node: ET.Element | None) -> Address | None:
    if node is None:
        return None
    return Address(
        street=_text(node, "xLgr"),
        number=_text(node, "nro"),
        complement=_text(node, "xCpl"),
        district=_text(node, "xBairro"),
        city_code=_text(node, "cMun"),
        city=_text(node, "xMun"),
        uf=_text(node, "UF"),
        zip_code=_text(node, "CEP"),
        country=_text(node, "xPais") or "Brasil",
    )


def _parse_party(node: ET.Element | None, address_tag: str) -> Party | None:
    if node is None:
        return None
    return Party(
        name=_text(node, "xNome"),
        trade_name=_text(node, "xFant"),
        cnpj=_text(node, "CNPJ"),
        cpf=_text(node, "CPF"),
        ie=_text(node, "IE"),
        email=_text(node, "email"),
        address=_parse_address(_find(node, address_tag)),
    )


def _parse_item(node: ET.Element) -> Item:
    prod = _find(node, "prod")
    imposto = _find(node, "imposto")
    try:
        number = int(node.get("nItem") or 0)
    except ValueError:
        number = 0
    product = Product(
        code=_text(prod, "cProd"),
        ean=_text(prod, "cEAN"),
        description=_text(prod, "xProd"),
        ncm=_text(prod, "NCM"),
        cfop=_text(prod, "CFOP"),
        unit=_text(prod, "uCom"),
        quantity=_decimal(prod, "qCom"),
        unit_price=_decimal(prod, "vUnCom"),
        total=_decimal(prod, "vProd"),
    )
    return Item(
        number=number,
        product=product,
        icms=_sum_tax(imposto, "ICMS", "vICMS"),
        ipi=_sum_tax(imposto, "IPI", "vIPI"),
        pis=_sum_tax(imposto, "PIS", "vPIS"),
        cofins=_sum_tax(imposto, "COFINS", "vCOFINS"),
        icms_cst=(
            _first_tax_field(imposto, "ICMS", "CST") or _first_tax_field(imposto, "ICMS", "CSOSN")
        ),
        icms_origin=_first_tax_field(imposto, "ICMS", "orig"),
    )


def _parse_totals(node: ET.Element | None) -> Totals:
    icms_tot = _find(node, "ICMSTot")
    if icms_tot is None:
        return Totals()
    return Totals(
        products=_decimal(icms_tot, "vProd"),
        icms_base=_decimal(icms_tot, "vBC"),
        icms=_decimal(icms_tot, "vICMS"),
        ipi=_decimal(icms_tot, "vIPI"),
        pis=_decimal(icms_tot, "vPIS"),
        cofins=_decimal(icms_tot, "vCOFINS"),
        freight=_decimal(icms_tot, "vFrete"),
        insurance=_decimal(icms_tot, "vSeg"),
        discount=_decimal(icms_tot, "vDesc"),
        other=_decimal(icms_tot, "vOutro"),
        invoice_total=_decimal(icms_tot, "vNF"),
    )


def _locate_inf_nfe(root: ET.Element) -> tuple[ET.Element, ET.Element | None]:
    """Return the ``infNFe`` element and the ``infProt`` element when present.

    Raises:
        UnsupportedDocumentError: If the root is not a recognized NF-e shape.
    """
    name = _local(root.tag)
    if name == "infNFe":
        return root, None
    if name == "NFe":
        inf = _find(root, "infNFe")
        if inf is None:
            raise UnsupportedDocumentError("<NFe> element has no <infNFe> child")
        return inf, None
    if name == "nfeProc":
        inf = _find(root, "NFe", "infNFe")
        if inf is None:
            raise UnsupportedDocumentError("<nfeProc> element has no <NFe><infNFe>")
        return inf, _find(root, "protNFe", "infProt")
    raise UnsupportedDocumentError(
        f"Expected <nfeProc>, <NFe> or <infNFe> as the root element, got <{name}>"
    )


def parse_nfe(source: str | bytes) -> NFe:
    """Parse NF-e XML from a string or bytes into an :class:`~fiscalkit.nfe.models.NFe`.

    Args:
        source: The XML document. Bytes are decoded using the document's own
            declared encoding, which matters because NF-e files are frequently
            ISO-8859-1 rather than UTF-8.

    Returns:
        The parsed document.

    Raises:
        ParseError: If the XML is not well-formed.
        UnsupportedDocumentError: If the root element is not an NF-e shape.
    """
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ParseError(f"Malformed XML: {exc}") from exc

    inf_nfe, inf_prot = _locate_inf_nfe(root)
    ide = _find(inf_nfe, "ide")

    # The Id attribute is prefixed with "NFe" by the layout; the key is the rest.
    raw_id = inf_nfe.get("Id") or ""
    access_key = raw_id[3:] if raw_id.upper().startswith("NFE") else raw_id

    return NFe(
        access_key=access_key,
        number=_text(ide, "nNF"),
        series=_text(ide, "serie"),
        model=_text(ide, "mod"),
        issued_at=_parse_datetime(_text(ide, "dhEmi") or _text(ide, "dEmi")),
        operation_nature=_text(ide, "natOp"),
        issuer=_parse_party(_find(inf_nfe, "emit"), "enderEmit"),
        recipient=_parse_party(_find(inf_nfe, "dest"), "enderDest"),
        items=[_parse_item(det) for det in _find_all(inf_nfe, "det")],
        totals=_parse_totals(_find(inf_nfe, "total")),
        protocol=_text(inf_prot, "nProt"),
        status_code=_text(inf_prot, "cStat"),
        status_reason=_text(inf_prot, "xMotivo"),
    )


def parse_nfe_file(path: str | Path) -> NFe:
    """Read the file at *path* and parse it with :func:`parse_nfe`.

    The file is read as bytes so that its declared XML encoding is honored.
    """
    return parse_nfe(Path(path).read_bytes())
