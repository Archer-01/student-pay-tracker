"""A money type for request schemas.

Money is a decimal **string** end to end (never a float). Values that round-trip the database come
back at the column's scale — ``Numeric(10, 2)``, so ``"150.00"`` — but a value taken straight from
a request and echoed back would render however the client wrote it (``"200"``). Mixing the two in
one response is confusing, so incoming money is normalised to two decimal places at the edge.

Normalised, never rounded: ``"199.999"`` passes through as it is, for the service to refuse with
a translated reason (rounded, ``"0.004"`` became a price of 0, a student silently free). At most
ten digits, the column's, so an absurd ``"1e30"`` is a 422 rather than a crash further in.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field

_CENTS = Decimal("0.01")


def _to_cents(value: Decimal) -> Decimal:
    """``"200"`` → ``"200.00"``; a value with more decimals is left for the service to refuse."""
    cents = value.quantize(_CENTS)
    return cents if cents == value else value


Money = Annotated[Decimal, Field(max_digits=10, allow_inf_nan=False), AfterValidator(_to_cents)]
