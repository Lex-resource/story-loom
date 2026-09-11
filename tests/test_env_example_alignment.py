"""S16 验收：.env.example 与 config.Settings 逐 key 对照。

新增 Settings 字段必须同步写进 .env.example（含注释掉的"有默认值、
通常无需覆盖"项），避免生产部署时配置项静默缺失。
"""
import re
from pathlib import Path

from config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"

# `KEY=` 或注释形态 `# KEY=`（注释 = 有默认值、通常无需覆盖）
_KEY_RE = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)\s*=", re.M)


def _documented_keys() -> set[str]:
    return set(_KEY_RE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def test_every_settings_field_is_documented():
    missing = sorted(set(Settings.model_fields) - _documented_keys())
    assert missing == [], f".env.example 缺少配置项: {missing}"


def test_env_example_has_no_unknown_keys():
    unknown = sorted(_documented_keys() - set(Settings.model_fields))
    assert unknown == [], f".env.example 里的未知配置项: {unknown}"
