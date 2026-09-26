import importlib
import pkgutil

import pytest

from bot import cogs as cogs_package


def test_all_cogs_import() -> None:
    """Регрессия: ког с битым импортом не грузится только в рантайме, тесты молчат."""
    names = [
        module.name
        for module in pkgutil.iter_modules(cogs_package.__path__)
        if not module.name.startswith("_")
    ]
    assert names, "коги не найдены"
    for name in names:
        importlib.import_module(f"{cogs_package.__name__}.{name}")


@pytest.mark.asyncio
async def test_cogs_setup_callable() -> None:
    for module in pkgutil.iter_modules(cogs_package.__path__):
        if module.name.startswith("_"):
            continue
        imported = importlib.import_module(f"{cogs_package.__name__}.{module.name}")
        assert callable(getattr(imported, "setup", None)), f"{module.name} без setup(bot)"
