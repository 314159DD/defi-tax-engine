"""US Tax Module - IRS rules for cryptocurrency taxation."""
from src.tax import register_module
from src.tax.us.module import USTaxModule

register_module(USTaxModule)

__all__ = ["USTaxModule"]
