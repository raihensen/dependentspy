from setuptools import setup, find_packages

from dependentspy.version import __version__


setup(
    name="dependentspy",
    version=__version__,
    url="https://github.com/raihensen/dependentspy",
    author="raihensen",
    description="Another tool for dependency graphs in python, focusing on project-internal imports. ",
    packages=find_packages(include=["dependentspy"]),
    install_requires=[
        "graphviz >= 0.20.3",
        "networkx >= 3.2.1",
    ],
)
