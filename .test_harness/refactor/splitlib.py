# One-shot tooling for the yt-msd GUI module split. Tracked, deliberately: the wave plan, the
# splitter, the verification gate and the record of every content edit it signed off are the
# only proof the split preserved anything, and a proof that exists on one machine proves nothing.
#
# The master copy stays GUI Source Code/yt-msd-gui.pyw throughout the split. Code is
# moved out in waves into GUI Source Code/yt_msd/, and the .pyw keeps working untouched
# because a re-export line replaces whatever was removed. The GUI Test Suite therefore
# keeps running against the same entry point after every wave, which is the point: no
# wave is accepted until the suite is still green.
#
#   python splitlib.py analyze            report the block map, wave plan and hazards
#   python splitlib.py extract <wave>     move one wave, write the files
#
# Blocks are whole top-level statements plus every comment line directly above them, so
# the file's extensive explanatory comments travel with the code they describe.
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # .test_harness/refactor -> repo root
GUI_DIR = os.path.join(ROOT, "GUI Source Code")
PYW = os.path.join(GUI_DIR, "yt-msd-gui.pyw")
PKG_DIR = os.path.join(GUI_DIR, "yt_msd")
HARNESS_DIR = os.path.join(GUI_DIR, "GUI Test Suite")

# Comment above each wave's module saying where its text came from.
MODULE_HEADER = '''# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package ({dotted}).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
'''


def read_pyw():
    with open(PYW, "r", encoding="utf-8") as fh:
        return fh.read()


def bound_names(node):
    """Names a top-level node binds in the module namespace."""
    found = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        found.append(node.name)
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    found.append(n.id)
    elif isinstance(node, ast.Import):
        for a in node.names:
            found.append(a.asname or a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for a in node.names:
            if a.name == "*":
                found.append("*")
            else:
                found.append(a.asname or a.name)
    elif isinstance(node, ast.Try):
        # Guard imports (winreg / vlc / watchdog) bind their names inside the try body.
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom)):
                for a in sub.names:
                    found.append(a.asname or a.name.split(".")[0])
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                found.append(sub.id)
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        pass
    return found


def free_names(node):
    """Names this block needs from MODULE scope.

    A name read inside a function is not a module dependency if anything anywhere in this
    block stores to it - that covers parameters, locals, comprehension targets, `except x as e`,
    walrus bindings and nested defs. The exception is a name a function declares `global`:
    that store writes the module's own name, so it is a genuine cross-module dependency and
    must be reported even though it also looks like a store. This is exactly how
    SILENCE_TRIM / SILENCE_PAD_DUR / CUSTOM_NORM_CMD travel between the settings dialog,
    MainApp and the normalizer, so getting this right is the whole point.
    """
    reads, stores, args, globals_ = set(), set(), set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            (reads if isinstance(sub.ctx, ast.Load) else stores).add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores.add(sub.name)
        elif isinstance(sub, ast.arguments):
            for a in (list(sub.posonlyargs) + list(sub.args) + list(sub.kwonlyargs)
                      + ([sub.vararg] if sub.vararg else [])
                      + ([sub.kwarg] if sub.kwarg else [])):
                args.add(a.arg)
        elif isinstance(sub, ast.ExceptHandler):
            if sub.name:
                stores.add(sub.name)          # `except X as e` binds via .name, not ast.Name
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            for a in sub.names:
                stores.add(a.asname or a.name.split(".")[0])
        elif isinstance(sub, ast.Global):
            globals_.update(sub.names)
    return (reads - stores - args - _builtins()) | globals_


def load_names(node):
    """Names this node reads, and the names it stores to, at any depth."""
    reads, stores = set(), set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            if isinstance(sub.ctx, ast.Load):
                reads.add(sub.id)
            else:
                stores.add(sub.id)
        elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores.add(sub.name)
    return reads, stores


