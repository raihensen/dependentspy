import os
from pathlib import Path
from typing import Literal
import warnings

import networkx as nx

from utils import PathLike, find_dead_ends
from visualization import create_graphviz
from module import Module, ProjectModule, complete_module_tree


__tool_name__ = "dependentspy"
__tool_url__ = "https://github.com/raihensen/dependentspy"
__version__ = "0.1.0"


def dependentspy(
    project_root: PathLike,
    *,
    name: str = "dependentspy_graph",
    save_dot: bool = True,
    render: bool | Literal["if_changed"] = "if_changed",
    output_to_project: bool = False,
    prune: bool = False,
    render_imports: bool = True,
    show_3rdparty: bool = True,
    show_builtin: bool = False,
    summarize_external: bool = True,
    use_clusters: bool = True,
    use_nested_clusters: bool = True,
    min_cluster_size: int = 2,
    ignore: list[str] = [],
    hide: list[str] = [],
    comment: str | None = None,
    **kwargs,
):
    """Main `dependentspy` function, walking the given project directory and creating a dependency graph using graphviz.

    Arguments:
    - project_root: The path of the project to analyze.

    Keyword arguments:
    - name: A name that will be given to the output files and the graph, defaults to `"dependentspy_graph"`
    - save_dot: Whether to save the dot string to a file. Defaults to `True`.
    - render: Whether to save the rendered graph. If "if_changed", only saves if the dot string has changed, should only be used when save_dot is True. defaults to `"if_changed"`.
    - output_to_project: Whether to save the output to the project directory. If False, saves to the current working directory. defaults to `False`.
    - prune: Whether to remove modules that are either never imported, or have no imports themselves. Can increase readability. defaults to `False`.
    - render_imports: Whether to render imports as edges. If False, just shows the project structure as nodes without edges. defaults to `True`.
    - show_3rdparty: Whether to show third-party modules. Defaults to `True`.
    - show_builtin: Whether to show stdlib / built-in modules. Defaults to `False`.
    - summarize_external: Whether to summarize external modules and their submodules when both are imported. Defaults to `True`.
    - use_clusters: Whether to group submodules of the same module and render them as a bordered subgraph. Defaults to `True`.
    - use_nested_clusters: Whether to use nested clusters for grouping nested submodules. Defaults to `True`.
    - min_cluster_size: Minimum number of submodules in the same module to make it a cluster. Defaults to `2`.
    - ignore: A list of path patterns (similar to .gitignore) for python files to ignore.
    - hide: A list of modules to hide in the graph
    - comment: Optional comment added to the first line of the source
    """

    # Process parameters
    use_nested_clusters = use_clusters and use_nested_clusters
    comment = ((comment + " -- ") if comment else "") + f"Created using {__tool_name__} {__version__} ({__tool_url__})"
    print(comment)
    # Get all python files

    cwd = os.getcwd()
    os.chdir(project_root)
    paths = Path(".").rglob("*.py")
    paths = [f for f in paths if not any(f.match(p) for p in ignore)]
    if not paths:
        raise ValueError(
            "The given project directory does not exist or contains no .py files."
        )

    # Init module objects
    project_modules = [ProjectModule.from_file(p) for p in paths]
    project_routes = {m.route for m in project_modules}

    # Complete tree structure
    project_modules: list[ProjectModule] = complete_module_tree(
        project_modules, cls=ProjectModule
    )  # type: ignore

    # Collect imported module routes and init objects
    import_routes = sorted(
        set(sum([m.import_routes or [] for m in project_modules], []))
    )
    external_modules = [Module(r) for r in import_routes if r not in project_routes]
    external_modules = complete_module_tree(external_modules, cls=Module)

    modules = project_modules + external_modules

    # Add import relations
    route_map = {module.route: module for module in modules}
    for module in project_modules:
        module.imports = [route_map[route] for route in module.import_routes or []]

    # print("\n".join([str(m) for m in sorted(project_modules, key=str)]))
    for t in ["project", "builtin", "3rdparty"]:
        tmodules = [m for m in modules if m.type == t]
        print(f"Found {len(tmodules)} {t} modules")

    hide = []

    # Init networkx import graph (just project modules)
    gr = nx.DiGraph()
    gr.add_nodes_from([m.route for m in project_modules if m.is_leaf()])
    for module in project_modules:
        for im in module.imports:
            if im.is_project:
                assert im.is_leaf()
                gr.add_edge(module.route, im.route)
    
    if prune:
        # Hide modules that have no imports / are not imported
        in_degrees = {module.route: gr.in_degree(module.route) for module in modules}
        out_degrees = {module.route: gr.out_degree(module.route) for module in modules}

        never_imported = [
            m.route for m in project_modules if m.is_leaf() and in_degrees[m.route] == 0
        ]
        no_imports = [
            m.route
            for m in project_modules
            if m.is_leaf() and out_degrees[m.route] == 0
        ]
        dead_ends = [r for r in find_dead_ends(gr)]

        print("Never imported:", len(never_imported))
        print("No imports:", len(no_imports))
        print("dead ends:", len(dead_ends))

        hide += never_imported + no_imports

    # Determine what modules to render as clusters/subgraphs
    cluster_names = {}
    
    cluster_map: dict[str, str | None] = {m.route: None for m in modules}  # Maps module routes to the module route representing the containing cluster, or None.
    
    if use_clusters:
        for module in project_modules if summarize_external else modules:
            if module.is_leaf():
                continue
            if not use_nested_clusters and not module.is_root():
                continue
            if len(module.children) < min_cluster_size:
                continue
            if module.route in hide:
                continue
            cluster_names[module.route] = f"cluster[{module.route}]"

        # Link each module to its containing cluster
        for module in modules:
            if not module.is_project and summarize_external:
                continue
            # Walk up the tree until module has a subgraph
            for m in module.path_to_root:
                if m.route in cluster_names:
                    cluster_map[module.route] = m.route
                    break

    # Determine what modules to render as nodes
    visible_modules = []
    for module in modules:
        if not show_builtin and module.is_builtin:
            continue
        if not show_3rdparty and module.is_3rdparty:
            continue
        if module.route in hide:
            continue

        # Merge external module paths to root module name
        if not module.is_project and summarize_external and not module.is_root():
            continue

        # When using clusters, omit module if it has its own cluster
        if module.route in cluster_names:
            continue
        visible_modules.append(module)

    G = create_graphviz(
        name=name,
        visible_modules=visible_modules,
        route_map=route_map,
        cluster_names=cluster_names,
        cluster_map=cluster_map,
        render_imports=render_imports,
        summarize_external=summarize_external,
        use_clusters=use_clusters,
        use_nested_clusters=use_nested_clusters,
        comment=comment,
        **kwargs,
    )

    if not output_to_project:
        os.chdir(cwd)

    if render == "if_changed":
        if not save_dot:
            warnings.warn(
                "save_dot=False while render='if_changed'. This seems accidental."
            )
        render = True
        if os.path.exists(G.filepath):
            prev = open(G.filepath).read()
            dot = G.source
            if prev == dot:
                print("dot string has not changed, skip rendering.")
                render = False
    if save_dot:
        G.save()
    if render:
        G.render()

    return G


if __name__ == "__main__":
    G = dependentspy(
        ".",
        name="dependentspy-test",
        render_imports=True,
        prune=False,
        use_clusters=True,
        use_nested_clusters=True,
        min_cluster_size=1,
        show_3rdparty=True,
        show_builtin=False,
        summarize_external=True,
        ignore=["drafts*"],
        hide=["main", "index"],
        output_to_project=True,
        save_dot=True,
        render="if_changed",
        format="png",
        comment="Test dependency graph of the dependentspy module",
    )
G.view()
