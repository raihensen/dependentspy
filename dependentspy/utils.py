import os
from typing import Union
import networkx as nx


PathLike = Union[str, os.PathLike]  # Type hint for file paths


def find_dead_ends(gr: nx.DiGraph):
    out_degrees = {v: gr.out_degree(v) for v in gr.nodes}
    no_out = {v for v, d in out_degrees.items() if d == 0}
    
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
