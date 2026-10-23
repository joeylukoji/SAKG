"""Extraction de la couche données : tables et colonnes déclarées par un ORM.

Seules les tables réellement déclarées dans le code entrent dans le graphe. Une clé étrangère
qui désigne une table absente du projet (base partagée, schéma tiers) ne produit aucune
relation : mieux vaut une colonne sans lien qu'un lien vers une table inventée.
"""

from dataclasses import dataclass, field

from sakg.domain import Node, NodeType, RelationType, make_node_id
from sakg.reverse.extraction import edge, node_provenance, parse_modules, top_level_symbols
from sakg.reverse.models import AttributeRef, ExtractionResult, ParsedModule, ProjectContext, Symbol
from sakg.reverse.parser import ParserRegistry

TABLE_NAME_ATTRIBUTE = "__tablename__"
TABLE_ARGS_ATTRIBUTE = "__table_args__"
COLUMN_FACTORIES = ("Column", "mapped_column")
FOREIGN_KEY = "ForeignKey"
SQLALCHEMY = "sqlalchemy"


@dataclass(frozen=True)
class TableSpec:
    """Table déclarée par une classe de modèle.

    Attributes:
        name: Nom de la table en base.
        model: Nom qualifié de la classe qui la déclare.
        module: Module déclarant.
        relative_path: Fichier déclarant.
        line: Ligne de la classe.
        schema: Schéma déclaré dans ``__table_args__``, s'il y en a un.
        columns: Colonnes déclarées.
    """

    name: str
    model: str
    module: str
    relative_path: str
    line: int
    schema: str = ""
    columns: tuple[AttributeRef, ...] = field(default_factory=tuple)

    @property
    def qualified_name(self) -> str:
        """Nom complet de la table, schéma compris : deux schémas peuvent avoir la même table."""
        return f"{self.schema}.{self.name}" if self.schema else self.name

    def column_names(self) -> set[str]:
        """Noms des colonnes tels qu'ils existent en base."""
        return {column_name(column) for column in self.columns}


def column_name(column: AttributeRef) -> str:
    """Nom d'une colonne en base.

    ``Column("email_address", String)`` nomme la colonne autrement que l'attribut Python qui
    la porte ; c'est le nom de la base qui compte, puisque le nœud décrit la base.
    """
    return column.arguments[0] if column.arguments else column.name


