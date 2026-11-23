"""Wave 6: the methods that outgrew the entry point, lifted into mixin modules.

The split closed at wave 5h with every top-level block moved out except MainApp - and that left
the class holding five methods of 150 lines or more, 1,618 of the 6,882 lines in the file. This
tool moves those methods and nothing else. The class keeps its name, its signals, its attributes
and every method that fits in a screenful; each long method goes to a module of its own as a
mixin the class inherits.

A mixin is what makes the move a cut-and-paste rather than a rewrite:

  - the body is untouched, so `self` still means the window and a zero-argument `super()` keeps
    resolving exactly as it did: the method is still written inside a class, only a different one;
  - nothing is re-indented. A method leaves MainApp's body and enters another class body at the
    same depth, so every line is byte for byte what it was - including the 207 lines inside
    apply_theme's triple-quoted stylesheet, whose leading spaces are part of what gets painted;
  - no wrapper is left behind, so the entry point gains no boilerplate - it gains one base class
    per module and a comment saying what each one is for.

The rule that made waves 1-5 safe still decides what may move: a lifted method may only reach for
stdlib and third-party imports, or for names already moved into a module. splitlib.free_names()
answers that per method, and a method with an out-edge still pointing at the .pyw is refused.
A `global` in a lifted method is refused too, for the reason cross_module_globals() spells out.

  python lift_methods.py check 6      what would move, and whether anything blocks it
  python lift_methods.py lift 6       move it, write the modules, rewrite the class line

LIFTS lives in waves.py next to WAVES because it is the part a human reviews.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import splitlib  # noqa: E402


def _plan(wave):
    import waves
    if wave not in getattr(waves, "LIFTS", {}):
        raise SystemExit("waves.py has no LIFTS entry for wave %r. The plan is the file that "
                         "says what moves; write it first." % wave)
    return waves.LIFTS[wave]


def _main_class(tree):
    return next(n for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == "MainApp")


def _method(main, name):
    for node in main.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise SystemExit("no method %s on MainApp - the plan and the file disagree" % name)


def _span_with_comments(lines, node):
    """The method plus the comment lines sitting directly above it at its own indent.

    The same rule parse_blocks() uses for top-level blocks: an explanation travels with the code
    it describes instead of being stranded where the code used to be.
    """
    start = node.lineno
    indent = len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())
    while start - 2 >= 0:
        raw = lines[start - 2]
        if not raw.strip().startswith("#"):
            break
        if len(raw) - len(raw.lstrip()) != indent:
            break
        start -= 1
    return start, node.end_lineno


def _literal_interiors(node):
    """Lines inside a multi-line string literal, for reporting.

    Dedenting those would not be a formatting change, it would change the string: apply_theme
    builds a 207-line stylesheet in a triple-quoted f-string, and its leading spaces are part of
    what gets painted. Nothing here is dedented - a method moves from one class body to another at
    the same depth - so the check exists to prove that, and to say so in the report.
    """
    interior = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and "\n" in sub.value:
            interior.update(range(sub.lineno + 1, sub.end_lineno + 1))
    return interior


def _moved(lines, start, end):
    """The lines of one method, exactly as they were written.

    The mixin is the whole point of this wave: a method leaves MainApp's body and enters another
    class body at the same indentation, so there is nothing to re-indent and nothing to rewrite.
    `self` still names the instance, a zero-argument `super()` still resolves through the class,
    and verify.py can compare the two files line for line and find no difference at all.
    """
    return [lines[i] for i in range(start - 1, end)]


def _edges(tree, nodes):
    """(names to copy as imports, names to import from the package, names that block the move)."""
    imps = splitlib.import_table(tree)
    plan = splitlib.plan_map()
    stdlib, package, blocked = set(), {}, []
    for node in nodes:
        for name in splitlib.free_names(node):
            if name in splitlib._builtins():
                continue
            if name in plan:
                package[name] = plan[name]
            elif name in imps:
                stdlib.add(name)
            else:
                blocked.append(name)
    return stdlib, package, sorted(set(blocked))


def _globals(nodes):
    found = []
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Global):
                found.extend(sub.names)
    return sorted(set(found))

def report(wave):
    """What would move, what it would need, and what would stop it - without writing anything."""
    text = splitlib.read_pyw()
    tree = ast.parse(text)
    main = _main_class(tree)
    lines = text.splitlines(keepends=True)
    groups = _plan(wave)
    print("wave %s: %d modules, %d methods\n"
          % (wave, len(groups), sum(len(g[2]) for g in groups)))
    problems = []
    for dotted, mixin, names in groups:
        nodes = [_method(main, n) for n in names]
        spans = [_span_with_comments(lines, n) for n in nodes]
        size = sum(e - s + 1 for s, e in spans)
        stdlib, package, blocked = _edges(tree, nodes)
        declared = _globals(nodes)
        keep = set()
        for node in nodes:
            keep |= _literal_interiors(node)
        print("  %-28s %s" % (dotted, mixin))
        print("      methods : %s" % ", ".join(names))
        print("      lines   : %d  (%s)" % (size, ", ".join("%d-%d" % sp for sp in spans)))
        print("      imports : %s" % ", ".join(sorted(stdlib)))
        print("      package : %s" % ", ".join("%s from %s" % (k, v)
                                               for k, v in sorted(package.items())))
        if keep:
            print("      lines inside a multi-line string : %d, left exactly as written" % len(keep))
        if blocked:
            problems.append("%s still reads %s, which is in the .pyw" % (dotted, ", ".join(blocked)))
            print("      BLOCKED : %s" % ", ".join(blocked))
        if declared:
            problems.append("%s declares `global %s`" % (dotted, ", ".join(declared)))
            print("      global  : %s" % ", ".join(declared))
    taken = {n for _d, _m, names in groups for n in names}
    decided = splitlib.left_by_decision()
    for name in sorted(taken & set(decided)):
        problems.append("the plan lifts %s, which LEFT_BY_DECISION has closed out: %s  (to reopen "
                        "it, delete LEFT_BY_DECISION[\"%s\"] from waves.py)" % (name, decided[name], name))
    if problems:
        print("\nBLOCKED - %d problems:" % len(problems))
        for line in problems:
            print("  " + line)
    else:
        print("\nOK: every out-edge of every lifted method points at an import or a moved module.")
    return problems


MIXIN_NOTE = (
    "#\n"
    "# A mixin, not a standalone module: MainApp inherits from this class, so what is written here\n"
    "# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class\n"
    "# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the\n"
    "# program were added, and the inside of a multi-line string kept the indentation it was written\n"
    "# with, because changing it would change what the program shows rather than where it is kept.\n"
)

def lift(wave):
    problems = report(wave)
    if problems:
        print("\nREFUSED: fix the plan before anything is written.")
        return 1

    groups = _plan(wave)
    for dotted, _mixin, _names in groups:
        if os.path.exists(splitlib.module_path(dotted)):
            print("REFUSED: %s already exists. This tool writes whole modules; it does not append "
                  "to one that has already been extracted." % dotted)
            return 1

    text = splitlib.read_pyw()
    tree = ast.parse(text)
    main = _main_class(tree)
    lines = text.splitlines(keepends=True)

    per_module = {}
    spans = []
    for dotted, mixin, names in groups:
        nodes = [_method(main, n) for n in names]
        per_module[(dotted, mixin)] = nodes
        for node in nodes:
            spans.append(_span_with_comments(lines, node))
    spans.sort()
    class_line = main.lineno

    os.makedirs(splitlib.PKG_DIR, exist_ok=True)
    written = []
    for (dotted, mixin), nodes in sorted(per_module.items()):
        stdlib, package, _blocked = _edges(tree, nodes)
        body = [splitlib.MODULE_HEADER.format(dotted=dotted), MIXIN_NOTE, "\n"]
        imports = splitlib.build_import_block(tree, stdlib, package)
        if imports:
            body.append(imports + "\n\n")
        body.append("class %s:\n" % mixin)
        for node in sorted(nodes, key=lambda n: n.lineno):
            start, end = _span_with_comments(lines, node)
            body.append("".join(_moved(lines, start, end)).rstrip("\n") + "\n\n")
        path = splitlib.module_path(dotted)
        splitlib.ensure_package_files(dotted)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(body).rstrip("\n") + "\n")
        written.append((dotted, mixin, path, len(nodes)))

    # The entry point: cut the methods out, name the bases, import the mixins above the class.
    cut = set()
    for start, end in spans:
        cut.update(range(start, end + 1))
    header = ["# Wave 6: every method below 150 lines stayed with the class. These five did not, and\n"
              "# each now lives in a module of its own that MainApp inherits below. Listed in the\n"
              "# order they are read in this file, which is not the order they run in.\n"]
    for dotted, mixin, _names in groups:
        header.append("from %s import %s\n" % (dotted, mixin))
    bases = ",\n           ".join(mixin for _d, mixin, _n in groups)
    emitted_blank = False
    new_lines = []
    for i, raw in enumerate(lines, start=1):
        if i in cut:
            continue
        if not raw.strip():
            if emitted_blank:
                continue                      # a cut leaves two blank lines where one divided them
            emitted_blank = True
        else:
            emitted_blank = False
        if i == class_line:
            new_lines.extend(header)
            new_lines.append("class MainApp(%s,\n           QMainWindow):\n" % bases)
            continue
        new_lines.append(raw)
    new_text = "".join(new_lines)
    with open(splitlib.PYW, "w", encoding="utf-8") as fh:
        fh.write(new_text)

    print("\nlifted wave %s -> %d modules" % (wave, len(written)))
    for dotted, mixin, path, n in written:
        print("  %-28s %-22s %3d methods  %s"
              % (dotted, mixin, n, os.path.relpath(path, splitlib.ROOT)))
    print("MainApp now inherits: %s, QMainWindow" % bases.replace("\n           ", " "))
    print("yt-msd-gui.pyw is now %d lines (was %d); %d lines lifted out"
          % (len(new_text.splitlines()), len(text.splitlines()),
             sum(e - s + 1 for s, e in spans)))
    return 0


def main(argv):
    if len(argv) < 3 or argv[1] not in ("check", "lift"):
        print("usage: python lift_methods.py check <wave>\n"
              "       python lift_methods.py lift <wave>")
        return 1
    if argv[1] == "check":
        return 1 if report(argv[2]) else 0
    return lift(argv[2])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
