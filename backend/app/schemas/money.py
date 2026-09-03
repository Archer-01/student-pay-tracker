"""A money type for request schemas.

Money is a decimal **string** end to end (never a float). Values that round-trip the database come
back at the column's scale — ``Numeric(10, 2)``, so ``"150.00"`` — but a value taken straight from
a request and echoed back would render however the client wrote it (``"200"``). Mixing the two in
one response is confusing, so incoming money is normalised to two decimal places at the edge.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator

_CENTS = Decimal("0.01")


def _to_cents(value: Decimal) -> Decimal:
    """Quantize to 2dp, matching the ``Numeric(10, 2)`` columns money is stored in."""
    return value.quantize(_CENTS)


Money = Annotated[Decimal, AfterValidator(_to_cents)]
