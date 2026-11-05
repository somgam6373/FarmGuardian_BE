import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy.pool import NullPool

from app.core.db import engine_options

ROOT = Path(__file__).resolve().parents[1]


def test_local_keeps_the_default_pool():
    assert engine_options(on_vercel=False) == {}


def test_vercel_holds_no_connections_and_turns_prepared_statements_off():
    # Supabase transaction 풀러는 prepared statement를 지원하지 않는다
    assert engine_options(on_vercel=True) == {
        "poolclass": NullPool,
        "connect_args": {"prepare_threshold": None},
    }


def test_starting_the_app_does_not_load_anthropic():
    # anthropic 로딩이 앱 시작 시간의 절반을 넘는다. Vercel 첫 접속이 그만큼 느려진다
    code = "import sys, app.main; sys.exit('anthropic' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], cwd=ROOT).returncode == 0


def test_vercel_runs_in_seoul_next_to_the_database():
    assert json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))["regions"] == ["icn1"]


def test_vercel_uses_the_python_version_the_tests_run_on():
    version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert version == f"{sys.version_info.major}.{sys.version_info.minor}"