class DatabaseExtractor:
    """Modèles SQLAlchemy : tables, colonnes et clés étrangères.

    Une classe est reconnue comme modèle si elle déclare ``__tablename__`` : c'est le seul
    signe certain sans exécuter le code, la classe de base pouvant être définie n'importe où.
    """

    name = "database"
    order = 30

    def extract(self, context: ProjectContext, registry: ParserRegistry) -> ExtractionResult:
        """Construit les nœuds ``Table`` et ``Column`` et leurs relations."""
        result = ExtractionResult()
        modules, _unparsed, warnings = parse_modules(
            context, registry, self.name, report_missing_parsers=False
        )
        result.warnings.extend(warnings)

        tables: list[TableSpec] = []
        for module in modules:
            if not module.imports_module(SQLALCHEMY):
                continue
            tables.extend(self._tables_of(module, top_level_symbols(module)))

        by_name: dict[str, TableSpec | None] = {}
        for table in tables:
            if table.qualified_name in by_name:
                result.warnings.append(
                    f"{self.name} : table « {table.qualified_name} » déclarée plusieurs fois, "
                    "clés étrangères non résolues vers elle"
                )
                by_name[table.qualified_name] = None
            else:
                by_name[table.qualified_name] = table

        for table in tables:
            self._add_table(table, by_name, context, result)
        return result

    def _tables_of(self, module: ParsedModule, symbols: list[Symbol]) -> list[TableSpec]:
        """Classes du module qui déclarent une table."""
        lines = {symbol.qualified_name: symbol.line for symbol in symbols if symbol.kind == "class"}
        found: list[TableSpec] = []
        for model, line in lines.items():
            attributes = module.attributes_of(model)
            table_name = next(
                (attribute.value for attribute in attributes if attribute.name == TABLE_NAME_ATTRIBUTE), ""
            )
            if not table_name:
                continue
            table_args = next((attribute for attribute in attributes if attribute.name == TABLE_ARGS_ATTRIBUTE), None)
            found.append(
                TableSpec(
                    name=table_name,
                    model=model,
                    module=module.module_name,
                    relative_path=module.file.relative_path,
                    line=line,
                    schema=table_args.mapping.get("schema", "") if table_args else "",
                    columns=tuple(attribute for attribute in attributes if attribute.callee in COLUMN_FACTORIES),
                )
            )
        return found

    def _add_table(
        self,
        table: TableSpec,
        by_name: dict[str, TableSpec | None],
        context: ProjectContext,
        result: ExtractionResult,
    ) -> None:
        path = table.relative_path
        properties: dict[str, object] = {"model": table.model, "module": table.module}
        if table.schema:
            properties["schema"] = table.schema
        table_node = Node(
            id=make_node_id(NodeType.TABLE, path, table.qualified_name),
            type=NodeType.TABLE,
            name=table.name,
            properties=properties,
            provenance=node_provenance(context, path, detected_by="SQLALCHEMY_TABLENAME", line=table.line),
        )
        result.nodes.append(table_node)
        result.edges.append(
            edge(
                make_node_id(NodeType.CLASS, path, table.model),
                RelationType.MAPS_TO,
                table_node.id,
                context,
                path,
                "SQLALCHEMY_DECLARATIVE_MODEL",
                table.line,
            )
        )

        for column in table.columns:
            column_node = Node(
                id=make_node_id(NodeType.COLUMN, path, f"{table.qualified_name}.{column_name(column)}"),
                type=NodeType.COLUMN,
                name=column_name(column),
                properties=_column_properties(column),
                provenance=node_provenance(context, path, detected_by="SQLALCHEMY_COLUMN", line=column.line),
            )
            result.nodes.append(column_node)
            result.edges.append(
                edge(
                    table_node.id,
                    RelationType.CONTAINS,
                    column_node.id,
                    context,
                    path,
                    "SQLALCHEMY_COLUMN",
                    column.line,
                )
            )
            target = self._foreign_key_target(column, by_name, result)
            if target is not None:
                result.edges.append(
                    edge(
                        column_node.id,
                        RelationType.REFERENCES,
                        target,
                        context,
                        path,
                        "SQLALCHEMY_FOREIGN_KEY",
                        column.line,
                    )
                )

    def _foreign_key_target(
        self, column: AttributeRef, by_name: dict[str, TableSpec | None], result: ExtractionResult
    ) -> str | None:
        """Colonne visée par une clé étrangère ``ForeignKey("orders.id")``, si elle existe vraiment.

        La référence peut être qualifiée par un schéma (``"sales.customers.id"``). Une table
        d'un autre schéma n'est pas la même table : à défaut de correspondance exacte, aucune
        relation n'est créée.
        """
        references = column.nested.get(FOREIGN_KEY, ())
        if not references or "." not in references[0]:
            return None
        qualified_table, _, target_column = references[0].rpartition(".")
        target = by_name.get(qualified_table)
        if target is None:
            return None
        if target_column not in target.column_names():
            result.warnings.append(
                f"{self.name} : clé étrangère vers « {references[0]} » ; la colonne "
                f"« {target_column} » n'est pas déclarée dans le modèle de {qualified_table}"
            )
            return None
        return make_node_id(NodeType.COLUMN, target.relative_path, f"{target.qualified_name}.{target_column}")


def _column_properties(column: AttributeRef) -> dict[str, object]:
    """Ce qu'on sait d'une colonne sans exécuter le code."""
    properties: dict[str, object] = {}
    # ``Column(Integer)`` donne un nom, ``Column(String(255))`` un appel : les deux nomment le type.
    parameterised = next((name for name in column.nested if name != FOREIGN_KEY), "")
    sql_type = column.argument_names[0] if column.argument_names else parameterised
    if sql_type:
        properties["sql_type"] = sql_type
    if column.arguments and column.arguments[0] != column.name:
        properties["attribute"] = column.name  # le nom en base diffère du nom Python
    properties.update(column.booleans)
    return properties
