"""Use exact v0.7 classes and reject a reference with changed shared runtime code."""

import hashlib
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "df8349b7abfcdd8485868225e6bb74589f397edb"
CHANGED = {"src/governed_memory/ledger.py", "src/governed_memory/retrieval.py"}


def reference_classes():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)

    paths = (
        git("ls-tree", "-r", "--name-only", COMMIT, "--", "src", "native/src").decode().splitlines()
    )
    hashes, modules = {}, {}
    for path in paths:
        original = git("show", f"{COMMIT}:{path}").replace(b"\r\n", b"\n")
        hashes[path] = hashlib.sha256(original).hexdigest()
        if path not in CHANGED:
            if (ROOT / path).read_bytes().replace(b"\r\n", b"\n") != original:
                raise ValueError(f"shared reference source changed: {path}")
            continue
        name = "_governed_memory_v07_" + Path(path).stem
        module = ModuleType(name)
        module.__file__ = f"<{COMMIT}:{path}>"
        sys.modules[name] = module
        exec(compile(original, module.__file__, "exec"), module.__dict__)
        modules[Path(path).stem] = module
    return (
        modules["ledger"].Ledger,
        modules["retrieval"].Retriever,
        {"commit": COMMIT, "source_sha256": hashes, "shared_runtime_unchanged": True},
    )
