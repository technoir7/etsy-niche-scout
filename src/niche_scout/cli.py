"""Typer CLI for Etsy Niche Scout."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from niche_scout.config import ROOT_DIR, load_defaults
from niche_scout.exporters import report_from_csv, report_from_json
from niche_scout.keyword_expansion import expand_keywords
from niche_scout.logging import setup_logging
from niche_scout.main import compare_files, enrich_file, import_metrics_file, load_ranked_payload, run_scan, score_file


app = typer.Typer(help="Local Etsy niche discovery for digital products.")
import_app = typer.Typer(help="Import external keyword metrics.")
app.add_typer(import_app, name="import")
console = Console()


def output_table(title: str, rows: list[tuple[str, ...]], headers: list[str]) -> None:
    table = Table(title=title)
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    console.print(table)


@app.callback()
def callback() -> None:
    setup_logging()


@app.command()
def expand(
    seeds: Annotated[list[str], typer.Argument(help="Seed niche keywords.")],
) -> None:
    defaults = load_defaults()
    expanded = expand_keywords(seeds, defaults.expansion)
    output_table(
        "Expanded Keywords",
        [(str(index + 1), query) for index, query in enumerate(expanded)],
        ["#", "Query"],
    )


@app.command()
def scan(
    seeds: Annotated[list[str], typer.Argument(help="Seed niche keywords.")],
    top_n: Annotated[int, typer.Option("--top-n", min=1, help="Max listings to inspect per query.")] = 24,
    use_cache: Annotated[bool, typer.Option("--use-cache/--no-cache", help="Reuse cached HTML snapshots when present.")] = False,
    refresh_cache: Annotated[bool, typer.Option("--refresh-cache", help="Ignore cached HTML and fetch fresh pages.")] = False,
) -> None:
    outputs = run_scan(seeds, top_n=top_n, use_cache=use_cache, refresh_cache=refresh_cache)
    output_table("Scan Outputs", [(key, str(path)) for key, path in outputs.items()], ["Artifact", "Path"])


@app.command()
def score(
    raw_path: Annotated[Path, typer.Argument(exists=True, readable=True, help="Raw scan JSON path.")],
) -> None:
    outputs = score_file(raw_path)
    output_table("Score Outputs", [(key, str(path)) for key, path in outputs.items()], ["Artifact", "Path"])


@import_app.command("metrics")
def import_metrics(
    metrics_path: Annotated[Path, typer.Argument(exists=True, readable=True, help="External metrics CSV.")],
    source: Annotated[str, typer.Option("--source", help="Metrics source name.")] = "erank",
) -> None:
    try:
        outputs = import_metrics_file(metrics_path, source=source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    output_table("Imported Metrics", [(key, str(path)) for key, path in outputs.items()], ["Artifact", "Path"])


@app.command()
def enrich(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True, help="Processed CSV or JSON file.")],
    metrics: Annotated[Path, typer.Option("--metrics", exists=True, readable=True, help="External metrics CSV.")],
    source: Annotated[str, typer.Option("--source", help="Metrics source name.")] = "erank",
) -> None:
    if input_path.suffix.lower() == ".csv":
        console.print(
            "[yellow]Warning: CSV enrichment only performs column joins. Use the JSON file for full score recalculation.[/yellow]"
        )
    try:
        outputs = enrich_file(input_path, metrics, source=source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    output_table("Enriched Outputs", [(key, str(path)) for key, path in outputs.items()], ["Artifact", "Path"])


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(exists=True, readable=True, help="Baseline CSV or JSON run.")],
    comparison: Annotated[Path, typer.Argument(exists=True, readable=True, help="Comparison CSV or JSON run.")],
) -> None:
    outputs = compare_files(baseline, comparison)
    output_table("Comparison Outputs", [(key, str(path)) for key, path in outputs.items()], ["Artifact", "Path"])


@app.command()
def families(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True, help="Processed JSON run.")],
    full: Annotated[bool, typer.Option("--full", help="Show the expanded family view.")] = False,
) -> None:
    payload = load_ranked_payload(input_path)
    if full:
        rows = [
            (
                family.cluster_name,
                f"{family.family_score:.1f}",
                str(family.family_width),
                family.family_type,
                ", ".join(family.keywords[:3]),
                f"{family.expansion_potential_score:.1f}",
                f"{family.bundle_potential_score:.1f}",
                family.launch_strategy,
            )
            for family in payload.families
        ]
        headers = ["Family", "Score", "Width", "Type", "Keywords", "Expansion", "Bundle", "Strategy"]
    else:
        rows = [
            (
                family.cluster_name,
                f"{family.family_score:.1f}",
                str(family.family_width),
                family.family_type,
                family.launch_strategy,
            )
            for family in payload.families
        ]
        headers = ["Family", "Score", "Width", "Type", "Strategy"]
    output_table("Family Analysis", rows, headers)


@app.command()
def report(
    input_path: Annotated[Path, typer.Argument(exists=True, readable=True, help="CSV or JSON processed file.")],
    format: Annotated[str, typer.Option("--format", help="Only markdown is supported in phase 2.")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output", help="Output report path.")] = None,
) -> None:
    if format != "markdown":
        raise typer.BadParameter("Only --format markdown is supported.")
    output_path = output or ROOT_DIR / "data/reports" / f"{input_path.stem}.md"
    if input_path.suffix.lower() == ".csv":
        report_from_csv(input_path, output_path)
    elif input_path.suffix.lower() == ".json":
        report_from_json(input_path, output_path)
    else:
        raise typer.BadParameter("Input must be a CSV or JSON file.")
    console.print(f"Report written to {output_path}")


@app.command()
def dashboard(
    payload: Annotated[
        Path,
        typer.Option("--payload", exists=True, readable=True, help="Processed JSON payload for the dashboard."),
    ] = ROOT_DIR / "data/processed/latest.json",
    compare_payload: Annotated[
        Path | None,
        typer.Option("--compare-payload", exists=True, readable=True, help="Optional second processed JSON payload."),
    ] = None,
) -> None:
    dashboard_path = ROOT_DIR / "src/niche_scout/dashboard.py"
    command = [sys.executable, "-m", "streamlit", "run", str(dashboard_path), "--", "--payload", str(payload)]
    if compare_payload is not None:
        command.extend(["--compare-payload", str(compare_payload)])
    subprocess.run(command, check=True)


def main() -> None:
    app()
