"""
Country-specific tax module system.

Usage:
    from src.tax import get_tax_module, TaxModule

    module = get_tax_module("US")  # USTaxModule
    module = get_tax_module("DE")  # GermanTaxModule
"""
from src.tax.base import TaxModule
from src.tax.models import (
    Exemption,
    HoldingPeriod,
    IncomeCategory,
    ReportFile,
    TaxSummary,
)

# Registry of country code -> module class
_REGISTRY: dict[str, type[TaxModule]] = {}


def register_module(cls: type[TaxModule]) -> type[TaxModule]:
    """Decorator to register a TaxModule subclass."""
    _REGISTRY[cls.country_code] = cls
    return cls


def get_tax_module(country_code: str) -> TaxModule:
    """
    Get an instantiated TaxModule for the given country code.

    Args:
        country_code: ISO 3166-1 alpha-2 code (e.g. "US", "DE")

    Returns:
        Instantiated TaxModule subclass

    Raises:
        ValueError: if country code is not supported
    """
    code = country_code.upper()

    # Lazy-import modules to populate registry
    if not _REGISTRY:
        _load_modules()

    if code not in _REGISTRY:
        supported = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unsupported country code: {code!r}. Supported: {supported}"
        )

    return _REGISTRY[code]()


def get_supported_countries() -> list[dict[str, str]]:
    """Return list of supported countries with their metadata."""
    if not _REGISTRY:
        _load_modules()

    result = []
    for code, cls in sorted(_REGISTRY.items()):
        result.append({
            "code": code,
            "name": cls.country_name,
            "currency": cls.currency_code,
        })
    return result


def _load_modules() -> None:
    """Import all country modules to trigger registration."""
    # Each module's __init__.py calls register_module
    import src.tax.us  # noqa: F401
    import src.tax.de  # noqa: F401


__all__ = [
    "TaxModule",
    "HoldingPeriod",
    "Exemption",
    "TaxSummary",
    "ReportFile",
    "IncomeCategory",
    "get_tax_module",
    "get_supported_countries",
    "register_module",
]
