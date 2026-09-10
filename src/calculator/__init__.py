"""
Cost basis calculator - FIFO, LIFO, HIFO with DeFi-specific handling.

Public API:
    CalculatorEngine   - main orchestration class
    compare_methods    - run all three methods and return a MethodComparison
    TaxLot             - acquisition lot dataclass
    Disposal           - realized gain/loss event dataclass
    LotManager         - in-memory lot book
"""

from src.calculator.engine import CalculatorEngine, CostBasisEngine, MethodComparison, compare_methods
from src.calculator.lots import Disposal, LotManager, TaxLot, holding_period

__all__ = [
    "CalculatorEngine",
    "CostBasisEngine",
    "MethodComparison",
    "compare_methods",
    "Disposal",
    "LotManager",
    "TaxLot",
    "holding_period",
]
