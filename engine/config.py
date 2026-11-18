import functools
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "Configuration"


@functools.lru_cache
def settings():
    return yaml.safe_load((CONF / "settings.yaml").read_text(encoding="utf-8"))


@functools.lru_cache
def taxonomy():
    return yaml.safe_load((CONF / "taxonomy.yaml").read_text(encoding="utf-8"))


def seed_sources():
    return yaml.safe_load((CONF / "sources_seed.yaml").read_text(encoding="utf-8"))["sources"]
