from __future__ import annotations

import ast
from functools import cached_property
import os
from pathlib import Path
import sys
from typing import Generator, Iterator, Sequence
import warnings


class Module:

    def __init__(self, path: str | Sequence[str]):
        if isinstance(path, str):
            self.path = tuple(path.split("."))
        elif isinstance(path, list):
            self.path = tuple(path)
        elif isinstance(path, tuple):
            self.path = path
        del path

        self.route = ".".join(self.path)
        self.name = self.path[-1]
        self.root = self.path[0]

        self.parent: Module | None = None
        self.children: list[Module] = []

    @property
    def is_project(self):
        return isinstance(self, ProjectModule)

    @cached_property
    def is_builtin(self):
        root = self.path[0]
        return is_builtin(root)

    @property
    def is_3rdparty(self):
        return not self.is_project and not self.is_builtin

    @cached_property
    def type(self):
        if self.is_project:
            return "project"
        if self.is_builtin:
            return "builtin"
        return "3rdparty"

    def __str__(self):
        if self.is_project:
            return self.route
        return f"{self.route} ({self.type})"

    def __repr__(self):
        return str(self)

    def is_root(self):
        return self.parent is None

    def is_leaf(self):
        return not self.children

    def get_root(self) -> Module:
        if self.parent is None:
            return self
        return self.parent.get_root()
    
    def find_leaf(self) -> Module:
        """Return any leaf"""
        if self.is_leaf():
            return self
        return self.children[0].find_leaf()
    
    @property
    def path_to_root(self) -> Generator[Module, None, None]:
        m = self
        while m:
            yield m
            m = m.parent


class ProjectModule(Module):

    def __init__(
        self,
        path: str | Sequence[str],
        file_path: Path | None = None,
    ):
        super().__init__(path=path)
        self.file_path = file_path
        self.imports: list[Module] = []

    @staticmethod
    def from_file(file_path: Path):
        assert file_path.suffix == ".py"
        path = (*file_path.parts[:-1], file_path.stem)
        return ProjectModule(file_path=file_path, path=path)

    @cached_property
    def import_routes(self) -> list[str] | None:
        if not self.file_path:
            return None
        imports = analyze_imports(self.file_path)
        names = extract_module_names(imports)

        # Handle relative imports
        routes = []
        for name in names:
            first = name.split(".")[0]
            paths = [self.file_path.parent / f"{first}.py", self.file_path.parent / first]
            if any(os.path.exists(p) for p in paths):
                if is_builtin(name):
                    warnings.warn(f"module '{first}' (imported in {self.route}) is both local and builtin.")
                routes.append(".".join([*self.path[:-1], name]))
            else:
                routes.append(name)
        return routes


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


def is_builtin(name: str):
    return name in sys.stdlib_module_names or name in sys.builtin_module_names


def analyze_imports(file_path: Path):
    """Analyze a Python file to extract import statements."""
    with open(file_path, "r", encoding="utf-8") as source_file:
        source_code = source_file.read()

    tree = ast.parse(source_code, filename=file_path)

    # Extract top-level import statements
    imports = [
        node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    ]

    return imports


def extract_module_names(import_nodes: list[ast.Import | ast.ImportFrom]) -> list[str]:
    """Extract module names from import nodes."""
    module_names = []
    for node in import_nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_names.append(node.module)
    return module_names
