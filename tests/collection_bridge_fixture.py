"""Run the deployed pre-refactor callers against their actual 0089 schema."""

import hashlib
import importlib
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.collection_fixtures import historical_fixture_models

HASHES = {
    "collect_benchmark_due": "8e01e918d586f152f0e0fb120fa0c208754440cdcaad6215c05c015c497cc7a4",
    "collection_scheduling": "513410476eba9db46ec12948060e61d83474b8cb02830400f9a57d1f004b70a2",
    "collection_jobs": "e1cf4ac0908b1f75132f966cf8380246567a9920d983ea2a244b5b67f81b1b3e",
    "collection_state": "68ecf6b6d9f2a0a8a42fd829c08d802ec6713de595dec94a8b3801091661bb1b",
    "benchmark_metric_store": "00e58a42963fb51297b691ed5044134f9900f8976e3fc330ca44aaccf85af2a1",
    "hf_catalog": "b1a897c28f5a2d490bdbbd52bf197527530a09b74e18dd3edcc2262818605a00",
}


@contextmanager
def bridge_runtime(historical, *, job_owned=True):
    import core

    with historical_fixture_models(historical), pytest.MonkeyPatch.context() as patch:
        # Historical migration models omit Python properties. These are the
        # deployed read-through properties, not persistence compatibility fields.
        run = historical.get_model("core", "CollectionRun")
        for field in (
            ("source", "source_id", "purpose", "contract", "contract_id")
            if job_owned
            else ()
        ):
            patch.setattr(
                run,
                field,
                property(lambda value, name=field: getattr(value.job, name)),
                raising=False,
            )
        if job_owned:
            patch.setattr(
                run,
                "scope",
                property(lambda value: value.job.definition["scope"]),
                raising=False,
            )
        loaded = {}
        for name in (
            "benchmark_metric_store",
            "collection_jobs",
            "collection_state",
            "hf_catalog",
            "collection_scheduling",
            "collect_benchmark_due",
        ):
            qualified = (
                "core." + name
                if name != "collect_benchmark_due"
                else "monitor.management.commands.collect_benchmark_due"
            )
            path = (
                Path(__file__).parent
                / "fixtures"
                / "collection_compat"
                / f"{name}_64b95c26.py.txt"
            )
            source = path.read_bytes()
            assert hashlib.sha256(source).hexdigest() == HASHES[name]
            module = types.ModuleType(qualified)
            patch.setitem(sys.modules, qualified, module)
            parent = (
                core
                if qualified.startswith("core.")
                else importlib.import_module("monitor.management.commands")
            )
            patch.setattr(parent, name, module, raising=False)
            exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102 - hash-pinned deployed source
            loaded[qualified] = module
        # Tests also import functions before a fixture enters. Route those
        # aliases to the same frozen caller rather than mixing code revisions.
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
