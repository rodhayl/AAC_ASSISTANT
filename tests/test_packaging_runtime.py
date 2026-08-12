"""Regression coverage for the slim Windows packaging layout."""

from pathlib import Path

from src import config

REPO_ROOT = Path(__file__).parents[1]


def test_frozen_installed_runtime_uses_appdata_for_writable_files(tmp_path):
    """Program Files installs must not write beside the executable."""
    app_root = Path("C:/Program Files/AAC Assistant")

    runtime_root = config.resolve_runtime_root(
        app_root,
        is_frozen=True,
        appdata_root=tmp_path,
    )

    assert runtime_root == tmp_path / "AACAssistant"


def test_frozen_portable_runtime_keeps_data_beside_executable(tmp_path):
    """Portable copies keep their data next to the executable."""
    runtime_root = config.resolve_runtime_root(
        tmp_path,
        is_frozen=True,
        appdata_root=tmp_path / "AppData",
    )

    assert runtime_root == tmp_path


def test_bundled_ngrams_resolve_from_meipass(monkeypatch, tmp_path):
    """Frozen resources are read from the PyInstaller bundle, not runtime data."""
    bundle_root = tmp_path / "_MEIPASS"
    ngrams_root = bundle_root / "src" / "aac_app" / "data" / "ngrams"
    ngrams_root.mkdir(parents=True)

    monkeypatch.setattr(config, "IS_FROZEN", True)
    monkeypatch.setattr(config, "BUNDLE_DIR", bundle_root)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "installed")

    assert config.get_ngrams_path() == ngrams_root


def test_companion_templates_use_bundled_resource_path(monkeypatch, tmp_path):
    """TemplateManager loads YAML files included by the spec."""
    from src.aac_app.services import template_manager

    bundle_root = tmp_path / "_MEIPASS"
    templates_root = bundle_root / "src" / "aac_app" / "config" / "companion_templates"
    templates_root.mkdir(parents=True)
    (templates_root / "default.yaml").write_text(
        "name: Bundled Default\ndescription: bundled\nversion: '1.0'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "IS_FROZEN", True)
    monkeypatch.setattr(config, "BUNDLE_DIR", bundle_root)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "installed")

    manager = template_manager.TemplateManager()

    assert manager.get_template("default")["name"] == "Bundled Default"


def test_packaging_scripts_describe_slim_unattended_build():
    """Static packaging guardrails prevent the legacy unsafe build flow returning."""
    spec = (REPO_ROOT / "AAC_Assistant.spec").read_text(encoding="utf-8")
    build = (REPO_ROOT / "build_package.bat").read_text(encoding="utf-8").lower()
    installer = (REPO_ROOT / "installer.iss").read_text(encoding="utf-8").lower()
    launcher = (REPO_ROOT / "launcher.pyw").read_text(encoding="utf-8")

    assert "src/aac_app/data/ngrams" in spec
    assert "src/aac_app/config/companion_templates" in spec
    assert '".env.example", "."' in spec
    for package in ("faster_whisper", "ctranslate2", "av", "torch"):
        assert package in spec
    assert "taskkill /f /im python.exe" not in build
    assert "c:\\users\\rulfe" not in build
    assert "inno_setup_path" in build
    assert "findstr /r /b /c:\"#define myappversion \" installer.iss" in build
    assert "set \"version=%%~v\"" in build
    assert "existing runtime config found" in build
    assert "existing runtime data found" in build
    assert "iscc_exe=%inno_setup_path:\"=%" in build
    assert "where iscc.exe" in build
    assert 'echo @echo off' not in build
    assert 'echo rem' not in build
    assert "uvicorn.Server" in launcher
    assert "_wait_for_server" in launcher
    assert "AAC_ASSISTANT_NO_BROWSER" in launcher
    assert "dist\\aac_assistant\\*" in installer
    assert "closeapplications=force" in installer
    assert "restartapplications=no" in installer
    assert "[custommessages]" in installer
    assert "english.updatewelcome=" in installer
    assert "spanish.updatewelcome=" in installer
    assert "unsaved work may be lost" in installer
    assert "trabajo no guardado" in installer
    assert "procedure initializewizard;" in installer
    assert "procedure curpagechanged(curpageid: integer);" in installer
    assert "function preparetoinstall(var needsrestart: boolean): string;" in installer
    assert "powershell.exe" in installer
    assert "openeventw@kernel32.dll stdcall" in installer
    assert "setevent@kernel32.dll stdcall" in installer
    assert "getsha256ofstring" in installer
    assert "requestgracefulshutdown" in installer
    assert "result := 'local\\aacassistantshutdown_'" in installer
    assert "addseconds(25)" in installer
    assert "start-sleep -milliseconds 250" in installer
    assert "sleep(5000)" not in installer
    assert '#define myappprocessname "aac_assistant"' in installer
    assert "get-process -name ''{#myappprocessname}''" in installer
    assert "[io.path]::getfullpath($_.path)" in installer
    assert "stop-process -force" in installer
    assert "start-sleep -milliseconds 500" in installer
    assert "exit 1" in installer
    assert "custommessage('closefailed')" in installer
    assert "resultcode <> 0" in installer
    assert "/f /t /im {#myappexename}" not in installer
    assert "addbackslash(wizardform.diredit.text) + '{#myappexename}'" in installer
    assert "defaultwelcomemessage" in installer
    assert "wizardform.diredit.onchange := @direditchanged" in installer
    assert "custommessage('updatewelcome')" in installer
    assert "source: \".env.example\"" in installer
    uninstall = installer.split("[uninstalldelete]", 1)[1].split("[messages]", 1)[0]
    assert 'name: "{app}\\data"' not in uninstall
    assert 'name: "{app}\\uploads"' not in uninstall
    assert 'type: filesandordirs' in uninstall
