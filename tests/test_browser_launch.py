from douyin_archive.browser_launch import chromium_launch_options


def test_chromium_launch_uses_configured_executable(monkeypatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "/usr/local/bin/douyin-chromium")

    options = chromium_launch_options()

    assert options["headless"] is True
    assert options["executable_path"] == "/usr/local/bin/douyin-chromium"
    assert "--disable-dev-shm-usage" in options["args"]
    assert "--no-sandbox" in options["args"]


def test_chromium_launch_lets_playwright_resolve_default(monkeypatch) -> None:
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)

    options = chromium_launch_options()

    assert "executable_path" not in options
