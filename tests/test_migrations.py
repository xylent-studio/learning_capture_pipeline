from pathlib import Path

from alembic import command
from alembic.config import Config


def test_alembic_upgrade_head_smoke(tmp_path: Path):
    database_path = tmp_path / "alembic-smoke.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve()}")
    config.set_main_option("script_location", str(Path("alembic").resolve()))

    command.upgrade(config, "head")

    assert database_path.exists()
