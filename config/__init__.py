"""
元策·擎天 配置加载器
从 config/*.yaml 加载所有配置，提供统一的 dict 接口。
app.yaml → cfg.app (扁平 dict)
plans.yaml → cfg.plans
rules.yaml → cfg.rules
"""
import os, yaml
from pathlib import Path

_CONFIG_DIR = Path(__file__).parent

def _load_yaml(name: str) -> dict:
    p = _CONFIG_DIR / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

class _Config:
    _loaded = {}

    def __getattr__(self, name):
        if name not in self._loaded:
            if name == "app":
                self._loaded["app"] = _load_yaml("app.yaml")
            elif name == "plans":
                self._loaded["plans"] = _load_yaml("plans.yaml")
            elif name == "rules":
                self._loaded["rules"] = _load_yaml("rules.yaml")
            else:
                raise AttributeError(f"Unknown config section: {name}")
        return self._loaded[name]

    def reload(self):
        self._loaded.clear()

    def get(self, *path, default=None):
        """
        安全读取嵌套配置:
          cfg.get('server', 'api_port')         → app.yaml 的 server.api_port
          cfg.get('rules', 'brands', 'A2080')   → rules.yaml 的 brands.A2080
          cfg.get('plans', 'plans', 'starter')  → plans.yaml 的 plans.starter
          cfg.get('procurement', 'sku_per_unit')→ app.yaml 的 procurement.sku_per_unit
        """
        if not path:
            return default
        
        section = path[0]
        if section in ('plans', 'rules'):
            # plans.yaml / rules.yaml → data IS the file content
            data = getattr(self, section)
            keys = path[1:]  # skip section name
        else:
            # Everything else lives in app.yaml
            data = getattr(self, 'app')
            keys = path  # keep all keys for navigation
        
        d = data
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key)
            else:
                return default
        return d if d is not None else default

cfg = _Config()

# ─── 快捷函数 ───
def get_plans():
    p = cfg.plans.get("plans", {})
    return list(p.values()) if isinstance(p, dict) else []

def get_brand_rules():
    return cfg.rules.get("brands", {})

def get_approval_flow():
    return cfg.rules.get("approval_flow", [])

def get_price_floors():
    return cfg.rules.get("price_floors", [])

def get_dimension(key: str):
    return cfg.rules.get("dimensions", key, {})

def sku_per_unit():
    return cfg.get("procurement", "sku_per_unit", default=20)

def calc_procurement_units(sku_count: int) -> int:
    spu = sku_per_unit()
    return (sku_count + spu - 1) // spu if spu > 0 else sku_count
