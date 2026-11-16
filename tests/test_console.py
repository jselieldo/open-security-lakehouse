from pathlib import Path


def test_console_assets_exist() -> None:
    console = Path(__file__).parents[1] / "apps" / "console"
    assert (console / "index.html").is_file()
    assert (console / "styles.css").is_file()
    assert (console / "app.js").is_file()
    assert "Open Security Lakehouse" in (console / "index.html").read_text()
    assert "/api/v1/dashboard/summary" in (console / "app.js").read_text()


def test_investigation_console_exposes_event_details() -> None:
    console = Path(__file__).parents[1] / "apps" / "console"
    html = (console / "index.html").read_text()
    javascript = (console / "app.js").read_text()
    for element_id in (
        'id="event-details"',
        'id="event-message"',
        'id="event-metadata"',
        'id="copy-event-json"',
        'id="investigate-event-ip"',
    ):
        assert element_id in html
    assert "raw_event_json" in javascript
    assert "eventos encontrados" in javascript
    assert "showEventDetails" in javascript
    assert "app.js?v=" in html
    assert "styles.css?v=" in html
    assert 'id="pagination"' in html
    assert "total_count" in javascript
    assert "goToPage" in javascript
