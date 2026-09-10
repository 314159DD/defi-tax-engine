"""German Tax Module - EStG rules for cryptocurrency taxation."""
from src.tax import register_module
from src.tax.de.module import GermanTaxModule

register_module(GermanTaxModule)

__all__ = ["GermanTaxModule"]
