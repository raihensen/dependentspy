import os
from pathlib import Path
from typing import Literal, Sequence
import warnings

import networkx as nx
import graphviz as gv

from module import Module, ProjectModule


def module_type_node_attrs(module_type: str):
    if module_type == "stdlib" or module_type == "builtin":
        return {"fillcolor": "lightblue", "style": "filled"}
    if module_type == "3rdparty":
        return {"fillcolor": "black", "fontcolor": "white", "style": "filled"}
    if module_type == "project":
        return {"fillcolor": "#e0e0e0", "style": "filled"}
    raise ValueError


def complete_module_tree(modules: Sequence[Module], cls: type[Module]) -> list[Module]:
    route_map = {m.route: m for m in modules}

    # Complete tree structure
    inner_modules = []
    for m in modules:
        child = m
        for i in reversed(range(1, len(m.path))):
            subpath = m.path[:i]
            subroute = ".".join(subpath)
            existing = subroute in route_map
            if existing:
                parent = route_map[subroute]
            else:
                parent = cls(path=subpath)
                route_map[subroute] = parent
            parent.children.append(child)
            child.parent = parent
            if existing:
                break

            inner_modules.append(parent)
            child = parent

    return list(modules) + inner_modules


def find_dead_ends(gr: nx.DiGraph):
    out_degrees = {v: gr.out_degree(v) for v in gr.nodes}
    no_out = {v for v, d in out_degrees.items() if d == 0}
    # in_degrees = {v: gr.in_degree(v) for v in gr.nodes}
    # no_in = {v for v, d in in_degrees.items() if d == 0}
    C = {*no_out}
    prev = {*C}
    while prev:
        new = set()
        for u in prev:
            for v in gr.predecessors(u):
                if v in C:
                    continue
                if set(gr.successors(v)) <= C:
                    new.add(v)
                    C.add(v)
        prev = new
    return C


def dependentspy(
    project_root,
    *,
    name: str = "dependency_graph",
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
    **kwargs,
):
    """Build a graph representing internal dependencies of the project."""
    use_nested_clusters = use_clusters and use_nested_clusters

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
    # sconn = list(nx.strongly_connected_components(gr))
    # print(f"{len(sconn)} strongly connected components")
    # wconn = list(nx.weakly_connected_components(gr))
    # print(f"{len(wconn)} weakly connected components")
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

    # Determine what modules are displayed as clusters/subgraphs
    cluster_names = {}
    cluster_map = {}
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
            cluster_map[module.route] = None
            if not module.is_project and summarize_external:
                continue
            # Walk up the tree until module has a subgraph
            m = module
            while m:
                if m.route in cluster_names:
                    cluster_map[module.route] = m.route
                    break
                m = m.parent

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


def create_graphviz(
    name: str,
    visible_modules: list[Module],
    route_map: dict[str, Module],
    cluster_names: dict[str, str],
    cluster_map: dict[str, str],
    render_imports: bool,
    summarize_external: bool,
    use_clusters: bool,
    use_nested_clusters: bool,
    **kwargs,
):
    # Init graphviz graph
    G = gv.Digraph(name=name, strict=True, **kwargs)

    # Init subgraphs/clusters
    subgraphs = {}
    for route, cluster_name in cluster_names.items():
        module = route_map[route]
        H = gv.Digraph(name=cluster_name)
        H.attr(label=module.route)
        subgraphs[module.route] = H

    def get_containing_graph(module: Module):
        cluster_route = cluster_map.get(module.route, None)
        return subgraphs[cluster_route] if cluster_route else G

    # Add node(s) and parent-child edges
    for module in visible_modules:
        H = get_containing_graph(module)
        H.node(
            module.route,
            type=module.type,
            label=module.name,
            shape="rect",
            **module_type_node_attrs(module.type),
        )
        if (
            module.parent
            and not use_nested_clusters
            and module.parent in visible_modules
        ):
            H.edge(
                module.parent.route,
                module.route,
                type="parent",
                color="black",
                penwidth="1",
                arrowtail="ediamond",
                dir="back",
            )

    # Add subgraphs to parent graphs
    for route, H in sorted(subgraphs.items(), key=lambda c: c[0], reverse=True):
        module = route_map[route]
        H0 = get_containing_graph(module.parent) if module.parent else G
        H0.subgraph(H)

    # Add import edges
    if render_imports:
        for module in visible_modules:
            if not isinstance(module, ProjectModule):
                continue
            for im in module.imports:
                # Fallback to root module if configured that way
                if not im.is_project and summarize_external:
                    im = im.get_root()
                # Only add edge if other module is visible
                if im not in visible_modules:
                    continue
                extra = {}
                if use_clusters and im.route in subgraphs:
                    extra["lhead"] = subgraphs[im.route].name
                    # pass
                G.edge(
                    module.route,
                    im.route,
                    type="import",
                    color="red",
                    penwidth="0.5",
                    **extra,
                )

    return G


if __name__ == "__main__":
    G = dependentspy(
        "../../ocean/backend",
        render_imports=True,
        prune=True,
        use_clusters=True,
        use_nested_clusters=True,
        min_cluster_size=1,
        show_3rdparty=False,
        show_builtin=False,
        summarize_external=True,
        ignore=["drafts*"],
        hide=["main", "index"],
        output_to_project=True,
        save_dot=True,
        render="if_changed",
        format="png",
    )
G.view()
