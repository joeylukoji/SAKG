# Diagrammes de classes — SAKG

Format : Mermaid (`classDiagram`), lisible par Claude Code, Cursor, GitHub et VS Code.
Le modèle est découpé par module pour rester lisible. Les noms correspondent aux
modules Python cibles (`src/sakg/<module>/`).

Légende : `<<interface>>` = classe abstraite / Protocol · `<<enumeration>>` = Enum ·
`*--` composition · `o--` agrégation · `..|>` réalisation · `<|--` héritage · `..>` dépendance

---

## 1. Cœur : domaine et Knowledge Graph (`domain/`, `graph/`)

`NodeResolver` est défini dans `domain/` pour que `OntologySchema` valide une relation sans
importer `graph/` ; `KnowledgeGraph` l'implémente structurellement (`Protocol`).

```mermaid
classDiagram
    direction LR

    class NodeType {
        <<enumeration>>
        PROJECT
        REQUIREMENT
        ACTOR
        USE_CASE
        BUSINESS_RULE
        CONSTRAINT
        SYSTEM
        SUBSYSTEM
        MODULE
        COMPONENT
        SERVICE
        LAYER
        PACKAGE
        CLASS
        INTERFACE
        FUNCTION
        METHOD
        FILE
        DIRECTORY
        ENDPOINT
        REQUEST
        RESPONSE
        EVENT
        MESSAGE
        DATABASE
        SCHEMA
        TABLE
        COLUMN
        INDEX
        CONTAINER
        IMAGE
        NETWORK
        VOLUME
        CLOUD_SERVICE
        DEPLOYMENT
        TEST
        TEST_SUITE
        FINDING
        ARCHITECTURE_VIOLATION
        TECHNOLOGY
        ADR
        ALTERNATIVE
        TRADE_OFF
    }

    class RelationType {
        <<enumeration>>
        REALIZED_BY
        CONSTRAINED_BY
        USED_BY
        IMPLEMENTED_BY
        CONTAINS
        DEPENDS_ON
        INHERITS
        IMPLEMENTS
        CALLS
        EXPOSES
        MAPS_TO
        READS_FROM
        WRITES_TO
        REFERENCES
        VERIFIES
        TESTS
        DEPLOYED_IN
        DECIDED_BY
        USES_TECHNOLOGY
        BELONGS_TO
    }

    class EvidenceType {
        <<enumeration>>
        OBSERVED
        INFERRED
        GENERATED
        USER_DEFINED
        RECOMMENDED
    }

    class Evidence {
        +file: str
        +line: int
        +end_line: int
        +snippet: str
    }

    class Provenance {
        +evidence_type: EvidenceType
        +confidence: float
        +detected_by: str
        +evidence: Optional~Evidence~
        +graph_version: int
        +commit_sha: str
        +created_at: datetime
        +is_fact() bool
    }

    class Node {
        +id: str
        +type: NodeType
        +name: str
        +properties: dict
        +provenance: Provenance
        +qualified_name() str
    }

    class Edge {
        +id: str
        +source_id: str
        +target_id: str
        +relation: RelationType
        +properties: dict
        +provenance: Provenance
    }

    class NodeResolver {
        <<interface>>
        +get_node(node_id: str) Optional~Node~
    }

    class OntologySchema {
        -allowed: frozenset
        +triples: frozenset
        +default() OntologySchema$
        +load(path: str) OntologySchema$
        +is_allowed(source: NodeType, relation: RelationType, target: NodeType) bool
        +validate_edge(edge: Edge, nodes: NodeResolver) None
    }

    class KnowledgeGraph {
        -nodes: dict
        -edges: dict
        +schema: OntologySchema
        +version: int
        +nodes() List~Node~
        +edges() List~Edge~
        +add_node(node: Node) Node
        +add_edge(edge: Edge) Edge
        +remove_node(node_id: str) None
        +remove_edge(edge_id: str) Edge
        +get_node(node_id: str) Optional~Node~
        +get_edge(edge_id: str) Optional~Edge~
        +nodes_of_type(type: NodeType) List~Node~
        +out_edges(node_id: str) List~Edge~
        +in_edges(node_id: str) List~Edge~
        +subgraph(node_ids: Iterable) KnowledgeGraph
        +to_networkx() MultiDiGraph
    }

    class GraphSnapshot {
        +version: int
        +graph_hash: str
        +commit_sha: str
        +label: str
        +created_at: datetime
        +graph: KnowledgeGraph
        +of(graph: KnowledgeGraph, commit_sha: str, label: str) GraphSnapshot$
        +meta() SnapshotMeta
    }

    class SnapshotMeta {
        +version: int
        +graph_hash: str
        +commit_sha: str
        +label: str
        +created_at: datetime
        +node_count: int
        +edge_count: int
    }

    class GraphQueryEngine {
        -graph: KnowledgeGraph
        +nodes() List~Node~
        +get_node(node_id: str) Optional~Node~
        +inventory(types: List~NodeType~, limit: int) List~Node~
        +find(text: str, types: List~NodeType~, limit: int) List~Node~
        +dependencies(node_id: str, depth: int) List~Node~
        +dependents(node_id: str, depth: int) List~Node~
        +path(source_id: str, target_id: str) List~Edge~
        +traverse(start: List~str~, strategy: TraversalStrategy) TraversalResult
    }

    class Direction {
        <<enumeration>>
        OUT
        IN
        BOTH
    }

    class TraversalStrategy {
        <<interface>>
        +traverse(graph: KnowledgeGraph, start: List~str~) TraversalResult
    }
    class BoundedBfsStrategy {
        +max_depth: int
        +relations: frozenset
        +direction: Direction
    }
    class WeightedPropagationStrategy {
        <<phase 3>>
        +relation_weights: dict
        +threshold: float
    }
    class TraversalResult {
        +visited: dict
        +scores: dict
        +edges: List~Edge~
        +at_depth(depth: int) List~str~
    }

    class GraphRepository {
        <<interface>>
        +save(graph: KnowledgeGraph, label: str, commit_sha: str) GraphSnapshot
        +load() KnowledgeGraph
        +list_snapshots() List~SnapshotMeta~
        +load_snapshot(version: int) GraphSnapshot
    }
    class JsonGraphRepository {
        +root: Path
        +architect_dir: Path
        +graph_dir: Path
        +versions_dir: Path
    }
    class PostgresGraphRepository {
        +dsn: str
    }

    Provenance --> EvidenceType
    Provenance o-- Evidence
    Node --> NodeType
    Edge --> RelationType
    Node *-- Provenance
    Edge *-- Provenance
    KnowledgeGraph "1" *-- "*" Node
    KnowledgeGraph "1" *-- "*" Edge
    KnowledgeGraph --> OntologySchema : valide avec
    NodeResolver <|.. KnowledgeGraph
    OntologySchema ..> NodeResolver
    GraphSnapshot *-- KnowledgeGraph
    GraphQueryEngine --> KnowledgeGraph
    GraphQueryEngine ..> TraversalStrategy
    TraversalStrategy <|.. BoundedBfsStrategy
    TraversalStrategy <|.. WeightedPropagationStrategy
    BoundedBfsStrategy --> Direction
    TraversalStrategy ..> TraversalResult
    GraphRepository <|.. JsonGraphRepository
    GraphRepository <|.. PostgresGraphRepository
    GraphRepository ..> GraphSnapshot
```

