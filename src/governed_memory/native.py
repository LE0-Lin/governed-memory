"""Optional native kernels, selected by the operator rather than a tool caller."""

from importlib import import_module


def kernels(backend: str):
    if backend not in {"auto", "python", "rust"}:
        raise ValueError("ranking backend must be auto, python or rust")
    if backend == "python":
        return None
    try:
        return import_module("governed_memory_native")
    except ModuleNotFoundError as exc:
        if exc.name != "governed_memory_native" or backend == "rust":
            raise RuntimeError("install the native extra with a Rust toolchain") from exc
        return None
