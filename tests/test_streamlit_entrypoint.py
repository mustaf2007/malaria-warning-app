from pathlib import Path
import runpy


def test_streamlit_entrypoint_executes_dashboard_on_every_rerun(monkeypatch):
    calls = []

    def record_run(path, **kwargs):
        calls.append((Path(path).name, kwargs))

    monkeypatch.setattr(runpy, "run_path", record_run)
    entrypoint = Path(__file__).resolve().parents[1] / "streamlit_app.py"
    source = entrypoint.read_text(encoding="utf-8")
    namespace = {"__file__": str(entrypoint)}

    # Streamlit reruns its entry-point script in the same Python process.
    exec(compile(source, str(entrypoint), "exec"), namespace)
    exec(compile(source, str(entrypoint), "exec"), namespace)

    assert calls == [("main.py", {}), ("main.py", {})]