---

## 2. Reverse engineering (`reverse/`)

Le reverse parse Python via `PythonAstParser` (`ast`, [ADR-003](../adr/ADR-003-parser-python.md))
et TypeScript via `TypeScriptParser` (Tree-sitter). Un langage supplémentaire s'ajoute par un
`LanguageParser` enregistré et, si besoin, un `ImportResolver`. `GoParser` reste prévu.

```mermaid
classDiagram
    direction LR

    class ProjectScanner {
        +ignore_patterns: List~str~
        +scan(root: Path, include: List~str~, commit_sha: str) ProjectContext
    }

    class ProjectContext {
        +root: Path
        +files: List~SourceFile~
        +languages: set
        +frameworks: set
        +commit_sha: str
        +files_of_language(language: str) List~SourceFile~
    }

    class SourceFile {
        +path: Path
        +relative_path: str
        +language: str
        +content_hash: str
    }

    class ParsedModule {
        +file: SourceFile
        +module_name: str
        +symbols: List~Symbol~
        +imports: List~ImportRef~
        +calls: List~CallRef~
        +decorators: List~DecoratorRef~
        +call_sites: List~CallSite~
        +attributes: List~AttributeRef~
        +symbols_of_kind(kind: str) List~Symbol~
        +attributes_of(owner: str) List~AttributeRef~
        +imports_module(prefix: str) bool
    }

    class AttributeRef {
        +owner: str
        +name: str
        +value: str
        +callee: str
        +arguments: List~str~
        +keywords: dict
        +booleans: dict
        +nested: dict
    }

    class Symbol {
        +kind: str
        +name: str
        +qualified_name: str
        +line: int
        +end_line: int
        +bases: List~str~
    }

    class LanguageParser {
        <<interface>>
        +language: str
        +supports(file: SourceFile) bool
        +parse(file: SourceFile) ParsedModule
    }

    class PythonAstParser {
        +language: str
        +supports(file: SourceFile) bool
        +parse(file: SourceFile) ParsedModule
    }

    class TreeSitterParser {
        <<abstract>>
        +language: str
        +grammar: Language
        +supports(file: SourceFile) bool
        +parse(file: SourceFile) ParsedModule
        +grammar_for(file: SourceFile) Language
        +collect(file, source, tree) ParsedModule*
    }
    class TypeScriptParser
    class GoParser {
        <<phase 7>>
    }

    class ImportResolver {
        <<interface>>
        +resolve(import_ref, module_name, is_package) str
    }
    class PythonImportResolver
    class EcmaImportResolver

    class ModuleVisitor {
        +visit_ClassDef(node) None
        +visit_FunctionDef(node) None
        +visit_Call(node) None
    }

    class ParserRegistry {
        -parsers: List~LanguageParser~
        -cache: dict
        +languages: set
        +register(parser: LanguageParser) None
        +for_file(file: SourceFile) Optional~LanguageParser~
        +parse(file: SourceFile) Optional~ParsedModule~
    }

    class Extractor {
        <<interface>>
        +name: str
        +order: int
        +extract(context: ProjectContext, registry: ParserRegistry) ExtractionResult
    }
    class CodeStructureExtractor
    class ApiExtractor {
        -adapters: List~FrameworkAdapter~
    }
    class DatabaseExtractor {
        +name: str
        +order: int
        +extract(context, registry) ExtractionResult
    }
    class InfrastructureExtractor {
        +name: str
        +order: int
        +extract(context, registry) ExtractionResult
    }
    class TableSpec {
        +name: str
        +model: str
        +module: str
        +relative_path: str
        +columns: List~AttributeRef~
    }
    class TestExtractor {
        <<phase 4>>
    }

    class FrameworkAdapter {
        <<interface>>
        +framework: str
        +detect(module: ParsedModule) bool
        +routes(module: ParsedModule, context: RouterContext) RouteExtraction
        +routers(module: ParsedModule) dict
        +inclusions(module: ParsedModule) List~RouterInclusion~
    }

    class RouterContext {
        +prefixes: Mapping
        +known_routers: frozenset
    }

    class RouteExtraction {
        +endpoints: List~EndpointSpec~
        +warnings: List~str~
    }

    class RouterInclusion {
        +router: str
        +parent: str
        +prefix: str
        +line: int
    }
    class EndpointSpec {
        +method: str
        +path: str
        +handler: str
        +line: int
        +router: str
        +framework: str
        +name: str
    }
    class FastApiAdapter
    class DjangoAdapter {
        <<phase 7>>
    }
    class ExpressAdapter {
        <<phase 7>>
    }

    class ExtractionResult {
        +nodes: List~Node~
        +edges: List~Edge~
        +warnings: List~str~
    }

    class GraphBuilder {
        +warnings: List~str~
        +add(result: ExtractionResult) GraphBuilder
        +resolve_references() GraphBuilder
        +merge_into(existing: KnowledgeGraph) KnowledgeGraph
        +build() KnowledgeGraph
    }

    class ReverseEngineeringPipeline {
        -registry: ParserRegistry
        +extractors: List~Extractor~
        +default() ReverseEngineeringPipeline$
        +add_extractor(e: Extractor) None
        +run(context: ProjectContext) ReverseResult
        +run_on(root: Path, include: List~str~) ReverseResult
    }

    class ReverseResult {
        +graph: KnowledgeGraph
        +warnings: List~str~
    }

    ProjectScanner ..> ProjectContext
    ProjectContext *-- SourceFile
    LanguageParser <|.. PythonAstParser
    LanguageParser <|.. TreeSitterParser
    TreeSitterParser <|-- TypeScriptParser
    TreeSitterParser <|-- GoParser
    ImportResolver <|.. PythonImportResolver
    ImportResolver <|.. EcmaImportResolver
    PythonAstParser ..> ModuleVisitor
    LanguageParser ..> ParsedModule
    ParsedModule *-- Symbol
    ParserRegistry o-- LanguageParser
    Extractor <|.. CodeStructureExtractor
    Extractor <|.. ApiExtractor
    Extractor <|.. DatabaseExtractor
    Extractor <|.. InfrastructureExtractor
    DatabaseExtractor ..> TableSpec
    ParsedModule *-- AttributeRef
    Extractor <|.. TestExtractor
    ApiExtractor o-- FrameworkAdapter
    FrameworkAdapter ..> RouteExtraction
    FrameworkAdapter ..> RouterContext
    FrameworkAdapter ..> RouterInclusion
    RouteExtraction *-- EndpointSpec
    FrameworkAdapter <|.. FastApiAdapter
    FrameworkAdapter <|.. DjangoAdapter
    FrameworkAdapter <|.. ExpressAdapter
    Extractor ..> ExtractionResult
    Extractor ..> ParserRegistry
    ReverseEngineeringPipeline o-- Extractor
    ReverseEngineeringPipeline --> ParserRegistry
    ReverseEngineeringPipeline --> GraphBuilder
    ReverseEngineeringPipeline ..> ReverseResult
    GraphBuilder ..> ExtractionResult
```

