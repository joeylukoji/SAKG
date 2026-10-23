"""Cas pièges de résolution : le graphe ne doit jamais affirmer une relation fausse."""

from pathlib import Path

import pytest

from sakg.domain import Edge, NodeType, RelationType
from sakg.reverse import CodeStructureExtractor, ParserRegistry, ProjectScanner, PythonAstParser
from sakg.reverse.models import ExtractionResult


def _extract(root: Path) -> ExtractionResult:
    context = ProjectScanner().scan(root)
    return CodeStructureExtractor().extract(context, ParserRegistry([PythonAstParser()]))


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _pairs(result: ExtractionResult, relation: RelationType) -> set[tuple[str, str]]:
    return {(edge.source_id, edge.target_id) for edge in result.edges if edge.relation == relation}


def test_inheriting_from_a_third_party_class_does_not_link_a_homonym(tmp_path: Path) -> None:
    """``enum.Enum`` ne doit pas être relié à une classe ``Enum`` du projet."""
    _write(tmp_path, "models.py", "import enum\n\n\nclass Enum:\n    pass\n\n\nclass Color(enum.Enum):\n    pass\n")

    result = _extract(tmp_path)

    assert _pairs(result, RelationType.INHERITS) == set()


def test_inheritance_through_an_imported_name(tmp_path: Path) -> None:
    _write(tmp_path, "core/__init__.py", "")
    _write(tmp_path, "core/base.py", "class BaseService:\n    pass\n")
    _write(tmp_path, "app.py", "from core.base import BaseService\n\n\nclass Service(BaseService):\n    pass\n")

    assert ("class:app.py::Service", "class:core/base.py::BaseService") in _pairs(
        _extract(tmp_path), RelationType.INHERITS
    )


def test_inheritance_through_a_module_alias(tmp_path: Path) -> None:
    _write(tmp_path, "core/__init__.py", "")
    _write(tmp_path, "core/base.py", "class BaseService:\n    pass\n")
    _write(tmp_path, "app.py", "import core.base as cb\n\n\nclass Service(cb.BaseService):\n    pass\n")

    assert ("class:app.py::Service", "class:core/base.py::BaseService") in _pairs(
        _extract(tmp_path), RelationType.INHERITS
    )


def test_inheritance_from_a_subscripted_base(tmp_path: Path) -> None:
    _write(tmp_path, "base.py", "class Repository:\n    pass\n")
    _write(tmp_path, "sql.py", "from base import Repository\n\n\nclass SqlRepository(Repository[int]):\n    pass\n")

    assert ("class:sql.py::SqlRepository", "class:base.py::Repository") in _pairs(
        _extract(tmp_path), RelationType.INHERITS
    )


def test_decorator_is_not_a_call_of_the_decorated_function(tmp_path: Path) -> None:
    _write(tmp_path, "helpers.py", "def post(path):\n    pass\n")
    _write(tmp_path, "api.py", 'import helpers\n\n\n@helpers.post("/pay")\ndef pay():\n    pass\n')

    result = _extract(tmp_path)

    assert _pairs(result, RelationType.CALLS) == set()


def test_method_called_on_a_third_party_object_is_not_linked(tmp_path: Path) -> None:
    """``logger.warning(...)`` ne doit pas pointer vers une fonction ``warning`` du projet."""
    _write(tmp_path, "report.py", "def warning(message):\n    pass\n")
    _write(
        tmp_path,
        "service.py",
        "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
        "class Service:\n    def handle(self):\n        logger.warning('hello')\n",
    )

    result = _extract(tmp_path)

    assert all(not target.endswith("::warning") for _, target in _pairs(result, RelationType.CALLS))


def test_self_call_resolves_on_the_class_then_on_its_bases(tmp_path: Path) -> None:
    _write(tmp_path, "base.py", "class Base:\n    def charge(self):\n        pass\n")
    _write(
        tmp_path,
        "service.py",
        "from base import Base\n\n\nclass Service(Base):\n    def pay(self):\n        return self.charge()\n",
    )
    _write(tmp_path, "other.py", "class Other:\n    def charge(self):\n        pass\n")

    calls = _pairs(_extract(tmp_path), RelationType.CALLS)

    assert ("method:service.py::Service.pay", "method:base.py::Base.charge") in calls
    assert ("method:service.py::Service.pay", "method:other.py::Other.charge") not in calls


