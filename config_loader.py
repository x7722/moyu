import json
from typing import Optional, Dict, Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

from paths import get_bundled_config_paths, get_external_config_paths


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并配置，override 中的键优先。"""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge_dict(result[k], v)
        else:
            result[k] = v
    return result


def _load_config_file(path: str) -> Dict[str, Any]:
    if yaml is None:
        raise ModuleNotFoundError(
            "未安装 PyYAML，无法读取 YAML 配置。请执行 `pip install PyYAML` 或 `pip install -r requirements.txt`。"
        )
    if path.endswith((".yml", ".yaml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    elif path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            data = yaml.safe_load(text)
        except Exception:
            data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（根节点不是对象）：{path}")
    return data


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    先加载内置默认配置（YAML），
    再使用外部覆盖配置（若存在）递归覆盖，仅需写改动字段即可。
    """
    # 1) 内置配置
    base_cfg: Dict[str, Any] = {}
    from os import path as _p

    for candidate in get_bundled_config_paths():
        if _p.exists(candidate):
            try:
                base_cfg = _load_config_file(candidate)
                break
            except Exception:
                continue
    if not base_cfg:
        raise FileNotFoundError("未找到内置配置文件（config.yml 或 config.yaml）。")

    # 2) 外部覆盖配置（可选）
    if path:
        override_paths = [path]
    else:
        override_paths = get_external_config_paths()

    merged = dict(base_cfg)
    for candidate in override_paths:
        if candidate and _p.exists(candidate):
            try:
                override_cfg = _load_config_file(candidate)
                merged = _merge_dict(merged, override_cfg)
            except Exception:
                # 忽略损坏的外部配置，继续使用内置/已有合并结果
                continue

    return merged
