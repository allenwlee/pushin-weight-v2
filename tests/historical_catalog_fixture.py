"""Pin pre-RG5 fixture builders to the catalog code that used their schema."""

import hashlib
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

HASHES = {
    "measurement_taxonomy": "51cdf01cbb7450ecd37f81d6c9143b6821860e6027a2ec7fb8fc55c7df48bbab",
    "model_kind_qualification": "903e7b5244398bcfc380bd068cdd7456d837f9df0e31507c956a379da73ffc0a",
    "benchmark_metric_identity": "245ecdffeccf9178a6b2dea7ec9f501bc22a54a3e0dea932fc3e69c00ba7df91",
}


@contextmanager
def catalog_runtime(historical):
    import core

    with pytest.MonkeyPatch.context() as patch:
        loaded = {}
        for name, expected in HASHES.items():
            qualified = "core." + name
            path = (
                Path(__file__).parent
                / "fixtures"
                / "collection_compat"
                / f"{name}_4952955f.py.txt"
            )
            source = path.read_bytes()
            assert hashlib.sha256(source).hexdigest() == expected
            module = types.ModuleType(qualified)
            patch.setitem(sys.modules, qualified, module)
            patch.setattr(core, name, module, raising=False)
            exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102 - hash-pinned deployed fixture
            for symbol, value in list(vars(module).items()):
                if hasattr(value, "_meta") and value._meta.app_label == "core":
                    try:
                        replacement = historical.get_model(
                            "core", value._meta.model_name
                        )
                    except LookupError:
                        # The pinned registration code checks whether these
                        # later catalogues exist before using them.
                        continue
                    patch.setattr(module, symbol, replacement)
            loaded[qualified] = module
        for name, module in list(sys.modules.items()):
            if (
                not name.startswith(("core.", "tests."))
                or module is None
                or module in loaded.values()
            ):
                continue
            for symbol, value in list(vars(module).items()):
                owner = loaded.get(getattr(value, "__module__", None))
                if (
                    owner is not None
                    and isinstance(value, types.FunctionType)
                    and hasattr(owner, value.__name__)
                ):
                    patch.setattr(module, symbol, getattr(owner, value.__name__))
        yield
