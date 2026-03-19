from __future__ import annotations

from shared.strategies.report import StrategyReport


def test_strategy_report_writes_utf8_markdown_and_json(tmp_path):
    report = StrategyReport(
        strategy_id="S5",
        strategy_name="S5_time_phase_midpoint_reclaim",
        context="live",
        date_range_start="2026-03-19T18:00:00+00:00",
        date_range_end="2026-03-19T23:00:00+00:00",
        total_bets=1,
        wins=1,
        total_pnl=1.23,
    )

    md_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"

    report.to_markdown(str(md_path))
    report.to_json(str(json_path))

    markdown = md_path.read_text(encoding="utf-8")
    payload = json_path.read_text(encoding="utf-8")

    assert "→" in markdown
    assert '"strategy_id": "S5"' in payload
