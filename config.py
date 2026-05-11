"""Project config loaded from a TOML file.

Layered defaults: built-in defaults < ./config.toml (or --config) < CLI flags.
The CLI layer is applied in main.py after this module returns a Config.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

VALID_STYLES: frozenset[str] = frozenset({"story", "philosophical", "wisdom-anchor", "actionable", "thread"})
# Wide range so users can experiment with very short threads (50 字) up to long-form essays.
LENGTH_MIN, LENGTH_MAX = 50, 15000
DEFAULT_LENGTH = 3500
VALID_PLATFORMS: frozenset[str] = frozenset({"threads", "ig", "fb", "general"})
VALID_AGENT_KEYS: frozenset[str] = frozenset({"hotspot", "pain_point", "character", "book", "orchestrator", "writer", "reviewer", "social"})


@dataclass(frozen=True)
class VersionSpec:
    style: str
    length: int


@dataclass
class SocialPostSpec:
    enabled: bool = False
    length: int = 300            # target chars for the social post
    platform: str = "general"    # one of VALID_PLATFORMS


@dataclass
class ReviewSpec:
    enabled: bool = False        # true 時，每篇長文（+ 社群版）寫完後跑 N 輪 AI 味審查改寫
    iterations: int = 1          # 審查改寫迭代輪數（1-5）


@dataclass
class Config:
    versions: int = 3
    length_tolerance: float = 0.15
    default_length: int = DEFAULT_LENGTH
    output_dir: str | None = None
    output_slug: str | None = None
    topic: str | None = None
    version_specs: list[VersionSpec] = field(default_factory=list)
    books_per_article: int = 3
    passages_per_book: int = 5
    character_count: int = 6
    social_post: SocialPostSpec = field(default_factory=SocialPostSpec)
    review: ReviewSpec = field(default_factory=ReviewSpec)
    models: dict[str, str] = field(default_factory=lambda: {
        "hotspot": "haiku",
        "pain_point": "sonnet",
        "character": "sonnet",
        "book": "opus",
        "orchestrator": "opus",
        "writer": "opus",
        "reviewer": "sonnet",
        "social": "sonnet",
    })


class ConfigError(ValueError):
    """Raised when config.toml is malformed."""


def _validate(cfg: Config) -> None:
    if cfg.versions < 1 or cfg.versions > 20:
        raise ConfigError(f"[output].versions must be 1..20, got {cfg.versions}")
    if not 0 < cfg.length_tolerance <= 0.5:
        raise ConfigError(f"[output].length_tolerance must be in (0, 0.5], got {cfg.length_tolerance}")
    if cfg.books_per_article < 1:
        raise ConfigError(f"[retrieval].books_per_article must be >= 1, got {cfg.books_per_article}")
    if cfg.passages_per_book < 1:
        raise ConfigError(f"[retrieval].passages_per_book must be >= 1, got {cfg.passages_per_book}")
    if cfg.character_count < 1:
        raise ConfigError(f"[character].count must be >= 1, got {cfg.character_count}")

    for i, spec in enumerate(cfg.version_specs, start=1):
        if spec.style not in VALID_STYLES:
            raise ConfigError(
                f"[[versions]] #{i}: style must be one of {sorted(VALID_STYLES)}, got {spec.style!r}"
            )
        if not (LENGTH_MIN <= spec.length <= LENGTH_MAX):
            raise ConfigError(
                f"[[versions]] #{i}: length must be in [{LENGTH_MIN}, {LENGTH_MAX}], got {spec.length}"
            )

    if len(cfg.version_specs) > cfg.versions:
        raise ConfigError(
            f"too many [[versions]] entries ({len(cfg.version_specs)}) for versions={cfg.versions}; "
            "delete extras or raise versions"
        )

    sp = cfg.social_post
    if sp.enabled:
        if not (LENGTH_MIN <= sp.length <= LENGTH_MAX):
            raise ConfigError(
                f"[social_post].length must be in [{LENGTH_MIN}, {LENGTH_MAX}], got {sp.length}"
            )
        if sp.platform not in VALID_PLATFORMS:
            raise ConfigError(
                f"[social_post].platform must be one of {sorted(VALID_PLATFORMS)}, got {sp.platform!r}"
            )

    rv = cfg.review
    if not (0 <= rv.iterations <= 5):
        raise ConfigError(f"[review].iterations must be in [0, 5], got {rv.iterations}")

    extra_models = set(cfg.models) - VALID_AGENT_KEYS
    if extra_models:
        raise ConfigError(f"[models] has unknown keys: {sorted(extra_models)}")
    missing_models = VALID_AGENT_KEYS - set(cfg.models)
    if missing_models:
        # not fatal — defaults filled, but warn early to make it explicit
        for key in missing_models:
            cfg.models[key] = Config().models[key]


def _from_dict(data: dict) -> Config:
    out = Config()

    output = data.get("output") or {}
    if "versions" in output:
        out.versions = int(output["versions"])
    if "length_tolerance" in output:
        out.length_tolerance = float(output["length_tolerance"])
    if "default_length" in output:
        out.default_length = int(output["default_length"])
    if "dir" in output:
        out.output_dir = str(output["dir"])
    if "slug" in output:
        out.output_slug = str(output["slug"])
    if "topic" in output:
        out.topic = str(output["topic"])

    versions_block = data.get("versions") or []
    out.version_specs = [
        VersionSpec(style=str(v["style"]), length=int(v["length"]))
        for v in versions_block
    ]

    retrieval = data.get("retrieval") or {}
    if "books_per_article" in retrieval:
        out.books_per_article = int(retrieval["books_per_article"])
    if "passages_per_book" in retrieval:
        out.passages_per_book = int(retrieval["passages_per_book"])

    character = data.get("character") or {}
    if "count" in character:
        out.character_count = int(character["count"])

    sp = data.get("social_post") or {}
    if sp:
        out.social_post = SocialPostSpec(
            enabled=bool(sp.get("enabled", False)),
            length=int(sp.get("length", out.social_post.length)),
            platform=str(sp.get("platform", out.social_post.platform)),
        )

    rv = data.get("review") or {}
    if rv:
        out.review = ReviewSpec(
            enabled=bool(rv.get("enabled", False)),
            iterations=int(rv.get("iterations", out.review.iterations)),
        )

    models = data.get("models") or {}
    for k, v in models.items():
        out.models[str(k)] = str(v)

    _validate(out)
    return out


def load_config(path: Path | None = None) -> Config:
    """Load config.toml. If path is None, fall back to ./config.toml; if neither
    exists, return defaults (= current behavior preserved).
    """
    if path is None:
        candidate = Path.cwd() / "config.toml"
        path = candidate if candidate.exists() else None

    if path is None:
        cfg = Config()
        _validate(cfg)
        return cfg

    with open(path, "rb") as f:
        data = tomllib.load(f)

    try:
        return _from_dict(data)
    except KeyError as e:
        raise ConfigError(f"missing required field in {path}: {e}") from e