---

## 3. Analyse, validation et évolution (`analysis/`, `validation/`)

```mermaid
classDiagram
    direction LR

    class ChangeRequest {
        +description: str
        +target_node_ids: List~str~
        +kind: str
    }

    class ImpactAnalyzer {
        -query: GraphQueryEngine
        -strategy: TraversalStrategy
        +locate(change: ChangeRequest) List~Node~
        +analyze(change: ChangeRequest, seed_limit: int) ImpactReport
    }

    class ImpactReport {
        +change: ChangeRequest
        +seeds: List~str~
        +affected: dict
        +scores: dict
        +warnings: List~str~
        +by_type(type: NodeType) List~Node~
        +all_nodes() List~Node~
        +is_empty() bool
        +to_markdown() str
    }

    class GraphDiffer {
        +diff(before: GraphSnapshot, after: GraphSnapshot) ArchitectureDiff
        +diff_graphs(before: KnowledgeGraph, after: KnowledgeGraph) ArchitectureDiff
    }

    class ArchitectureDiff {
        +before: int
        +after: int
        +added_nodes: List~Node~
        +removed_nodes: List~Node~
        +modified_nodes: List~ChangedNode~
        +added_edges: List~Edge~
        +removed_edges: List~Edge~
        +modified_edges: List~ChangedEdge~
        +is_empty() bool
        +counts() dict
        +by_type() dict
        +to_markdown() str
    }

    class ChangedNode {
        +before: Node
        +after: Node
        +changed_fields() List~str~
        +describe() List~str~
    }

    class ChangedEdge {
        +before: Edge
        +after: Edge
        +changed_fields() List~str~
        +describe() List~str~
    }

    class DriftDetector {
        +detect(intended: KnowledgeGraph, actual: KnowledgeGraph) DriftReport
    }

    class DriftReport {
        +drift_score: float
        +missing_in_code: List~Edge~
        +undocumented_in_code: List~Edge~
    }

    class ReconstructionEvaluator {
        +evaluate(extracted: KnowledgeGraph, ground_truth: KnowledgeGraph) EvaluationReport
    }

    class EvaluationReport {
        +node_precision: float
        +node_recall: float
        +edge_precision: float
        +edge_recall: float
        +drift_score: float
        +calibration: dict
    }

    class MetricsCalculator {
        +coupling(node_id: str) dict
        +instability(node_id: str) float
        +cohesion(node_id: str) float
        +cycles() List~List~
    }

    class ArchitectureRule {
        <<interface>>
        +id: str
        +severity: Severity
        +check(graph: KnowledgeGraph) List~Finding~
    }
    class LayerDependencyRule {
        +layers: List~str~
    }
    class NoCycleRule {
        +relation: RelationType
    }
    class TraceabilityRule
    class OrphanComponentRule

    class RuleLoader {
        +load(dir: Path) List~ArchitectureRule~
    }

    class ArchitectureValidator {
        -rules: List~ArchitectureRule~
        +validate(graph: KnowledgeGraph) ValidationReport
    }

    class ValidationReport {
        +findings: List~Finding~
        +passed() bool
    }

    class Finding {
        +rule_id: str
        +severity: Severity
        +message: str
        +node_ids: List~str~
        +edge_ids: List~str~
    }

    class Severity {
        <<enumeration>>
        INFO
        WARNING
        ERROR
    }

    class ArchitectureDecisionRecord {
        +id: str
        +title: str
        +status: str
        +context: str
        +decision: str
        +alternatives: List~str~
        +consequences: str
        +related_node_ids: List~str~
        +to_node() Node
    }

    ImpactAnalyzer ..> ChangeRequest
    ImpactAnalyzer ..> ImpactReport
    GraphDiffer ..> ArchitectureDiff
    ArchitectureDiff *-- ChangedNode
    ArchitectureDiff *-- ChangedEdge
    DriftDetector ..> DriftReport
    ReconstructionEvaluator ..> EvaluationReport
    ReconstructionEvaluator ..> DriftDetector
    ArchitectureRule <|.. LayerDependencyRule
    ArchitectureRule <|.. NoCycleRule
    ArchitectureRule <|.. TraceabilityRule
    ArchitectureRule <|.. OrphanComponentRule
    RuleLoader ..> ArchitectureRule
    ArchitectureValidator o-- ArchitectureRule
    ArchitectureValidator ..> ValidationReport
    ValidationReport *-- Finding
    Finding --> Severity
    NoCycleRule ..> MetricsCalculator
```

