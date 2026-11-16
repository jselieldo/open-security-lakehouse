from pathlib import Path


def test_console_assets_exist() -> None:
    console = Path(__file__).parents[1] / "apps" / "console"
    assert (console / "index.html").is_file()
    assert (console / "styles.css").is_file()
    assert (console / "app.js").is_file()
    assert "Open Security Lakehouse" in (console / "index.html").read_text()
    assert "/api/v1/dashboard/summary" in (console / "app.js").read_text()
