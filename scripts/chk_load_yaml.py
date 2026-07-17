#!/usr/bin/env python3
"""Extracted: load_yaml"""
import os, sys, re


def load_yaml(yaml_path: str) -> dict:
    """加载 YAML 配置文件，失败时给出明确提示"""
    try:
        import yaml
    except ImportError:
        print("[ERROR] 需要 PyYAML 库。请执行: pip install pyyaml")
        sys.exit(1)

    if not os.path.exists(yaml_path):
        print(f"[WARN] 配置文件不存在: {yaml_path}")
        return {}

    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
