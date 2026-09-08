"""Tests for the NF-e XML parser."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fiscalkit import ParseError, UnsupportedDocumentError, parse_nfe, parse_nfe_file
from fiscalkit.nfe.parser import _local

NS = "http://www.portalfiscal.inf.br/nfe"

# A two-item authorized NF-e. Amounts are internally consistent so that the
# reconciliation check has something real to verify: 3 x 25.50 + 1 x 149.90.
SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="{NS}" versao="4.00">
  <NFe>
    <infNFe Id="NFe43240311222333000181550010000001231000000018" versao="4.00">
      <ide>
        <cUF>43</cUF>
        <cNF>00000001</cNF>
        <natOp>Venda de mercadoria</natOp>
        <mod>55</mod>
        <serie>1</serie>
        <nNF>123</nNF>
        <dhEmi>2024-03-15T10:30:00-03:00</dhEmi>
        <tpNF>1</tpNF>
        <cMunFG>4314902</cMunFG>
        <tpEmis>1</tpEmis>
        <cDV>8</cDV>
      </ide>
      <emit>
        <CNPJ>11222333000181</CNPJ>
        <xNome>Comercio Exemplo Ltda</xNome>
        <xFant>Exemplo</xFant>
        <enderEmit>
          <xLgr>Rua das Flores</xLgr>
          <nro>100</nro>
          <xBairro>Centro</xBairro>
          <cMun>4314902</cMun>
          <xMun>Porto Alegre</xMun>
          <UF>RS</UF>
          <CEP>90010000</CEP>
        </enderEmit>
        <IE>1234567890</IE>
        <CRT>3</CRT>
      </emit>
      <dest>
        <CPF>11144477735</CPF>
        <xNome>Cliente Exemplo</xNome>
        <enderDest>
          <xLgr>Av Brasil</xLgr>
          <nro>2000</nro>
          <xBairro>Jardim</xBairro>
          <cMun>3550308</cMun>
          <xMun>Sao Paulo</xMun>
          <UF>SP</UF>
          <CEP>01000000</CEP>
        </enderDest>
        <indIEDest>9</indIEDest>
        <email>cliente@example.com</email>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>SKU-001</cProd>
          <cEAN>7891234567890</cEAN>
          <xProd>Caneta esferografica azul</xProd>
          <NCM>96081000</NCM>
          <CFOP>5102</CFOP>
          <uCom>UN</uCom>
          <qCom>3.0000</qCom>
          <vUnCom>25.5000000000</vUnCom>
          <vProd>76.50</vProd>
        </prod>
        <imposto>
          <ICMS>
            <ICMS00>
              <orig>0</orig>
              <CST>00</CST>
              <vBC>76.50</vBC>
              <pICMS>18.00</pICMS>
              <vICMS>13.77</vICMS>
            </ICMS00>
          </ICMS>
          <PIS><PISAliq><CST>01</CST><vBC>76.50</vBC><pPIS>1.65</pPIS><vPIS>1.26</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><vBC>76.50</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>5.81</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <det nItem="2">
        <prod>
          <cProd>SKU-002</cProd>
          <cEAN>SEM GTIN</cEAN>
          <xProd>Mochila executiva</xProd>
          <NCM>42021210</NCM>
          <CFOP>6102</CFOP>
          <uCom>UN</uCom>
          <qCom>1.0000</qCom>
          <vUnCom>149.9000000000</vUnCom>
          <vProd>149.90</vProd>
        </prod>
        <imposto>
          <ICMS>
            <ICMS20>
              <orig>1</orig>
              <CST>20</CST>
              <vBC>119.92</vBC>
              <pICMS>12.00</pICMS>
              <vICMS>14.39</vICMS>
            </ICMS20>
          </ICMS>
          <IPI><IPITrib><CST>50</CST><vBC>149.90</vBC><pIPI>5.00</pIPI><vIPI>7.50</vIPI></IPITrib></IPI>
          <PIS><PISAliq><CST>01</CST><vBC>149.90</vBC><pPIS>1.65</pPIS><vPIS>2.47</vPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><vBC>149.90</vBC><pCOFINS>7.60</pCOFINS><vCOFINS>11.39</vCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <total>
        <ICMSTot>
          <vBC>196.42</vBC>
          <vICMS>28.16</vICMS>
          <vProd>226.40</vProd>
          <vFrete>0.00</vFrete>
          <vSeg>0.00</vSeg>
          <vDesc>0.00</vDesc>
          <vIPI>7.50</vIPI>
          <vPIS>3.73</vPIS>
          <vCOFINS>17.20</vCOFINS>
          <vOutro>0.00</vOutro>
          <vNF>233.90</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00">
    <infProt>
      <chNFe>43240311222333000181550010000001231000000018</chNFe>
      <dhRecbto>2024-03-15T10:31:22-03:00</dhRecbto>
      <nProt>143240000123456</nProt>
      <cStat>100</cStat>
      <xMotivo>Autorizado o uso da NF-e</xMotivo>
    </infProt>
  </protNFe>
</nfeProc>
"""


