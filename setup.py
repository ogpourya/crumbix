import os
from setuptools import setup

def read_requirements():
    """Reads dependencies from requirements.txt."""
    if not os.path.exists("requirements.txt"):
        return []
    with open("requirements.txt", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="crumbix",
    version="1.0.0",
    py_modules=["crumbix"],
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "crumbix=crumbix:main",
        ],
    },
)
