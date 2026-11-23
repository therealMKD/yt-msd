"""Wave 5h: drop the names the entry point no longer reads.

The split moved code out a wave at a time, and the .pyw imported every moved name back so that
nothing - the file itself or the GUI Test Suite - lost a name it could reach. With the split
closed, that blanket promise has stopped earning its keep: 117 of the 354 names the entry point
binds from its import layer are read by nobody.

This removes exactly those, and refuses to guess. A name is kept when

  - the entry point reads it or binds it anywhere in its own text, or
  - the suite reaches it as mod.<name> (splitlib.harness_couplings, read from the suite's syntax),
    or
  - the suite names it in a string, which is how harness_seam.patch() and getattr(mod, "<name>")
    reach it.

Comments are never touched: what each re-export group is for is a decision a human reviews, not a
side effect of a prune. Import style is preserved per statement - single-line stays single-line,
one-name-per-line parenthesised stays that way, wrapped parenthesised stays wrapped - so the diff
is the removals and nothing else.

  python prune_reexports.py           report what would go, change nothing
  python prune_reexports.py --apply   rewrite the .pyw
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import splitlib  # noqa: E402

WIDTH = 100


def main():
    apply = "--apply" in sys.argv
    text = splitlib.read_pyw()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)

    status = splitlib.import_layer_status()      # the same rule analyze() reports

    def wanted(binding):
        return bool(status.get(binding, ""))

    edits = []          # (lineno, end_lineno, new_text, removed_names)
    dropped_names = []
    dropped_statements = 0
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        kept = [a for a in node.names if wanted(a.asname or a.name.split(".")[0])]
        if len(kept) == len(node.names):
            continue
        gone = [a.asname or a.name.split(".")[0]
                for a in node.names if a not in kept]
        dropped_names.extend(gone)
        if not kept:
            dropped_statements += 1
            edits.append((node.lineno, node.end_lineno, "", gone))
            continue
        original = [lines[i - 1] for i in range(node.lineno, node.end_lineno + 1)]
        head = ("from %s%s import " % ("." * node.level, node.module)
                if isinstance(node, ast.ImportFrom) else "import ")
        names = [("%s as %s" % (a.name, a.asname) if a.asname else a.name) for a in kept]
        if len(original) == 1:
            new = head + ", ".join(names) + "\n"
        else:
            indent = original[1][:len(original[1]) - len(original[1].lstrip())]
            packed = len(original[0].split("import")[-1].replace("(", "").strip().split(",")) > 1
            groups, cur = [], ""
            for name in names:
                candidate = (cur + ", " + name) if cur else name
                if cur and len(head) + 1 + len(candidate) > WIDTH:
                    groups.append(cur)
                    cur = name
                else:
                    cur = candidate
            if cur:
                groups.append(cur)
            if packed:
                new = head + "(" + groups[0]
                for group in groups[1:]:
                    new += ",\n" + indent + group
                new += ")\n"
            else:
                new = head + "(\n" + "".join("    %s,\n" % n for n in names) + ")\n"
        edits.append((node.lineno, node.end_lineno, new, gone))

    print("names nothing reads : %d across %d statements (%d statements go entirely)"
          % (len(dropped_names), len(edits), dropped_statements))
    for lineno, _end, _new, gone in edits:
        print("  line %5d  -%s" % (lineno, ", ".join(gone)))

    if not apply:
        print("\nno change made: re-run with --apply")
        return 0

    for lineno, end, new, _gone in sorted(edits, reverse=True):
        lines[lineno - 1:end] = [new] if new else []
    updated = "".join(lines)
    ast.parse(updated)                      # the result must still be valid Python
    with open(splitlib.PYW, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print("\napplied: %d lines -> %d lines"
          % (len(text.splitlines()), updated.count("\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