@pytest.fixture(scope="module")
def nfe():
    return parse_nfe(SAMPLE)


def test_local_strips_namespace() -> None:
    assert _local("{http://example.com}tag") == "tag"
    assert _local("tag") == "tag"


def test_header_fields(nfe) -> None:
    assert nfe.access_key == "43240311222333000181550010000001231000000018"
    assert nfe.number == "123"
    assert nfe.series == "1"
    assert nfe.model == "55"
    assert nfe.operation_nature == "Venda de mercadoria"
    assert nfe.issued_at is not None
    assert nfe.issued_at.year == 2024 and nfe.issued_at.month == 3


def test_id_attribute_prefix_is_stripped(nfe) -> None:
    """The layout writes Id="NFe<key>"; the key itself must come back clean."""
    assert not nfe.access_key.upper().startswith("NFE")
    assert len(nfe.access_key) == 44


def test_issuer(nfe) -> None:
    assert nfe.issuer is not None
    assert nfe.issuer.name == "Comercio Exemplo Ltda"
    assert nfe.issuer.cnpj == "11222333000181"
    assert nfe.issuer.is_company
    assert nfe.issuer.tax_id == "11222333000181"
    assert nfe.issuer.address is not None
    assert nfe.issuer.address.uf == "RS"
    assert "Porto Alegre" in nfe.issuer.address.one_line


def test_recipient_is_a_natural_person(nfe) -> None:
    assert nfe.recipient is not None
    assert nfe.recipient.cpf == "11144477735"
    assert not nfe.recipient.is_company
    assert nfe.recipient.tax_id == "11144477735"
    assert nfe.recipient.email == "cliente@example.com"


def test_items_parsed(nfe) -> None:
    assert nfe.item_count == 2
    first, second = nfe.items
    assert first.number == 1
    assert first.product.description == "Caneta esferografica azul"
    assert first.product.ncm == "96081000"
    assert first.product.cfop == "5102"
    assert first.product.quantity == Decimal("3.0000")
    assert first.product.total == Decimal("76.50")
    assert second.number == 2
    assert second.product.cfop == "6102"


def test_money_is_decimal_not_float(nfe) -> None:
    """Binary floats corrupt cent-level reconciliation, so everything is Decimal."""
    assert isinstance(nfe.totals.invoice_total, Decimal)
    assert isinstance(nfe.items[0].product.unit_price, Decimal)
    assert nfe.items[0].product.unit_price == Decimal("25.5000000000")


def test_taxes_extracted_across_cst_variants(nfe) -> None:
    """ICMS00 and ICMS20 are different elements; both must be summed."""
    first, second = nfe.items
    assert first.icms == Decimal("13.77")
    assert first.icms_cst == "00"
    assert first.icms_origin == "0"
    assert first.ipi == Decimal("0")
    assert second.icms == Decimal("14.39")
    assert second.icms_cst == "20"
    assert second.icms_origin == "1"
    assert second.ipi == Decimal("7.50")


def test_item_total_tax(nfe) -> None:
    first = nfe.items[0]
    assert first.total_tax == Decimal("13.77") + Decimal("1.26") + Decimal("5.81")


