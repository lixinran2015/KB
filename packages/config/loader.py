import os
from pathlib import Path
import yaml
from typing import Any, Dict, List

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "config")


def load_yaml(filename: str) -> Dict[str, Any]:
    path = os.path.join(CONFIG_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scoring_rules() -> Dict[str, Any]:
    return load_yaml("scoring_rules.yml")


def load_stocks() -> list:
    return load_yaml("stocks.yml").get("stocks", [])


def save_stocks(stocks: list) -> None:
    path = os.path.join(CONFIG_DIR, "stocks.yml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"stocks": stocks}, f, allow_unicode=True, sort_keys=False)


def load_industry(name: str) -> Dict[str, Any]:
    return load_yaml(f"industries/{name}.yml")


def save_industry(name: str, data: Dict[str, Any]) -> None:
    """Save an industry config to config/industries/{name}.yml."""
    industry_dir = Path(CONFIG_DIR) / "industries"
    industry_dir.mkdir(parents=True, exist_ok=True)
    path = industry_dir / f"{name}.yml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def load_all_industries() -> List[Dict[str, str]]:
    """Scan config/industries/ and return a list of {key, name, icon} dicts."""
    industry_dir = Path(CONFIG_DIR) / "industries"
    if not industry_dir.exists():
        return []

    industries = []
    for f in sorted(industry_dir.glob("*.yml")):
        key = f.stem
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            industries.append({
                "key": key,
                "name": data.get("name", key),
                "icon": "🏭",
            })
        except Exception:
            continue
    return industries
