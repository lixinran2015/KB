import os
import yaml
from typing import Any, Dict

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")


def load_yaml(filename: str) -> Dict[str, Any]:
    path = os.path.join(CONFIG_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scoring_rules() -> Dict[str, Any]:
    return load_yaml("scoring_rules.yml")


def load_stocks() -> list:
    return load_yaml("stocks.yml").get("stocks", [])


def load_industry(name: str) -> Dict[str, Any]:
    return load_yaml(f"industries/{name}.yml")
