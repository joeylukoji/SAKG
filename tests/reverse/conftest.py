from pathlib import Path

import pytest

SERVICE = '''
"""Service de paiement."""

from core.base import BaseService
from core import helpers


class PaymentService(BaseService):
    """Encaisse les paiements."""

    def pay(self, amount: int) -> bool:
        helpers.audit(amount)
        return self.charge(amount)

    def refund(self, amount: int) -> bool:
        return True


def build_service() -> PaymentService:
    def inner() -> None:  # fonction imbriquée : volontairement absente du graphe
        pass

    inner()
    return PaymentService()
'''

BASE = """
class BaseService:
    def charge(self, amount: int) -> bool:
        return amount > 0
"""

HELPERS = """
def audit(amount: int) -> None:
    pass
"""

BROKEN = "def broken(:\n"


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Mini-projet : payment/service.py, core/base.py, core/helpers.py."""
    (tmp_path / "payment").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "payment" / "service.py").write_text(SERVICE, encoding="utf-8")
    (tmp_path / "core" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "base.py").write_text(BASE, encoding="utf-8")
    (tmp_path / "core" / "helpers.py").write_text(HELPERS, encoding="utf-8")
    return tmp_path
