"""CLI entrypoint.

Usage:
    python main.py --topic "AA 制" --versions 3
    python main.py --input example/AA制/input.txt --versions 3 --slug AA制
    python main.py --input example/AA制/input.txt --output ./output --versions 2
    python main.py --topic "AA 制" --config my_config.toml
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import click

from config import ConfigError, load_config
from pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "output"
MAX_VERSIONS = 20


def _slugify(text: str) -> str:
    """Make a filesystem-safe folder name from a topic string.

    Keeps CJK characters; drops shell-unfriendly punctuation.
    """
    cleaned = re.sub(r"[\s/\\:*?\"<>|]+", "_", text.strip())
    cleaned = cleaned.strip("_.")
    return cleaned or "untitled"


def _read_topic_from_input(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    # convention used in example/AA制/input.txt: "主題是探討 AA 制"
    m = re.match(r"^\s*主題[是為:：]\s*(?:探討\s*)?(.+?)\s*$", text)
    return m.group(1) if m else text


@click.command()
@click.option("--topic", "topic", default=None, help="Topic string (e.g. 'AA 制').")
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a text file whose first line names the topic.",
)
@click.option(
    "--versions",
    "versions",
    type=int,
    default=None,
    help=f"Number of article versions to produce (1-{MAX_VERSIONS}). Overrides config.toml.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Output root. Files go to <output>/<slug>/output_{{i}}.txt. Defaults to [output].dir in config.toml, else {DEFAULT_OUTPUT}.",
)
@click.option("--slug", "slug", default=None, help="Folder slug under output/. Defaults to [output].slug in config.toml, else a slugified topic.")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to config.toml. Defaults to ./config.toml if it exists; else built-in defaults.",
)
@click.option("--quiet", is_flag=True, help="Suppress per-step progress output.")
def main(
    topic: str | None,
    input_file: Path | None,
    versions: int | None,
    output_dir: Path | None,
    slug: str | None,
    config_path: Path | None,
    quiet: bool,
) -> None:
    if topic and input_file:
        raise click.UsageError("provide --topic OR --input, not both")

    try:
        config = load_config(config_path)
    except ConfigError as e:
        raise click.UsageError(str(e)) from e

    if not topic and not input_file and not config.topic:
        raise click.UsageError("provide --topic, --input, or set [output].topic in config.toml")

    effective_versions = versions if versions is not None else config.versions
    if not 1 <= effective_versions <= MAX_VERSIONS:
        raise click.UsageError(f"versions must be between 1 and {MAX_VERSIONS}, got {effective_versions}")
    if len(config.version_specs) > effective_versions:
        raise click.UsageError(
            f"config has {len(config.version_specs)} [[versions]] entries but versions={effective_versions}; "
            "delete extras or raise --versions"
        )

    if input_file:
        topic = _read_topic_from_input(input_file)
    if not topic:
        topic = config.topic
    assert topic is not None

    slug = slug or config.output_slug or _slugify(topic)
    if output_dir is None:
        output_dir = Path(config.output_dir) if config.output_dir else DEFAULT_OUTPUT
    output_dir = output_dir.resolve()

    click.echo(f"Topic       : {topic}")
    click.echo(f"Versions    : {effective_versions}" + (
        f" ({len(config.version_specs)} specified, {effective_versions - len(config.version_specs)} auto)"
        if config.version_specs else " (all auto)"
    ))
    if config.version_specs:
        for i, spec in enumerate(config.version_specs, start=1):
            click.echo(f"  v{i}: style={spec.style:<14} length={spec.length}")
    click.echo(f"Output      : {output_dir / slug}/output_{{1..{effective_versions}}}.txt")
    click.echo(f"Models      : orch={config.models['orchestrator']} book={config.models['book']} "
               f"others={config.models['hotspot']}/{config.models['pain_point']}/{config.models['character']}")
    click.echo(f"Retrieval   : books_per_article={config.books_per_article} passages_per_book={config.passages_per_book}")
    click.echo(f"Characters  : count={config.character_count}")
    if config.social_post.enabled:
        click.echo(f"Social post : ON (platform={config.social_post.platform}, length={config.social_post.length})")
    click.echo("-" * 60)

    asyncio.run(
        run_pipeline(
            topic=topic,
            versions=effective_versions,
            output_dir=output_dir,
            slug=slug,
            config=config,
            verbose=not quiet,
        )
    )

    written = sorted((output_dir / slug).glob("output_*.txt"))
    click.echo("-" * 60)
    click.echo(f"Wrote {len(written)} file(s):")
    for p in written:
        click.echo(f"  {p}")


if __name__ == "__main__":
    main()
