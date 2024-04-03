from dependentspy.main import dependentspy


if __name__ == "__main__":
    G = dependentspy(
        ".",
        name="dependentspy-test",
        allow_local_imports=True,
        render_imports=True,
        prune=False,
        use_clusters=True,
        use_nested_clusters=True,
        min_cluster_size=1,
        show_3rdparty=True,
        show_builtin=False,
        summarize_external=True,
        ignore=["drafts*", "ocean.py"],
        hide=[],
        output_to_project=True,
        save_dot=True,
        render="if_changed",
        format="png",
        comment="Test dependency graph of the dependentspy module",
    )
    G.view()
