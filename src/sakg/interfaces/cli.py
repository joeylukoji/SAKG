"""CLI ``sakg`` : usage local et intégration continue.

Conformément à la règle 2 d'AGENTS.md, ce module n'appelle que ``ArchitectureService``.
"""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from sakg.application import ArchitectureService
from sakg.domain import Node, NodeType, SakgError
from sakg.generation import DiagramView, UnsupportedViewError

app = typer.Typer(
    help="SAKG — graphe de connaissances de l'architecture logicielle.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def main() -> None:
    """Point d'entrée : traduit les erreurs attendues en message lisible et code de sortie.

    Un traceback Python n'aide ni un utilisateur en ligne de commande, ni un journal de CI.
    """
    try:
        app()
    except (SakgError, OSError) as error:
        typer.echo(f"Erreur : {error}", err=True)
        raise SystemExit(1) from error


@app.callback()
def _main() -> None:
    """Rend la sortie tolérante aux consoles à encodage limité (cp1252 sous Windows).

    Sans cela, un caractère absent de l'encodage du terminal fait échouer la commande entière
    au lieu d'afficher le rapport.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


RootOption = Annotated[Path, typer.Option("--root", "-r", help="Racine du projet analysé.")]
DepthOption = Annotated[int, typer.Option("--depth", "-d", min=1, max=10, help="Profondeur de parcours.")]


@app.command()
def init(
    root: RootOption = Path("."),
    name: Annotated[str | None, typer.Option("--name", help="Nom du projet.")] = None,
) -> None:
    """Crée le dossier .architect/ et sa configuration."""
    existed = (Path(root) / ".architect" / "project.yaml").exists()
    architect = ArchitectureService.for_project(root).init_project(name)
    if existed:
        typer.echo(f"Configuration existante conservée : {architect}")
    else:
        typer.echo(f"Projet initialisé : {architect}")


@app.command()
def reverse(
    source: Annotated[list[str] | None, typer.Argument(help="Dossiers à analyser.")] = None,
    root: RootOption = Path("."),
) -> None:
    """Reconstruit le graphe depuis le code source."""
    service = ArchitectureService.for_project(root)
    snapshot = service.reverse(source)
    graph = service.graph
    typer.echo(f"Version {snapshot.version} : {len(graph)} nœuds, {len(graph.edges())} relations")
    for warning in service.warnings:
        typer.echo(f"  avertissement : {warning}", err=True)


@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Nom ou fragment d'identifiant ; facultatif avec --type.")] = "",
    root: RootOption = Path("."),
    node_type: Annotated[NodeType | None, typer.Option("--type", "-t", help="Type de nœud.")] = None,
    dependencies: Annotated[bool, typer.Option("--dependencies", help="Ce dont le nœud dépend.")] = False,
    dependents: Annotated[bool, typer.Option("--dependents", help="Ce qui dépend du nœud.")] = False,
    depth: DepthOption = 1,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="Nombre de résultats.")] = 20,
) -> None:
    """Interroge le graphe : recherche, dépendances, dépendants.

    Sans texte, ``--type`` liste tous les nœuds de ce type : « quelles routes expose ce
    projet ? », « quelles tables manipule-t-il ? ».
    """
    service = ArchitectureService.for_project(root)
    if not text.strip() and node_type is None:
        typer.echo("Préciser un texte à rechercher, ou un --type à lister.", err=True)
        raise typer.Exit(code=2)
    found = service.search(text, [node_type] if node_type else None, limit)
    if not found:
        wanted = f"« {text} »" if text.strip() else f"type {node_type.value if node_type else ''}"
        typer.echo(f"Aucun nœud ne correspond à {wanted}.")
        raise typer.Exit(code=1)

    if not dependencies and not dependents:
        for node in found:
            typer.echo(f"{node.type.value:10} {node.id}")
        return

    target = found[0]
    if len(found) > 1:
        others = ", ".join(node.id for node in found[1:4])
        typer.echo(f"{len(found)} correspondances ; analyse de la première. Autres : {others}", err=True)
    typer.echo(f"{target.id}")
    if dependencies:
        _echo_group("dépend de", service.dependencies(target.id, depth))
    if dependents:
        _echo_group("utilisé par", service.dependents(target.id, depth))


@app.command()
def impact(
    change: Annotated[str, typer.Argument(help="Changement envisagé, en langage naturel.")],
    root: RootOption = Path("."),
    node_id: Annotated[list[str] | None, typer.Option("--node", help="Point de départ imposé.")] = None,
) -> None:
    """Analyse l'impact d'un changement sur l'architecture."""
    report = ArchitectureService.for_project(root).impact(change, node_id)
    typer.echo(report.to_markdown())
    if report.is_empty():
        raise typer.Exit(code=1)


@app.command()
def uml(
    root: RootOption = Path("."),
    view: Annotated[DiagramView, typer.Option("--view", "-v", help="Vue générée.")] = DiagramView.CLASS,
    focus: Annotated[list[str] | None, typer.Option("--focus", help="Restreindre au voisinage de ces nœuds.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Fichier de sortie.")] = None,
) -> None:
    """Génère un diagramme Mermaid depuis le graphe."""
    service = ArchitectureService.for_project(root)
    try:
        path = service.write_diagram(view, focus, output)
    except UnsupportedViewError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    for warning in service.warnings:
        typer.echo(f"  avertissement : {warning}", err=True)
    typer.echo(f"Diagramme écrit : {path}")


@app.command()
def history(root: RootOption = Path(".")) -> None:
    """Liste les versions archivées du graphe."""
    snapshots = ArchitectureService.for_project(root).snapshots()
    if not snapshots:
        typer.echo("Aucune version enregistrée.")
        return
    for snapshot in snapshots:
        label = snapshot.label or "-"
        size = f"{_count(snapshot.node_count)} nœuds, {_count(snapshot.edge_count)} relations"
        typer.echo(f"v{snapshot.version:04d}  {snapshot.graph_hash[:12]}  {size}  {label}")


@app.command()
def validate(root: RootOption = Path(".")) -> None:
    """Vérifie les règles d'architecture déclarées dans .architect/rules/*.yaml."""
    report = ArchitectureService.for_project(root).validate()
    typer.echo(report.to_markdown())
    if not report.passed():
        raise typer.Exit(code=1)


@app.command()
def drift(root: RootOption = Path(".")) -> None:
    """Compare le graphe enregistré au code actuel, sans rien modifier."""
    report = ArchitectureService.for_project(root).detect_drift()
    typer.echo(report.to_markdown())
    if report.has_drifted():
        raise typer.Exit(code=1)


@app.command()
def diff(
    before: Annotated[int, typer.Argument(help="Version de départ.")],
    after: Annotated[int, typer.Argument(help="Version d'arrivée.")],
    root: RootOption = Path("."),
) -> None:
    """Compare deux versions du graphe : ce qui a changé dans l'architecture."""
    report = ArchitectureService.for_project(root).diff(before, after)
    typer.echo(report.to_markdown())


def _count(value: int | None) -> str:
    """Un compte inconnu (version ancienne) s'affiche « ? », pas « 0 »."""
    return f"{value:4}" if value is not None else "   ?"


def _echo_group(title: str, nodes: Sequence[Node]) -> None:
    typer.echo(f"  {title} ({len(nodes)}) :")
    for node in nodes:
        typer.echo(f"    {node.type.value:10} {node.id}")
    if not nodes:
        typer.echo("    (aucune relation de dépendance ; « sakg impact » suit aussi les fichiers)")


if __name__ == "__main__":  # pragma: no cover
    main()
