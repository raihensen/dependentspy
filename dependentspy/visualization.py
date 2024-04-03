import graphviz as gv
import uuid

from module import Module, ProjectModule


MODULE_NODE_ATTR_COMMON = dict(
    shape="rect",
    style="filled",
)

MODULE_NODE_ATTR = {
    "project": dict(
        **MODULE_NODE_ATTR_COMMON,
        fillcolor="#e0e0e0",
    ),
    "builtin": dict(
        **MODULE_NODE_ATTR_COMMON,
        fillcolor="lightblue",
    ),
    "3rdparty": dict(
        **MODULE_NODE_ATTR_COMMON,
        fillcolor="black",
        fontcolor="white",
    ),
}

CLUSTER_NODE_ATTR = lambda module: dict(
    style="filled",
    fillcolor="#f0f0f0",
)

SUBMODULE_EDGE_ATTR = dict(
    color="black",
    penwidth="1",
    arrowtail="ediamond",
    dir="back",
)

IMPORT_EDGE_ATTR = dict(
    color="#404040",
    penwidth="1",
)


def create_graphviz(
    name: str,
    visible_modules: list[Module],
    route_map: dict[str, Module],
    cluster_names: dict[str, str],
    cluster_map: dict[str, str | None],
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
        H.attr(label=module.route, **CLUSTER_NODE_ATTR(module))
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
            **MODULE_NODE_ATTR[module.type],
        )
        if (
            module.parent
            and not use_nested_clusters
            and module.parent in visible_modules
            and module.parent not in subgraphs
        ):
            u = module.parent.route
            v = (
                module.route
                if not module.route in subgraphs
                else module.find_leaf().route
            )
            extra = {}
            if module.route in subgraphs:
                extra["lhead"] = subgraphs[module.route].name
            H.edge(u, v, type="submodule", **SUBMODULE_EDGE_ATTR, **extra)

    # Add subgraphs to parent graphs
    for route, H in sorted(subgraphs.items(), key=lambda c: c[0], reverse=True):
        module = route_map[route]
        H0 = get_containing_graph(module.parent) if module.parent else G
        H0.subgraph(H)
        # print(f"{H0.name} -> {H.name}")

    # print(route_map["api"], route_map["api.model"].parent)

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
                    module.route, im.route, type="import", **IMPORT_EDGE_ATTR, **extra
                )

    return G