def node_start(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.decorator_list:
        return min(d.lineno for d in node.decorator_list)
    return node.lineno


def parse_blocks():
    """Every top-level block: (index, node, kind, names, start, end).

    `start` reaches back to the end of the previous block so the comments sitting above a
    definition are carried along with it instead of being stranded in the shrinking .pyw.
    """
    text = read_pyw()
    tree = ast.parse(text)
    blocks, prev_end = [], 0
    for i, node in enumerate(tree.body):
        end = node.end_lineno
        blocks.append({
            "i": i,
            "node": node,
            "kind": type(node).__name__,
            "names": bound_names(node),
            "raw_start": node_start(node),
            "start": prev_end + 1,      # one-based, absorbs the gap comments above it
            "end": end,
        })
        prev_end = end
    return text, tree, blocks



IMPORT_KINDS = ("Import", "ImportFrom")
GUARD_KINDS = ("Try",)


def unconditional_names(node):
    """Names this block binds on every path. Inside a guard import, `import vlc` in the try
    body is unconditional but `_VLC_IMPORT_ERROR = str(e)` in its except handler is not, and
    the app relies on that difference: it reads the error text with getattr(..., default)
    precisely because the name is absent when the import succeeded."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    if isinstance(node, ast.Import):
        return {a.asname or a.name.split(".")[0] for a in node.names}
    if isinstance(node, ast.ImportFrom):
        return {a.asname or a.name for a in node.names}
    if isinstance(node, ast.Try):
        found = set()
        for sub in node.body:
            found |= unconditional_names(sub)
            for n in ast.walk(sub):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    found.add(n.id)
        return found
    return set()


def conditional_names(node):
    return set(bound_names(node)) - unconditional_names(node)


def block_text(text, block):
    lines = text.splitlines(keepends=True)
    return "".join(lines[block["start"] - 1:block["end"]])


def wave_plan():
    """Import waves.py next to this file: {wave_name: [(dotted_module, [names])]}.
    Keeping the plan in its own file is deliberate - it is the part a human reviews."""
    sys.path.insert(0, HERE)
    import waves
    return waves.WAVES


def plan_map():
    """name -> dotted module, flattened from the wave plan."""
    out = {}
    for _wave, groups in wave_plan().items():
        for dotted, names in groups:
            for name in names:
                if name in out and out[name] != dotted:
                    raise SystemExit("name listed in two modules: %s (%s, %s)"
                                     % (name, out[name], dotted))
                out[name] = dotted
    return out


def wave_names(wave):
    out = []
    for _dotted, names in wave_plan().get(wave, []):
        out.extend(names)
    return out


def analyze(wave=None):
    if wave and cross_module_globals(wave):
        print("\nCROSS-MODULE `global` HAZARDS in wave '%s':" % wave)
        for line in cross_module_globals(wave):
            print("  " + line)
    text, tree, blocks = parse_blocks()
    plan = plan_map()
    problems = []
    for b in blocks:
        named = [n for n in b["names"] if n != "*"]
        if not named:
            continue
        targets = {plan[n] for n in named if n in plan}
        if len(targets) > 1:
            problems.append("block %s spans modules: %s" % (named, sorted(targets)))

    picked = [b for b in blocks if wave and set(b["names"]) & set(wave_names(wave))]
    print("blocks total        : %d" % len(blocks))
    if wave:
        print("blocks in wave '%s' : %d  (%d lines)"
              % (wave, len(picked), sum(b["end"] - b["start"] + 1 for b in picked)))
        for dotted, names in sorted(wave_plan().get(wave, []), key=lambda g: g[0]):
            print("  %-34s %4d names" % (dotted, len(names)))
    if problems:
        print("\nHAZARDS")
        for p in problems:
            print("  " + p)
    uncovered = [b for b in blocks
                 if b["kind"] not in IMPORT_KINDS
                 and any(n != "*" and n not in plan for n in b["names"])]
    covered = [b for b in blocks
               if b["kind"] in IMPORT_KINDS
               or all(n in plan for n in b["names"] if n != "*")]
    print("\nTOP-LEVEL BLOCKS COVERED BY THE PLAN : %d of %d" % (len(covered), len(blocks)))
    print("TOP-LEVEL BLOCKS NOT COVERED         : %d" % len(uncovered))
    for b in uncovered:
        print("  %-10s %5d-%-6d %s" % (b["kind"], b["start"], b["end"], ", ".join(b["names"])))


# ---------------------------------------------------------------- checks

def _builtins():
    import builtins
    names = set(dir(builtins))
    names |= {"__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__"}
    return names


def import_table(tree):
    """binding -> how the original .pyw obtained it. These names are copyable into any
    new module, so they never count as a dependency on the .pyw."""
    tbl = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                tbl[a.asname or a.name.split(".")[0]] = ("import", a.name, None)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                tbl[a.asname or a.name] = ("from", node.module, a.name, a.asname)
    return tbl


def wave_order():
    return list(wave_plan().keys())


def cumulative_names(up_to):
    """Every name planned to have left the .pyw by the end of wave `up_to`."""
    out = set()
    for wave in wave_order():
        out |= set(wave_names(wave))
        if wave == up_to:
            break
    return out


def module_of(dotted_groups, name):
    for dotted, names in dotted_groups:
        if name in names:
            return dotted
    return None

# The coupling a wave check cannot see from the source alone.
#
# The GUI Test Suite drives the program through the entry point's own namespace: it copies the
# .pyw to a .py, imports it as `mod`, and then writes `mod.run_yt_dlp_json = fake` or inspects
# `mod._stream_fetches` or replaces `mod.subprocess` before calling `mod.resolve_stream_url`.
# That only injects behaviour while those names resolve in the module the suite imported. Move
# run_yt_dlp_json into a package module and resolve_stream_url - wherever it lives - starts
# calling the copy in its own module: the patch lands on a name nothing reads, the check keeps
# passing, and it now tests nothing. That is worse than a failing check, so a name the suite
# assigns through mod. stays in the entry point until the suite is re-aimed at the module that
# owns it. A name the suite only reads is safe, because the re-export keeps mod.X working.
_ASSIGNED_RE = re.compile(r"\bmod\.([A-Za-z_][A-Za-z0-9_]*)\s*=[^=]")
_ANY_RE = re.compile(r"\bmod\.([A-Za-z_][A-Za-z0-9_]*)")


def harness_couplings():
    """(assigned, read): names the test suite reaches through the entry point's namespace."""
    assigned, read = set(), set()
    if not os.path.isdir(HARNESS_DIR):
        return assigned, read
    for name in sorted(os.listdir(HARNESS_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(HARNESS_DIR, name), "r", encoding="utf-8") as fh:
            text = fh.read()
        assigned |= set(_ASSIGNED_RE.findall(text))
        read |= set(_ANY_RE.findall(text))
    return assigned, read


def harness_exemptions(wave):
    """Names a wave is allowed to move despite the suite patching them, each with the reason
    and the harness change that makes it safe. Lives in waves.py because it is a decision."""
    sys.path.insert(0, HERE)
    import waves
    return getattr(waves, "HARNESS_EXEMPT", {}).get(wave, {})




def check_wave(wave, verbose=True):
    """The safety rule, enforced: a module moved in `wave` may only reach for stdlib and
    third-party imports, or for names already in a module from this wave or an earlier
    one. Anything else still lives in the .pyw and cannot be imported by a package
    module, so the wave is refused until the plan is re-ordered."""
    text, tree, blocks = parse_blocks()
    plan = plan_map()
    imps = import_table(tree)
    allowed = cumulative_names(wave)
    groups = wave_plan()[wave]
    picked = [b for b in blocks if set(b["names"]) & set(wave_names(wave))]

    blockers = []
    for b in picked:
        own = {n for n in b["names"] if n != "*"}
        target = dotted_of(groups, own)
        for dotted, names in groups:
            if dotted == target:
                own |= set(names)
        reads = free_names(b["node"])
        for name in sorted(reads - own - _builtins()):
            if name in allowed:
                continue                       # already in a moved module: fine
            if name in imps and name not in plan:
                continue                       # stdlib / third-party: copy the import
            blockers.append("%s <- %s : %s" % (target, sorted(own)[0], name))
    assigned, _read = harness_couplings()
    exempt = harness_exemptions(wave)
    for b in picked:
        own = {n for n in b["names"] if n != "*"}
        target = dotted_of(groups, own)
        for name in sorted(own & assigned):
            if name in exempt:
                continue
            blockers.append("%s would take %s out of the entry point, but the test suite "
                            "writes mod.%s to drive the program" % (target, name, name))

    blockers = sorted(set(blockers))
    if verbose:
        if exempt and verbose:
            for name, reason in sorted(exempt.items()):
                print("harness exemption accepted: mod.%s - %s" % (name, reason))
        if blockers:
            print("\nBLOCKED - %d edges point at names that are still in the .pyw, or that the "
                  "test suite reaches through the entry point:" % len(blockers))
            for line in blockers:
                print("  " + line)
        else:
            print("\nOK: every out-edge of wave '%s' points at an import or an earlier wave." % wave)
    return blockers


def cross_module_globals(wave):
    """The hazard a wave check alone cannot see.

    `global SILENCE_TRIM` inside a function writes the global of the module that function
    now lives in. Move the renamer to yt_msd.audio.renamer while SILENCE_TRIM stays in the
    .pyw, and the renamer silently starts writing its own copy while the normalizer keeps
    reading the original - no error, just a setting that stops doing anything. So any
    `global X` in a block that moves is refused unless X lands in the same module.
    """
    text, tree, blocks = parse_blocks()
    plan = plan_map()
    groups = wave_plan()[wave]
    out = []
    for b in blocks:
        if not (set(b["names"]) & set(wave_names(wave))):
            continue
        owner = dotted_of(groups, {n for n in b["names"] if n != "*"})
        for sub in ast.walk(b["node"]):
            if isinstance(sub, ast.Global):
                for name in sub.names:
                    home = plan.get(name, "(still in the .pyw)")
                    if home != owner:
                        out.append("line %5d  %-28s moves to %-26s but declares 'global %s', "
                                   "which lives in %s" % (b["raw_start"], b["names"][0],
                                                           owner, name, home))
    return sorted(set(out))


def dotted_of(groups, own):
    for dotted, names in groups:
        if own & set(names):
            return dotted
    return "?"


# ---------------------------------------------------------------- generate

def build_import_block(tree, needed_stdlib, needed_package):
    """Re-emit the .pyw's own import lines, filtered to what this module actually uses,
    plus the imports that reach names already moved into the package. Reusing the original
    import statements rather than inventing new ones is deliberate: the Python-3.15
    `concurrent.futures.thread` workaround at the top of the .pyw has to survive the move."""
    lines, seen = [], set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                if (a.asname or a.name.split(".")[0]) not in needed_stdlib:
                    continue
                if a.name in seen:
                    continue
                seen.add(a.name)
                lines.append("import %s%s" % (a.name, " as %s" % a.asname if a.asname else ""))
        elif isinstance(node, ast.ImportFrom):
            keep = [a for a in node.names if (a.asname or a.name) in needed_stdlib]
            if not keep:
                continue
            key = (node.module, tuple(sorted(a.name for a in keep)))
            if key in seen:
                continue
            seen.add(key)
            parts = ", ".join("%s as %s" % (a.name, a.asname) if a.asname else a.name
                              for a in keep)
            lines.append("from %s import %s" % (node.module, parts))
    by_module = {}
    for name, dotted in sorted(needed_package.items()):
        by_module.setdefault(dotted, []).append(name)
    for dotted in sorted(by_module):
        lines.append("from %s import %s" % (dotted, ", ".join(sorted(by_module[dotted]))))
    return "\n".join(lines)


def module_path(dotted):
    parts = dotted.split(".")
    assert parts[0] == "yt_msd", dotted
    return os.path.join(PKG_DIR, *parts[1:]) + ".py"


def ensure_package_files(dotted):
    parts = dotted.split(".")[1:]
    for i in range(1, len(parts)):
        d = os.path.join(PKG_DIR, *parts[:i])
        init = os.path.join(d, "__init__.py")
        if not os.path.exists(init):
            os.makedirs(d, exist_ok=True)
            with open(init, "w", encoding="utf-8") as fh:
                fh.write("# Subpackage of the yt-msd GUI package.\n")


def splice_pyw(text, picked, shim_text):
    """Cut the moved blocks out of the .pyw and put the re-export where the first one sat.
    A block's `start` already reaches back over the comments above it, so a gap between two
    consecutive moved blocks travels with them; a gap that belongs to a block that is staying
    is kept."""
    lines = text.splitlines(keepends=True)
    cut = sorted((b["start"], b["end"]) for b in picked)
    first = cut[0][0]
    out = ["".join(lines[:first - 1]), shim_text]
    pos = first - 1          # not 0: the head above already covers everything before the first cut
    for s, e in cut:
        out.append("".join(lines[pos:s - 1]))
        pos = e
    out.append("".join(lines[pos:]))
    return "".join(out)


def add_source_dir_bootstrap(text):
    """Not used. Tried and rejected: the GUI Test Suite runs a *copy* of the .pyw from its
    own folder, so __file__ there points at the copy, not at the source folder, and a
    sys.path bootstrap built from it cannot find the package. The harness states the source
    folder itself instead - it already knows where the .pyw it copies lives."""
    return text


def extract(wave):
    text, tree, blocks = parse_blocks()
    plan = plan_map()
    imps = import_table(tree)
    allowed = cumulative_names(wave)
    groups = wave_plan()[wave]

    blockers = check_wave(wave, verbose=False) + cross_module_globals(wave)
    if blockers:
        print("REFUSED: wave '%s' has %d hazards. Re-plan before extracting." % (wave, len(blockers)))
        for line in blockers:
            print("  " + line)
        return 1

    picked = [b for b in blocks if set(b["names"]) & set(wave_names(wave))]
    per_module = {}
    for b in picked:
        per_module.setdefault(dotted_of(groups, {n for n in b["names"] if n != "*"}), []).append(b)

    wave_bound = set(wave_names(wave))
    os.makedirs(PKG_DIR, exist_ok=True)
    init = os.path.join(PKG_DIR, "__init__.py")
    if not os.path.exists(init):
        with open(init, "w", encoding="utf-8") as fh:
            fh.write('"""The yt-msd GUI package, split out of the single yt-msd-gui.pyw in 3.5."""\n')
    written = []
    for dotted, blist in sorted(per_module.items()):
        bound_here = {n for b in blist for n in b["names"] if n != "*"}
        maybe = set()
        for b in blist:
            maybe |= conditional_names(b["node"])
        maybe &= bound_here
        reads = set()
        for b in blist:
            reads |= free_names(b["node"])
        needed_stdlib = {n for n in reads - bound_here - wave_bound if n in imps and n not in plan}
        needed_package = {n: plan[n] for n in reads - bound_here
                          if n in wave_bound or n in allowed}
        body = [MODULE_HEADER.format(dotted=dotted)]
        imports = build_import_block(tree, needed_stdlib, needed_package)
        if imports:
            body.append(imports + "\n\n")
        for b in sorted(blist, key=lambda x: x["start"]):
            body.append(block_text(text, b).rstrip("\n") + "\n\n")
        path = module_path(dotted)
        ensure_package_files(dotted)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(body).rstrip("\n") + "\n")
        written.append((dotted, path,
                        sorted(bound_here - maybe), sorted(maybe)))

    shim = ["# These names moved out of this file during the 3.5 modularisation (wave %s) and are\n"
            "# re-exported here so the entry point keeps every name it has always had while the\n"
            "# split proceeds. The final wave replaces this with the package's own entry point.\n"
            % wave]
    for dotted, _p, always, maybe in written:
        shim.append("from %s import (\n" % dotted)
        for name in sorted(always):
            shim.append("    %s,\n" % name)
        shim.append(")\n")
        if maybe:
            parent, leaf = dotted.rsplit(".", 1)
            alias = "_%s_mod" % leaf
            shim.append("from %s import %s as %s\n" % (parent, leaf, alias))
            shim.append("# %s only ever exists on a machine where the guarded import above failed,\n"
                        "# and the program reads it with getattr(..., default) for exactly that\n"
                        "# reason, so it is forwarded the same way rather than demanded here.\n"
                        % ", ".join(sorted(maybe)))
            for name in sorted(maybe):
                shim.append("if hasattr(%s, %r):\n" % (alias, name))
                shim.append("    %s = %s.%s\n" % (name, alias, name))

    new_text = add_source_dir_bootstrap(splice_pyw(text, picked, "".join(shim)))
    with open(PYW, "w", encoding="utf-8") as fh:
        fh.write(new_text)

    print("extracted wave '%s' -> %d modules" % (wave, len(written)))
    for dotted, path, always, maybe in written:
        note = "" if not maybe else "  (%s forwarded conditionally)" % ", ".join(maybe)
        print("  %-34s %3d names  %s%s" % (dotted, len(always) + len(maybe),
                                           os.path.relpath(path, ROOT), note))
    print("yt-msd-gui.pyw is now %d lines (was %d)" % (len(new_text.splitlines()), len(text.splitlines())))
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print("usage: python splitlib.py analyze [wave]\n"
              "       python splitlib.py extract <wave>")
        return 0
    if argv[1] == "analyze":
        analyze(argv[2] if len(argv) > 2 else None)
        return 0
    if argv[1] == "extract":
        return extract(argv[2])
    print("unknown command: %s" % argv[1])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

    os.makedirs(os.path.dirname(module_path(dotted)), exist_ok=True)


