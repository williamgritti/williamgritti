"""Typed representations of the parts of an NF-e that callers actually consume.

Monetary values use :class:`~decimal.Decimal`. NF-e amounts are fixed-point with
two decimal places (unit prices allow more), and binary floats silently corrupt
the totals that tax authorities reconcile to the cent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

__all__ = ["Address", "Item", "NFe", "Party", "Product", "Totals"]

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Address:
    """A postal address as it appears in ``enderEmit`` or ``enderDest``."""

    street: str = ""
    number: str = ""
    complement: str = ""
    district: str = ""
    city_code: str = ""
    city: str = ""
    uf: str = ""
    zip_code: str = ""
    country: str = "Brasil"

    @property
    def one_line(self) -> str:
        """The address collapsed into a single readable line."""
        head = ", ".join(p for p in (self.street, self.number, self.complement) if p)
        tail = ", ".join(p for p in (self.district, self.city, self.uf) if p)
        return " - ".join(p for p in (head, tail) if p)


@dataclass(frozen=True, slots=True)
class Party:
    """An issuer (``emit``) or recipient (``dest``)."""

    name: str = ""
    trade_name: str = ""
    cnpj: str = ""
    cpf: str = ""
    ie: str = ""
    email: str = ""
    address: Address | None = None

    @property
    def tax_id(self) -> str:
        """The party's CNPJ when present, otherwise its CPF."""
        return self.cnpj or self.cpf

    @property
    def is_company(self) -> bool:
        """Whether this party is identified by a CNPJ."""
        return bool(self.cnpj)


@dataclass(frozen=True, slots=True)
class Product:
    """The ``prod`` block of a line item."""

    code: str = ""
    ean: str = ""
    description: str = ""
    ncm: str = ""
    cfop: str = ""
    unit: str = ""
    quantity: Decimal = ZERO
    unit_price: Decimal = ZERO
    total: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class Item:
    """One numbered line of the invoice, product plus its taxes."""

    number: int
    product: Product
    icms: Decimal = ZERO
    ipi: Decimal = ZERO
    pis: Decimal = ZERO
    cofins: Decimal = ZERO
    icms_cst: str = ""
    icms_origin: str = ""

    @property
    def total_tax(self) -> Decimal:
        """Sum of the taxes recorded on this line."""
        return self.icms + self.ipi + self.pis + self.cofins


@dataclass(frozen=True, slots=True)
class Totals:
    """The ``ICMSTot`` block: the document's own declared totals."""

    products: Decimal = ZERO
    icms_base: Decimal = ZERO
    icms: Decimal = ZERO
    ipi: Decimal = ZERO
    pis: Decimal = ZERO
    cofins: Decimal = ZERO
    freight: Decimal = ZERO
    insurance: Decimal = ZERO
    discount: Decimal = ZERO
    other: Decimal = ZERO
    invoice_total: Decimal = ZERO

    @property
    def total_tax(self) -> Decimal:
        """Sum of ICMS, IPI, PIS and COFINS as declared in the totals block."""
        return self.icms + self.ipi + self.pis + self.cofins


@dataclass(slots=True)
class NFe:
    """A parsed NF-e.

    ``access_key`` is the raw 44-digit string; decode it with
    :class:`~fiscalkit.nfe.chave.AccessKey` when you need its fields.
    """

    access_key: str = ""
    number: str = ""
    series: str = ""
    model: str = ""
    issued_at: datetime | None = None
    operation_nature: str = ""
    issuer: Party | None = None
    recipient: Party | None = None
    items: list[Item] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)
    protocol: str = ""
    status_code: str = ""
    status_reason: str = ""

    @property
    def is_authorized(self) -> bool:
        """Whether SEFAZ returned an authorization status.

        ``100`` is a plain authorization and ``150`` an authorization recorded
        outside the normal window. Both mean the document is valid.
        """
        return self.status_code in ("100", "150")

    @property
    def item_count(self) -> int:
        """Number of line items."""
        return len(self.items)

    @property
    def computed_products_total(self) -> Decimal:
        """Sum of the line totals, for reconciling against :attr:`Totals.products`.

        A mismatch against the declared total is a strong signal of a tampered or
        malformed document.
        """
        return sum((item.product.total for item in self.items), ZERO)

    def totals_reconcile(self, *, tolerance: Decimal = Decimal("0.01")) -> bool:
        """Whether the summed line totals match the declared product total.

        Args:
            tolerance: Allowed absolute difference, defaulting to one cent to
                absorb the rounding the layout itself permits.
        """
        return abs(self.computed_products_total - self.totals.products) <= tolerance