def test_same_method_name_on_another_class_is_not_linked(tmp_path: Path) -> None:
    _write(tmp_path, "repo.py", "class Repository:\n    def save(self, item):\n        pass\n")
    _write(
        tmp_path,
        "service.py",
        "class Service:\n    def handle(self, session):\n        session.save(1)\n",
    )

    assert _pairs(_extract(tmp_path), RelationType.CALLS) == set()


def test_nested_class_methods_are_not_extracted(tmp_path: Path) -> None:
    _write(tmp_path, "models.py", "class Box:\n    class Meta:\n        def label(self):\n            pass\n")

    result = _extract(tmp_path)

    assert {node.id for node in result.nodes if node.type != NodeType.FILE} == {"class:models.py::Box"}


def test_every_symbol_has_exactly_one_containing_parent(tmp_path: Path) -> None:
    """Invariant : aucun nœud orphelin, et le parent est toujours dans le même fichier."""
    _write(tmp_path, "models.py", "class Box:\n    class Meta:\n        def label(self):\n            pass\n")
    _write(tmp_path, "api.py", "def outer():\n    def inner():\n        pass\n\n    inner()\n")
    _write(tmp_path, "svc.py", "class A:\n    @property\n    def x(self):\n        return 1\n")

    result = _extract(tmp_path)

    parents: dict[str, list[str]] = {}
    for edge in result.edges:
        if edge.relation == RelationType.CONTAINS:
            parents.setdefault(edge.target_id, []).append(edge.source_id)
    for node in result.nodes:
        if node.type == NodeType.FILE:
            continue
        assert len(parents.get(node.id, [])) == 1, f"{node.id} n'a pas exactement un parent"
        source_path = parents[node.id][0].split(":", 1)[1].split("::")[0]
        assert source_path == node.id.split(":", 1)[1].split("::")[0]


def test_call_from_a_nested_function_is_attached_to_its_enclosing_symbol(tmp_path: Path) -> None:
    _write(tmp_path, "helpers.py", "def audit(x):\n    pass\n")
    _write(
        tmp_path,
        "svc.py",
        "from helpers import audit\n\n\nclass Service:\n    def run(self):\n"
        "        def inner():\n            audit(1)\n\n        inner()\n",
    )

    assert ("method:svc.py::Service.run", "function:helpers.py::audit") in _pairs(
        _extract(tmp_path), RelationType.CALLS
    )


def test_property_and_setter_produce_a_single_node(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "svc.py",
        "class A:\n    @property\n    def value(self):\n        return 1\n\n"
        "    @value.setter\n    def value(self, v):\n        pass\n",
    )

    result = _extract(tmp_path)

    assert len([node for node in result.nodes if node.id.endswith("::A.value")]) == 1


def test_module_name_collision_disables_resolution_and_warns(tmp_path: Path) -> None:
    """``src/conf.py`` et ``conf.py`` portent le même nom de module : aucun lien inter-fichiers."""
    _write(tmp_path, "src/conf.py", "def setting():\n    pass\n")
    _write(tmp_path, "conf.py", "def other():\n    pass\n")
    _write(tmp_path, "app.py", "import conf\n\n\ndef run():\n    conf.other()\n")

    result = _extract(tmp_path)

    assert any("ambigu" in warning for warning in result.warnings)
    assert _pairs(result, RelationType.CALLS) == set()
    for source, target in _pairs(result, RelationType.CONTAINS):
        assert source.split("::")[0].split(":", 1)[1] == target.split("::")[0].split(":", 1)[1]


