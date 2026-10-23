"""Extraction de la couche données : une table du graphe doit exister dans le code."""

from pathlib import Path

import pytest

from sakg.domain import EvidenceType, NodeType, RelationType
from sakg.reverse import DatabaseExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.models import ExtractionResult

ORDERS = '''
"""Modèle des commandes."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    reference = Column(String(32), nullable=False)
'''

ITEMS = """
from sqlalchemy import Column, ForeignKey, Integer

from models.orders import Base


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    label = Column(String)
"""

PLAIN = """
class NotAModel:
    value = 1
"""


@pytest.fixture
def orm_project(tmp_path: Path) -> Path:
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "models" / "orders.py").write_text(ORDERS, encoding="utf-8")
    (tmp_path / "models" / "items.py").write_text(ITEMS, encoding="utf-8")
    (tmp_path / "plain.py").write_text(PLAIN, encoding="utf-8")
    return tmp_path


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root, commit_sha="abc123")
    return DatabaseExtractor().extract(context, ParserRegistry([PythonAstParser()]))


def _pairs(result: ExtractionResult, relation: RelationType) -> set[tuple[str, str]]:
    return {(edge.source_id, edge.target_id) for edge in result.edges if edge.relation == relation}


def test_tables_are_extracted_from_models(orm_project: Path) -> None:
    result = _extract(orm_project)

    assert {node.name for node in result.nodes if node.type == NodeType.TABLE} == {"orders", "order_items"}


def test_a_class_without_tablename_is_not_a_table(orm_project: Path) -> None:
    result = _extract(orm_project)

    assert all(node.name != "NotAModel" for node in result.nodes)
    assert all("plain.py" not in node.id for node in result.nodes)


def test_model_maps_to_its_table(orm_project: Path) -> None:
    assert ("class:models/orders.py::Order", "table:models/orders.py::orders") in _pairs(
        _extract(orm_project), RelationType.MAPS_TO
    )


def test_columns_belong_to_their_table(orm_project: Path) -> None:
    contains = _pairs(_extract(orm_project), RelationType.CONTAINS)

    assert ("table:models/orders.py::orders", "column:models/orders.py::orders.id") in contains
    assert ("table:models/orders.py::orders", "column:models/orders.py::orders.reference") in contains


def test_column_properties_and_provenance(orm_project: Path) -> None:
    result = _extract(orm_project)
    column = next(node for node in result.nodes if node.id.endswith("::orders.id"))

    assert column.properties == {"sql_type": "Integer", "primary_key": True}
    assert column.provenance.evidence_type == EvidenceType.OBSERVED
    assert column.provenance.detected_by == "SQLALCHEMY_COLUMN"
    assert column.provenance.commit_sha == "abc123"


def test_foreign_key_crosses_files(orm_project: Path) -> None:
    assert ("column:models/items.py::order_items.order_id", "column:models/orders.py::orders.id") in _pairs(
        _extract(orm_project), RelationType.REFERENCES
    )


def test_a_foreign_key_to_an_unknown_table_is_ignored(tmp_path: Path) -> None:
    """Une base partagée n'est pas dans le projet : aucune relation ne doit être inventée."""
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, ForeignKey, Integer\n\n\nclass Item:\n    __tablename__ = "items"\n\n'
        '    tenant_id = Column(Integer, ForeignKey("tenants.id"))\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert {node.name for node in result.nodes if node.type == NodeType.TABLE} == {"items"}
    assert _pairs(result, RelationType.REFERENCES) == set()


