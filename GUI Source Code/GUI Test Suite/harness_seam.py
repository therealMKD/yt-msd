"""Reaching the code under test wherever the program currently keeps it.

This suite drives the program by replacing parts of it - a fake yt-dlp, a fake
pointer, a subprocess that never spawns one. A replacement only tests something if
it lands on the code the program actually calls.

While the program was one .pyw, writing `mod.run_yt_dlp_json = fake` was enough. It
is not enough now. As waves move names into yt_msd.*, the .pyw keeps a re-exported
copy that nothing calls, so a write to the entry point lands on a name no caller
reads: the check still passes, and it tests nothing. That is the worst failure a
test suite can have, because nothing about it is visible.

So every replacement in this suite goes through patch() below. patch() finds each
module that owns the name - the entry point and any yt_msd module that defines or
imports it at module level - and writes to all of them, so whichever copy a caller
looks up, it finds the replacement. restore() gives every module its own original
back, which matters when two modules legitimately held different things under the
same name.

The owners are read out of the corpus with ast instead of written down here, so a
name that moves in a later wave is followed automatically: when the split moves
run_yt_dlp_json into a package module, nothing in this suite has to be edited.

patch() refuses a name nothing owns. A typo, or a name that stopped being a
module-level one, fails loudly here instead of quietly doing nothing.
"""

import ast
import importlib
import types
from contextlib import contextmanager
from pathlib import Path

_MISSING = object()


class SeamError(RuntimeError):
    """The suite asked to patch something the program does not have."""


_entry = None
_entry_name = None
_modules = {}        # dotted module name -> module object, for every yt_msd module
_owners = {}         # name -> [dotted module names that bind it at module level]
_original = {}       # name -> {dotted module name: the value it held before any patch}
_patched = set()     # names currently holding a replacement


def _imported_names(node):
    """Names an import statement binds."""
    names = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name != "*":
                names.add(alias.asname or alias.name)
    return names


def _module_level_bindings(path):
    """Names this file binds at module level - the only ones a patch can reach."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= _imported_names(node)
        elif isinstance(node, ast.Try):
            # A guarded import still binds at module level: the PyQt6 import in deps.py.
            for child in node.body:
                names |= _imported_names(child)
    return names


def install(entry_module, src_dir, package="yt_msd"):
    """Map the program as it is today: the entry point plus every module of `package`."""
    global _entry, _entry_name
    _entry = entry_module
    _entry_name = entry_module.__name__
    _modules.clear()
    _owners.clear()
    _original.clear()
    _patched.clear()

    corpus = [(_entry_name, Path(entry_module.__file__))]
    src_dir = Path(src_dir)
    package_dir = src_dir / package
    if package_dir.is_dir():
        for path in sorted(package_dir.rglob("*.py")):
            parts = list(path.relative_to(src_dir).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            corpus.append((".".join(parts), path))

    for dotted, path in corpus:
        if not path.is_file():
            continue
        for name in _module_level_bindings(path):
            _owners.setdefault(name, []).append(dotted)


def _module(dotted):
    if dotted == _entry_name:
        return _entry
    found = _modules.get(dotted)
    if found is None:
        found = importlib.import_module(dotted)
        _modules[dotted] = found
    return found


def owners(name):
    """Every module in the program that holds `name` at module level."""
    found = [m for m in (_module(d) for d in _owners.get(name, ())) if m is not None]
    if not found:
        raise SeamError(
            f"nothing in the program owns {name!r}. Either it has moved and this file still "
            f"names it, or it is not a module-level name and cannot be patched at all."
        )
    return found


def owned_by(name):
    """The same, as dotted names - for reporting."""
    return list(_owners.get(name, ()))


def original(name):
    """The real implementation of `name`, as it was before any patch touched it."""
    saved = _original.get(name)
    if saved:
        for value in saved.values():
            if value is not _MISSING:
                return value
    for module in owners(name):
        if hasattr(module, name):
            return getattr(module, name)
    raise SeamError(f"{name!r} has no value to read")


def patch(name, value):
    """Put `value` where every caller of `name` will find it."""
    found = owners(name)
    saved = _original.setdefault(name, {})
    for module in found:
        saved.setdefault(module.__name__, getattr(module, name, _MISSING))
        setattr(module, name, value)
    _patched.add(name)
    return value


def restore(name):
    """Hand every module back the value it had before the first patch of `name`."""
    saved = _original.get(name)
    if not saved:
        return
    for dotted, value in saved.items():
        module = _module(dotted)
        if module is None:
            continue
        if value is _MISSING:
            try:
                delattr(module, name)
            except AttributeError:
                pass
        else:
            setattr(module, name, value)
    _patched.discard(name)


def is_patched(name):
    return name in _patched


@contextmanager
def patched(name, value):
    """Hold `value` in place for the length of a block, and hand the name back afterwards.

    A replacement left in place is how one check quietly changes the next one, and a patch()/restore()
    pair can have its restore skipped by an exception raised in between. A check that needs a name
    replaced only while it is driving it uses this. restore() still hands back what was there before
    the first patch, so a name patched twice still comes back to the program's own value.
    """
    patch(name, value)
    try:
        yield value
    finally:
        restore(name)


def read(name):
    """Whatever the program currently sees for `name`, from the first module that owns it."""
    return getattr(owners(name)[0], name, _MISSING)


def partial_module(real, **overrides):
    """A stand-in that behaves exactly like `real` except for the names given here.

    Replacing a whole module is usually more than the suite means to do. Patching
    `subprocess` reaches every yt_msd module that imports it, including the audio
    helpers that call subprocess.run for real; a hand-written stand-in carrying only
    the few names one yt-dlp function happens to use breaks those. This keeps every
    other attribute - DEVNULL, PIPE, run, STARTUPINFO, TimeoutExpired - the genuine
    one, and swaps only what is named. Fake the narrowest thing the check is about.
    """
    stand_in = types.ModuleType(f"harness_for_{getattr(real, '__name__', 'module')}")
    for key, value in overrides.items():
        setattr(stand_in, key, value)
    stand_in.__dict__["__getattr__"] = lambda key: getattr(real, key)
    return stand_in


