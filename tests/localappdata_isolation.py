"""Keep tests away from the real save folder under %LOCALAPPDATA% (freddys/Saved/SaveGames: the user's saves).

APBridgeClient._on_connected archives and recreates Playerarchi.sav under LOCALAPPDATA, so any test
that connects a client must redirect it first.
"""
import os
from pathlib import Path

from tests.gvas_fixtures import starter_player00

SAVE_SUBDIR = Path("freddys") / "Saved" / "SaveGames"


def isolate_localappdata(testcase, base_dir: Path, starter_save: bool = True) -> Path:
    """Point LOCALAPPDATA at <base_dir>/localappdata for this test; restored automatically.

    By default a synthetic, fresh Player00.sav is installed in its save folder. That is the template the client uses to create
    Playerarchi.sav, and it keeps the save helpers from falling back to files in the current directory (the developer's private
    saves), which made the suite depend on them.
    """
    fake = Path(base_dir) / "localappdata"
    fake.mkdir(parents=True, exist_ok=True)
    if starter_save:
        save_dir = fake / SAVE_SUBDIR
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / "Player00.sav").write_bytes(starter_player00())
    original = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(fake)

    def restore():
        if original is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original

    testcase.addCleanup(restore)
    return fake