def test_a_duplicated_table_name_disables_resolution(tmp_path: Path) -> None:
    for module in ("first", "second"):
        (tmp_path / f"{module}.py").write_text(
            f'from sqlalchemy import Column, Integer\n\n\nclass Model{module}:\n    __tablename__ = "users"\n\n'
            "    id = Column(Integer, primary_key=True)\n",
            encoding="utf-8",
        )
    (tmp_path / "link.py").write_text(
        'from sqlalchemy import Column, ForeignKey, Integer\n\n\nclass Link:\n    __tablename__ = "links"\n\n'
        '    user_id = Column(Integer, ForeignKey("users.id"))\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert any("déclarée plusieurs fois" in warning for warning in result.warnings)
    assert _pairs(result, RelationType.REFERENCES) == set()


def test_sqlalchemy_two_point_zero_mapped_column(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        "from sqlalchemy.orm import Mapped, mapped_column\nfrom sqlalchemy import Integer\n\n\n"
        'class User:\n    __tablename__ = "users"\n\n    id: Mapped[int] = mapped_column(Integer, primary_key=True)\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert {node.name for node in result.nodes if node.type == NodeType.COLUMN} == {"id"}


def test_two_schemas_may_hold_the_same_table_name(tmp_path: Path) -> None:
    """``billing.customers`` et ``sales.customers`` sont deux tables : ne pas les confondre."""
    (tmp_path / "billing.py").write_text(
        'from sqlalchemy import Column, Integer\n\n\nclass BillingCustomer:\n    __tablename__ = "customers"\n'
        '    __table_args__ = {"schema": "billing"}\n\n    id = Column(Integer, primary_key=True)\n',
        encoding="utf-8",
    )
    (tmp_path / "invoices.py").write_text(
        'from sqlalchemy import Column, ForeignKey, Integer\n\n\nclass Invoice:\n    __tablename__ = "invoices"\n\n'
        '    cust_id = Column(Integer, ForeignKey("sales.customers.id"))\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert _pairs(result, RelationType.REFERENCES) == set()  # « sales » n'est pas « billing »
    assert "table:billing.py::billing.customers" in {node.id for node in result.nodes}


def test_a_foreign_key_resolves_within_its_own_schema(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, ForeignKey, Integer\n\n\nclass Customer:\n    __tablename__ = "customers"\n'
        '    __table_args__ = {"schema": "billing"}\n\n    id = Column(Integer, primary_key=True)\n\n\n'
        'class Invoice:\n    __tablename__ = "invoices"\n\n'
        '    cust_id = Column(Integer, ForeignKey("billing.customers.id"))\n',
        encoding="utf-8",
    )

    assert ("column:models.py::invoices.cust_id", "column:models.py::billing.customers.id") in _pairs(
        _extract(tmp_path), RelationType.REFERENCES
    )


def test_a_column_is_named_after_the_database_not_the_attribute(tmp_path: Path) -> None:
    """``Column("email_address", ...)`` crée la colonne ``email_address``, pas ``email``."""
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, String\n\n\nclass Customer:\n    __tablename__ = "customers"\n\n'
        '    email = Column("email_address", String(255), nullable=False)\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)
    column = next(node for node in result.nodes if node.type == NodeType.COLUMN)

    assert column.name == "email_address"
    assert column.id == "column:models.py::customers.email_address"
    assert column.properties == {"sql_type": "String", "attribute": "email", "nullable": False}


def test_a_foreign_key_to_an_unknown_column_is_reported(tmp_path: Path) -> None:
    """La table existe mais pas la colonne : aucune relation, et l'utilisateur est prévenu."""
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, ForeignKey, Integer\n\n\nclass Order:\n    __tablename__ = "orders"\n\n'
        "    id = Column(Integer, primary_key=True)\n\n\n"
        'class Line:\n    __tablename__ = "lines"\n\n'
        '    order_id = Column(Integer, ForeignKey("orders.absente"))\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert _pairs(result, RelationType.REFERENCES) == set()
    assert any("n'est pas déclarée" in warning for warning in result.warnings)


def test_mapped_annotation_without_a_call_declares_no_column(tmp_path: Path) -> None:
    """Forme SQLAlchemy 2.0 sans appel : rien n'est extrait, ce qui vaut mieux qu'un faux."""
    (tmp_path / "models.py").write_text(
        'from sqlalchemy.orm import Mapped\n\n\nclass User:\n    __tablename__ = "users"\n\n    id: Mapped[int]\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert {node.type for node in result.nodes} == {NodeType.TABLE}


def test_columns_declared_by_a_mixin_are_not_attached(tmp_path: Path) -> None:
    """Les colonnes d'un mixin appartiennent à une autre classe : elles ne sont pas inventées ici."""
    (tmp_path / "models.py").write_text(
        "from sqlalchemy import Column, DateTime, Integer\n\n\nclass TimestampMixin:\n"
        "    created_at = Column(DateTime)\n\n\n"
        'class User(TimestampMixin):\n    __tablename__ = "users"\n\n    id = Column(Integer, primary_key=True)\n',
        encoding="utf-8",
    )

    result = _extract(tmp_path)

    assert {node.name for node in result.nodes if node.type == NodeType.COLUMN} == {"id"}


def test_a_project_without_sqlalchemy_has_no_table(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text('class Thing:\n    __tablename__ = "things"\n', encoding="utf-8")

    assert _extract(tmp_path).nodes == []
