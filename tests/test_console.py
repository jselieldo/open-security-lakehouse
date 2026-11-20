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
    assert 'name="windows_channel"' in html
    assert 'name="windows_event_id"' in html
    assert 'name="message_contains"' in html
    assert "eventDisplay" in javascript
    assert "Windows Event ID" in javascript
    assert 'id="triage-controls"' in html
    assert "updateSelectedAlert" in javascript
    assert "submitAlertComment" in javascript


def test_source_console_exposes_freshness_and_diagnostic_actions() -> None:
    console = Path(__file__).parents[1] / "apps" / "console"
    html = (console / "index.html").read_text()
    javascript = (console / "app.js").read_text()
    styles = (console / "styles.css").read_text()
    assert 'id="sources-summary"' in html
    assert "seconds_since_last_event" in javascript
    assert "seconds_until_silent" in javascript
    assert "active_silence_alert_id" in javascript
    assert "sourceGuidance" in javascript
    assert "investigateSource" in javascript
    assert "openSourceAlert" in javascript
    assert ".source-timing" in styles


def test_asset_console_exposes_inventory_and_investigation() -> None:
    console = Path(__file__).parents[1] / "apps" / "console"
    html = (console / "index.html").read_text()
    javascript = (console / "app.js").read_text()
    styles = (console / "styles.css").read_text()
    assert 'data-view="assets"' in html
    assert 'id="assets-summary"' in html
    assert 'id="assets-list"' in html
    assert "/api/v1/assets" in javascript
    assert "loadAssets" in javascript
    assert "investigateAsset" in javascript
    assert "saveAssetContext" in javascript
    assert "asset_criticality" in javascript
    assert "24 * 60 * 60 * 1000" in javascript
    assert ".asset-grid" in styles
