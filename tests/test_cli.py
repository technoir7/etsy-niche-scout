from pathlib import Path

from typer.testing import CliRunner

from niche_scout import cli


runner = CliRunner()


def test_enrich_csv_path_warns_user(monkeypatch, tmp_path) -> None:
    input_csv = tmp_path / "input.csv"
    metrics_csv = tmp_path / "metrics.csv"
    input_csv.write_text("normalized_query\nrealtor intake form\n", encoding="utf-8")
    metrics_csv.write_text("Keyword Phrase,Search Volume\nrealtor intake form,1000\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "enrich_file",
        lambda input_path, metrics, source="erank": {"csv": Path("out.csv"), "json": Path("out.json"), "markdown": Path("out.md")},
    )

    result = runner.invoke(cli.app, ["enrich", str(input_csv), "--metrics", str(metrics_csv)])

    assert result.exit_code == 0
    assert "CSV enrichment only performs column joins" in result.stdout