def test_totals(nfe) -> None:
    assert nfe.totals.products == Decimal("226.40")
    assert nfe.totals.invoice_total == Decimal("233.90")
    assert nfe.totals.icms == Decimal("28.16")
    assert nfe.totals.ipi == Decimal("7.50")


def test_totals_reconcile(nfe) -> None:
    """3 x 25.50 + 149.90 = 226.40, matching the declared vProd."""
    assert nfe.computed_products_total == Decimal("226.40")
    assert nfe.totals_reconcile()


def test_tampered_total_fails_reconciliation() -> None:
    tampered = SAMPLE.replace("<vProd>226.40</vProd>", "<vProd>999.99</vProd>")
    assert not parse_nfe(tampered).totals_reconcile()


def test_protocol_and_authorization(nfe) -> None:
    assert nfe.protocol == "143240000123456"
    assert nfe.status_code == "100"
    assert nfe.is_authorized
    assert "Autorizado" in nfe.status_reason


def test_rejected_document_is_not_authorized() -> None:
    rejected = SAMPLE.replace("<cStat>100</cStat>", "<cStat>110</cStat>")
    assert not parse_nfe(rejected).is_authorized


def test_status_150_counts_as_authorized() -> None:
    late = SAMPLE.replace("<cStat>100</cStat>", "<cStat>150</cStat>")
    assert parse_nfe(late).is_authorized


# ---------------------------------------------------------------------------
# Accepted document shapes
# ---------------------------------------------------------------------------


def test_bare_nfe_element_parses() -> None:
    """Some ERPs hand over the signed <NFe> without the SEFAZ protocol wrapper."""
    inner = SAMPLE[SAMPLE.index("<NFe>") : SAMPLE.index("</NFe>") + len("</NFe>")]
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n<NFe xmlns="{NS}">{inner[len("<NFe>") :]}'
    parsed = parse_nfe(doc)
    assert parsed.number == "123"
    assert parsed.status_code == ""  # no protocol, so no status
    assert not parsed.is_authorized


def test_namespaceless_document_parses() -> None:
    """Tools that strip the namespace still produce readable documents."""
    stripped = SAMPLE.replace(f' xmlns="{NS}"', "")
    assert parse_nfe(stripped).number == "123"


def test_latin1_encoded_bytes_parse() -> None:
    """NF-e files are frequently ISO-8859-1; bytes must honor the declaration."""
    latin = SAMPLE.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').replace(
        "Comercio Exemplo Ltda", "Comércio Exemplo Ltda"
    )
    parsed = parse_nfe(latin.encode("iso-8859-1"))
    assert parsed.issuer is not None
    assert parsed.issuer.name == "Comércio Exemplo Ltda"


def test_parse_from_file(tmp_path) -> None:
    path = tmp_path / "nota.xml"
    path.write_bytes(SAMPLE.encode("utf-8"))
    assert parse_nfe_file(path).number == "123"


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_malformed_xml_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_nfe("<nfeProc><unclosed>")


def test_wrong_root_raises_unsupported() -> None:
    with pytest.raises(UnsupportedDocumentError):
        parse_nfe('<?xml version="1.0"?><cteProc></cteProc>')


def test_nfe_without_infnfe_raises() -> None:
    with pytest.raises(UnsupportedDocumentError):
        parse_nfe(f'<NFe xmlns="{NS}"><signature/></NFe>')


def test_missing_optional_blocks_degrade_to_empty() -> None:
    minimal = f'<infNFe xmlns="{NS}" Id="NFe123"><ide><nNF>7</nNF></ide></infNFe>'
    parsed = parse_nfe(minimal)
    assert parsed.number == "7"
    assert parsed.issuer is None
    assert parsed.items == []
    assert parsed.totals.invoice_total == Decimal("0")


def test_unparseable_amount_degrades_to_zero() -> None:
    """One bad number must not make an otherwise valid document unreadable."""
    broken = SAMPLE.replace("<vProd>76.50</vProd>", "<vProd>N/A</vProd>")
    parsed = parse_nfe(broken)
    assert parsed.items[0].product.total == Decimal("0")
    assert parsed.totals.invoice_total == Decimal("233.90")