---

## 4. Génération et IA (`generation/`, `ai/`)

```mermaid
classDiagram
    direction LR

    class DiagramView {
        <<enumeration>>
        CLASS
        USE_CASE
        SEQUENCE
        COMPONENT
        DEPLOYMENT
        ERD
    }

    class ViewProjection {
        +view: DiagramView
        +node_types: frozenset
        +relations: frozenset
        +for_view(view: DiagramView) ViewProjection$
        +project(graph: KnowledgeGraph, focus: List~str~) KnowledgeGraph
    }

    class DiagramGenerator {
        <<interface>>
        +format: str
        +generate(graph: KnowledgeGraph, view: DiagramView, focus: List~str~) Diagram
    }
    class MermaidGenerator
    class PlantUmlGenerator {
        <<phase 2>>
    }

    class Diagram {
        +view: DiagramView
        +format: str
        +source: str
        +graph_version: int
        +to_markdown() str
    }

    class ProjectConfig {
        +name: str
        +languages: List~str~
        +source_roots: List~str~
        +ignore: List~str~
        +rules: List~str~
        +default_for(root: Path) ProjectConfig$
        +load(root: Path) ProjectConfig$
        +save(root: Path) Path
    }

    class DocumentationGenerator {
        +technical_spec(graph: KnowledgeGraph) str
        +adr_index(adrs: List~ArchitectureDecisionRecord~) str
    }

    class LLMProvider {
        <<interface>>
        +name: str
        +complete(messages: List, tools: List) LLMResponse
    }
    class AnthropicProvider
    class OpenAIProvider
    class LocalModelProvider

    class LLMProviderFactory {
        +create(config: AIConfig) LLMProvider$
    }

    class GraphToolkit {
        -query: GraphQueryEngine
        -impact: ImpactAnalyzer
        +tool_specs() List
        +invoke(name: str, args: dict) dict
    }

    class AIArchitect {
        -llm: LLMProvider
        -tools: GraphToolkit
        -validator: ProposalValidator
        +design_from_idea(idea: str) ArchitectureProposal
        +explain(question: str) GroundedAnswer
        +propose_change(change: ChangeRequest) ArchitectureProposal
    }

    class ProposalValidator {
        -schema: OntologySchema
        +validate(raw: dict) ArchitectureProposal
    }

    class ArchitectureProposal {
        +id: str
        +title: str
        +status: ProposalStatus
        +nodes_to_add: List~Node~
        +edges_to_add: List~Edge~
        +node_ids_to_remove: List~str~
        +impact: Optional~ImpactReport~
        +rationale: str
    }

    class ProposalStatus {
        <<enumeration>>
        PROPOSED
        ACCEPTED
        REJECTED
        APPLIED
    }

    class GroundedAnswer {
        +text: str
        +cited_node_ids: List~str~
    }

    DiagramGenerator <|.. MermaidGenerator
    DiagramGenerator <|.. PlantUmlGenerator
    DiagramGenerator ..> ViewProjection
    DiagramGenerator ..> Diagram
    ViewProjection --> DiagramView
    LLMProvider <|.. AnthropicProvider
    LLMProvider <|.. OpenAIProvider
    LLMProvider <|.. LocalModelProvider
    LLMProviderFactory ..> LLMProvider
    AIArchitect --> LLMProvider
    AIArchitect --> GraphToolkit
    AIArchitect --> ProposalValidator
    AIArchitect ..> ArchitectureProposal
    AIArchitect ..> GroundedAnswer
    ProposalValidator ..> ArchitectureProposal
    ArchitectureProposal --> ProposalStatus
```