def test_from_package_import_submodule_creates_the_dependency(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/util.py", "def helper():\n    pass\n")
    _write(tmp_path, "consumer.py", "from pkg import util\n\n\ndef run():\n    util.helper()\n")

    result = _extract(tmp_path)

    assert ("file:consumer.py::consumer", "file:pkg/util.py::pkg.util") in _pairs(result, RelationType.DEPENDS_ON)
    assert ("function:consumer.py::run", "function:pkg/util.py::helper") in _pairs(result, RelationType.CALLS)


def test_aliased_import_of_a_name(tmp_path: Path) -> None:
    _write(tmp_path, "helpers.py", "def audit(x):\n    pass\n")
    _write(tmp_path, "svc.py", "from helpers import audit as check\n\n\ndef run():\n    check(1)\n")

    assert ("function:svc.py::run", "function:helpers.py::audit") in _pairs(_extract(tmp_path), RelationType.CALLS)


def test_type_checking_import_is_a_dependency_marked_as_such(tmp_path: Path) -> None:
    """Une dépendance de typage compte dans l'architecture, mais ne pèse pas à l'exécution."""
    _write(tmp_path, "models.py", "class User:\n    pass\n")
    _write(
        tmp_path,
        "svc.py",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from models import User\n",
    )

    result = _extract(tmp_path)

    depends = {
        (edge.source_id, edge.target_id): edge for edge in result.edges if edge.relation == RelationType.DEPENDS_ON
    }
    assert depends[("file:svc.py::svc", "file:models.py::models")].properties["type_only"] is True
    assert depends[("file:svc.py::svc", "class:models.py::User")].properties["type_only"] is True


def test_a_runtime_import_is_not_marked_type_only(tmp_path: Path) -> None:
    _write(tmp_path, "models.py", "class User:\n    pass\n")
    _write(tmp_path, "svc.py", "from models import User\n")

    edge = next(edge for edge in _extract(tmp_path).edges if edge.relation == RelationType.DEPENDS_ON)
    assert edge.properties == {}


def test_a_module_imported_both_ways_is_a_runtime_dependency(tmp_path: Path) -> None:
    """Le bloc TYPE_CHECKING vient en premier, mais le module est bien importé à l'exécution."""
    _write(tmp_path, "models.py", "class User:\n    pass\n\n\ndef load():\n    pass\n")
    _write(
        tmp_path,
        "svc.py",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from models import User\n\n"
        "from models import load\n",
    )

    depends = _depends_on(_extract(tmp_path))
    assert depends[("file:svc.py::svc", "file:models.py::models")].properties == {}  # le module sert à l'exécution
    assert depends[("file:svc.py::svc", "class:models.py::User")].properties == {"type_only": True}
    assert depends[("file:svc.py::svc", "function:models.py::load")].properties == {}


def test_a_named_import_makes_the_symbol_answer_dependents(tmp_path: Path) -> None:
    """« Qui utilise BaseService ? » : les fichiers qui l'importent, et non une liste vide."""
    _write(tmp_path, "base.py", "class BaseService:\n    pass\n")
    _write(tmp_path, "api.py", "from base import BaseService\n")
    _write(tmp_path, "worker.py", "import base\n")

    depends = _depends_on(_extract(tmp_path))

    assert ("file:api.py::api", "class:base.py::BaseService") in depends
    # « import base » désigne le module, pas la classe : aucune relation vers le symbole
    assert ("file:worker.py::worker", "class:base.py::BaseService") not in depends


def test_inheritance_through_a_package_reexport(tmp_path: Path) -> None:
    """``from pkg import Base`` où ``pkg/__init__.py`` ré-exporte ``pkg.base.Base``."""
    _write(tmp_path, "pkg/__init__.py", "from pkg.base import Base\n")
    _write(tmp_path, "pkg/base.py", "class Base:\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import Base\n\n\nclass Child(Base):\n    pass\n")

    result = _extract(tmp_path)

    assert ("class:app.py::Child", "class:pkg/base.py::Base") in _pairs(result, RelationType.INHERITS)
    assert ("file:app.py::app", "class:pkg/base.py::Base") in _depends_on(result)


def test_a_chain_of_reexports_is_followed(tmp_path: Path) -> None:
    """Deux niveaux : ``top`` ré-exporte ``top.mid``, qui ré-exporte ``top.mid.impl``."""
    _write(tmp_path, "top/__init__.py", "from top.mid import helper\n")
    _write(tmp_path, "top/mid/__init__.py", "from top.mid.impl import helper\n")
    _write(tmp_path, "top/mid/impl.py", "def helper():\n    pass\n")
    _write(tmp_path, "app.py", "from top import helper\n\n\ndef run():\n    helper()\n")

    calls = _pairs(_extract(tmp_path), RelationType.CALLS)

    assert ("function:app.py::run", "function:top/mid/impl.py::helper") in calls


def test_a_name_the_package_does_not_export_is_not_invented(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/base.py", "class Base:\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import Base\n\n\nclass Child(Base):\n    pass\n")

    assert _pairs(_extract(tmp_path), RelationType.INHERITS) == set()


def test_an_import_fallback_is_ambiguous(tmp_path: Path) -> None:
    """``try: from .fast import impl / except ImportError: from .slow import impl`` :
    lequel s'exécute dépend de l'environnement, aucune relation ne doit l'affirmer."""
    _write(
        tmp_path,
        "pkg/__init__.py",
        "try:\n    from pkg.fast import impl\nexcept ImportError:\n    from pkg.slow import impl\n",
    )
    _write(tmp_path, "pkg/fast.py", "def impl():\n    pass\n")
    _write(tmp_path, "pkg/slow.py", "def impl():\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import impl\n\n\ndef run():\n    impl()\n")

    result = _extract(tmp_path)

    assert _pairs(result, RelationType.CALLS) == set()
    assert not any(target.endswith("::impl") for _, target in _depends_on(result))
    assert any("lié plusieurs fois" in warning for warning in result.warnings)


def test_a_name_both_defined_and_imported_is_ambiguous(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "class Base:\n    pass\n\n\nfrom pkg.other import Base\n")
    _write(tmp_path, "pkg/other.py", "class Base:\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import Base\n\n\nclass Child(Base):\n    pass\n")

    assert _pairs(_extract(tmp_path), RelationType.INHERITS) == set()


def test_a_fallback_in_the_importing_file_is_ambiguous_too(tmp_path: Path) -> None:
    _write(tmp_path, "fast.py", "def impl():\n    pass\n")
    _write(tmp_path, "slow.py", "def impl():\n    pass\n")
    _write(
        tmp_path,
        "app.py",
        "try:\n    from fast import impl\nexcept ImportError:\n    from slow import impl\n\n\ndef run():\n    impl()\n",
    )

    assert _pairs(_extract(tmp_path), RelationType.CALLS) == set()


def test_an_import_inside_a_function_is_not_a_reexport(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "def load():\n    from pkg.impl import Engine\n    return Engine\n")
    _write(tmp_path, "pkg/impl.py", "class Engine:\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import Engine\n")

    assert ("file:app.py::app", "class:pkg/impl.py::Engine") not in _depends_on(_extract(tmp_path))


def test_a_relative_reexport_under_an_alias(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import helper as public_helper\n")
    _write(tmp_path, "pkg/impl.py", "def helper():\n    pass\n")
    _write(tmp_path, "app.py", "from pkg import public_helper\n\n\ndef run():\n    public_helper()\n")

    assert ("function:app.py::run", "function:pkg/impl.py::helper") in _pairs(_extract(tmp_path), RelationType.CALLS)


def test_a_symbol_imported_for_typing_then_at_runtime_is_a_runtime_dependency(tmp_path: Path) -> None:
    """Ordre inverse du cas du module : c'est l'existence d'un import d'exécution qui compte."""
    _write(tmp_path, "models.py", "class User:\n    pass\n")
    _write(
        tmp_path,
        "svc.py",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from models import User\n\n\n"
        "def build():\n    from models import User\n    return User()\n",
    )

    assert _depends_on(_extract(tmp_path))[("file:svc.py::svc", "class:models.py::User")].properties == {}


def test_circular_reexports_terminate(tmp_path: Path) -> None:
    _write(tmp_path, "a/__init__.py", "from b import thing\n")
    _write(tmp_path, "b/__init__.py", "from a import thing\n")
    _write(tmp_path, "app.py", "from a import thing\n\n\ndef run():\n    thing()\n")

    assert _pairs(_extract(tmp_path), RelationType.CALLS) == set()


def test_an_imported_constant_creates_no_symbol_dependency(tmp_path: Path) -> None:
    """Une constante n'est pas un nœud du graphe : seul le fichier en dépend."""
    _write(tmp_path, "base.py", "VERSION = 1\n\n\nclass Base:\n    pass\n")
    _write(tmp_path, "api.py", "from base import VERSION\n")

    depends = _depends_on(_extract(tmp_path))

    assert [target for source, target in depends if source == "file:api.py::api"] == ["file:base.py::base"]


@pytest.mark.parametrize("source", ["from ..... import x\n", "from ... import y\n"])
def test_relative_import_beyond_the_root_is_ignored(tmp_path: Path, source: str) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/mod.py", source)

    assert _pairs(_extract(tmp_path), RelationType.DEPENDS_ON) == set()


def _depends_on(result: ExtractionResult) -> dict[tuple[str, str], Edge]:
    return {(edge.source_id, edge.target_id): edge for edge in result.edges if edge.relation == RelationType.DEPENDS_ON}
