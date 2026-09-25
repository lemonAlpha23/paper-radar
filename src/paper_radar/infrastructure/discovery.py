import importlib
import inspect
import pkgutil

from paper_radar.core.exceptions import RadarError


def discover[T](package_name: str, base: type[T]) -> dict[str, type[T]]:
    """Discover concrete, locally defined implementations in a trusted package."""
    package = importlib.import_module(package_name)
    found: dict[str, type[T]] = {}
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        module = importlib.import_module(info.name)
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                candidate is base
                or not issubclass(candidate, base)
                or inspect.isabstract(candidate)
                or candidate.__module__ != module.__name__
            ):
                continue
            name = getattr(candidate, "name", "")
            if not isinstance(name, str) or not name:
                raise RadarError(f"Plugin {candidate.__name__} has no name")
            if name in found:
                raise RadarError(f"Duplicate plugin name: {name}")
            found[name] = candidate
    return found