---

## 5. Application et interfaces (`application/`, `interfaces/`)

```mermaid
classDiagram
    direction TB

    class ArchitectureService {
        <<facade>>
        -repo: GraphRepository
        -pipeline: ReverseEngineeringPipeline
        -query: GraphQueryEngine
        -impact: ImpactAnalyzer
        -validator: ArchitectureValidator
        -drift: DriftDetector
        -differ: GraphDiffer
        -diagrams: DiagramGenerator
        -docs: DocumentationGenerator
        -architect: AIArchitect
        -evaluator: ReconstructionEvaluator
        -commands: CommandBus
        +root: Path
        +graph: KnowledgeGraph
        +warnings: List~str~
        +for_project(root: Path) ArchitectureService$
        +init_project(name: str) Path
        +reverse(source_roots: List~str~) GraphSnapshot
        +write_diagram(view: DiagramView, focus: List~str~, path: Path) Path
        +snapshots() List~SnapshotMeta~
        +design(idea: str) ArchitectureProposal
        +search(text: str) List~Node~
        +dependencies(node_id: str) List~Node~
        +dependents(node_id: str) List~Node~
        +impact(change: str) ImpactReport
        +propose(change: str) ArchitectureProposal
        +accept(proposal_id: str) GraphSnapshot
        +reject(proposal_id: str) None
        +validate() ValidationReport
        +detect_drift() DriftReport
        +diff(v1: int, v2: int) ArchitectureDiff
        +diagram(view: DiagramView) Diagram
        +documentation() str
        +record_adr(adr: ArchitectureDecisionRecord) None
        +explain(question: str) GroundedAnswer
        +add_requirement(requirement: Node) GraphSnapshot
        +evaluate(ground_truth: Path) EvaluationReport
    }

    class GraphCommand {
        <<abstract>>
        +label: str
        +execute(graph: KnowledgeGraph) None
        +undo(graph: KnowledgeGraph) None
    }
    class AddNodeCommand
    class AddEdgeCommand
    class ReplaceObservedLayerCommand
    class ApplyProposalCommand

    class CommandBus {
        -repository: GraphRepository
        -events: EventBus
        +graph: KnowledgeGraph
        +commit_sha: str
        +history: List~GraphCommand~
        +execute(cmd: GraphCommand) GraphSnapshot
        +undo_last() GraphSnapshot
    }

    class EventBus {
        -subscribers: dict
        +subscribe(event_type: type, handler: Callable) None
        +publish(event: DomainEvent) None
    }

    class DomainEvent {
        <<abstract>>
        +occurred_at: datetime
    }
    class GraphChanged {
        +version: int
        +command: str
    }
    class ProposalCreated {
        +proposal_id: str
    }
    class ValidationCompleted {
        +passed: bool
    }

    class CliApp {
        +init()
        +reverse()
        +query()
        +impact()
        +uml()
        +history()
        +design() [S10]
        +change() [S10]
        +proposal() [S10]
        +validate() [S9]
        +drift() [S9]
        +diff()
        +docs() [S8]
        +adr() [S8]
        +ask() [S10]
        +requirement() [S9]
        +eval() [S12]
        +mcp() [S12]
    }

    class McpServer {
        +get_architecture()
        +search_architecture()
        +get_node()
        +get_dependencies()
        +get_dependents()
        +calculate_impact()
        +validate_architecture()
        +generate_diagram()
        +propose_change()
    }

    class RestApi {
        +router: APIRouter
    }

    GraphCommand <|.. AddNodeCommand
    GraphCommand <|.. AddEdgeCommand
    GraphCommand <|.. ReplaceObservedLayerCommand
    GraphCommand <|.. ApplyProposalCommand
    CommandBus o-- GraphCommand
    CommandBus --> EventBus : publie
    DomainEvent <|-- GraphChanged
    DomainEvent <|-- ProposalCreated
    DomainEvent <|-- ValidationCompleted
    ArchitectureService --> CommandBus
    ArchitectureService --> EventBus
    CliApp --> ArchitectureService
    McpServer --> ArchitectureService
    RestApi --> ArchitectureService
```
