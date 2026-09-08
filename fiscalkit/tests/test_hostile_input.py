"""Regression tests for defects found by adversarial audit.

Each test here pins a specific failure that reached a user-facing surface -- the
CLI, the MCP tools, or a star import -- rather than a hypothetical one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import fiscalkit
from fiscalkit import ValidationError, is_valid_access_key, parse_nfe
from fiscalkit.mcp.server import analisar_nfe, calcular_dv_cnpj, decodificar_chave
from fiscalkit.nfe.chave import AccessKey, access_key_check_digit


def _key(uf: str = "43", year_month: str = "2403") -> str:
    body = f"{uf}{year_month}11222333000181550010000001231" + "0" * 8
    assert len(body) == 43
    return body + str(access_key_check_digit(body))


# ---------------------------------------------------------------------------
# Public API integrity
# ---------------------------------------------------------------------------


def test_star_import_works() -> None:
    """__all__ must contain only resolvable names, never section comments."""
    namespace: dict[str, object] = {}
    exec("from fiscalkit import *", namespace)
    assert "AccessKey" in namespace


def test_every_exported_name_resolves() -> None:
    for name in fiscalkit.__all__:
        assert not name.startswith("#"), f"{name!r} is a comment, not an export"
        assert hasattr(fiscalkit, name), f"{name} is exported but missing"


# ---------------------------------------------------------------------------
# Hostile numeric values in third-party XML
# ---------------------------------------------------------------------------

_HOSTILE = ["NaN", "sNaN", "-sNaN", "Infinity", "-Infinity", "1E999999999", "-1E999999999"]


@pytest.mark.parametrize("value", _HOSTILE)
def test_non_finite_amounts_degrade_to_zero(value: str) -> None:
    """Decimal accepts these strings; only later arithmetic explodes.

    They must be refused at parse time so a hostile document cannot raise an
    uncaught decimal error out of the library.
    """
    xml = (
        f'<infNFe Id="NFe1"><total><ICMSTot><vProd>10.00</vProd></ICMSTot></total>'
        f'<det nItem="1"><prod><vProd>{value}</vProd></prod></det></infNFe>'
    )
    nfe = parse_nfe(xml)
    total = nfe.items[0].product.total
    assert total.is_finite()
    assert total == Decimal("0")


@pytest.mark.parametrize("value", _HOSTILE)
def test_totals_reconcile_never_raises_on_hostile_input(value: str) -> None:
    xml = (
        f'<infNFe Id="NFe1"><total><ICMSTot><vProd>{value}</vProd></ICMSTot></total>'
        f'<det nItem="1"><prod><vProd>{value}</vProd></prod></det></infNFe>'
    )
    assert parse_nfe(xml).totals_reconcile() is True


@pytest.mark.parametrize("value", _HOSTILE)
def test_hostile_tax_value_does_not_escape_the_mcp_tool(value: str) -> None:
    """The MCP contract is a structured payload, never a raised exception."""
    xml = (
        f'<infNFe Id="NFe1"><det nItem="1"><prod><vProd>1</vProd></prod>'
        f"<imposto><ICMS><ICMS00><vICMS>{value}</vICMS></ICMS00></ICMS></imposto>"
        f"</det></infNFe>"
    )
    assert analisar_nfe(xml)["ok"] is True


def test_ordinary_amounts_still_parse() -> None:
    """The magnitude guard must not reject real monetary values."""
    xml = (
        '<infNFe Id="NFe1"><total><ICMSTot><vProd>12345678901.23</vProd></ICMSTot></total></infNFe>'
    )
    assert parse_nfe(xml).totals.products == Decimal("12345678901.23")


# ---------------------------------------------------------------------------
# Out-of-range emission month
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("year_month", ["2400", "2413", "2499"])
def test_out_of_range_month_is_rejected(year_month: str) -> None:
    key = _key(year_month=year_month)
    assert not is_valid_access_key(key)
    with pytest.raises(ValidationError) as exc:
        AccessKey.parse(key)
    assert exc.value.reason == "year_month"


@pytest.mark.parametrize("year_month", ["2401", "2412", "0001", "9912"])
def test_valid_months_still_accepted(year_month: str) -> None:
    parsed = AccessKey.parse(_key(year_month=year_month))
    assert parsed.emitted_on.month == int(year_month[2:])


def test_out_of_range_month_never_escapes_as_valueerror() -> None:
    """A key built bypassing parse() must still fail inside FiscalKitError."""
    bad = AccessKey(_key(year_month="2400"))
    with pytest.raises(ValidationError):
        _ = bad.emitted_on


def test_decodificar_chave_returns_payload_for_bad_month() -> None:
    result = decodificar_chave(_key(year_month="2400"))
    assert result["valido"] is False
    assert result["motivo"] == "year_month"


# ---------------------------------------------------------------------------
# Encoding and normalization
# ---------------------------------------------------------------------------


def test_cli_reads_latin1_without_mangling(tmp_path, capsys) -> None:
    """The CLI must not lossily decode files the parser reads correctly."""
    from fiscalkit.cli import main

    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<infNFe Id="NFe1"><emit><xNome>Comércio Ação Ltda</xNome></emit>'
        "<total><ICMSTot><vNF>1.00</vNF></ICMSTot></total></infNFe>"
    )
    path = tmp_path / "latin.xml"
    path.write_bytes(xml.encode("iso-8859-1"))
    assert main(["nfe", str(path)]) == 0
    assert "Comércio Ação Ltda" in capsys.readouterr().out


def test_calcular_dv_cnpj_normalizes_non_ascii() -> None:
    """str.isalnum() is True for 'Ç'; the result must still be a real CNPJ."""
    result = calcular_dv_cnpj("11222333000ç1")
    assert result["ok"] is True
    assert result["cnpj_completo"] == "11222333000181"
    assert len(result["cnpj_completo"]) == 14
