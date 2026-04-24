from pathlib import Path

from typer.testing import CliRunner

from som_seedtalent_capture.cli import app

runner = CliRunner()


def test_batch_create_writes_json(tmp_path: Path):
    out = tmp_path / "batch.json"
    result = runner.invoke(app, ["batch", "create", "--scope", "fake test scope", "--operator", "tester", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert "capture_batch_id" in out.read_text()


def test_session_note_writes_json(tmp_path: Path):
    out = tmp_path / "note.json"
    result = runner.invoke(app, [
        "session", "note",
        "--session-id", "session_fake",
        "--timestamp-ms", "1234",
        "--note", "Fake operator note",
        "--out", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    assert "Fake operator note" in out.read_text()
