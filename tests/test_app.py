import importlib.util
from pathlib import Path
from types import SimpleNamespace

APP_PATH = Path(__file__).parents[1] / "app.py"
APP_SPEC = importlib.util.spec_from_file_location("youtube_wiki_streamlit_app", APP_PATH)
assert APP_SPEC is not None and APP_SPEC.loader is not None
app = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(app)


def test_video_table_keeps_columns_when_empty(monkeypatch):
    repository = SimpleNamespace(statuses=lambda video_ids: {})
    monkeypatch.setattr(app, "state_repository", lambda database_path: repository)

    table = app.video_table([])

    assert table.empty
    assert table.columns.tolist() == app.VIDEO_TABLE_COLUMNS
    table.sort_values("Published", ascending=False)
