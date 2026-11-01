# Dov-Bot shac checks: formatting, linting, typechecking, policy, and public ArtBOT API contract locking.
# Run `shac test` to verify Starlark rules and `shac check` to enforce them.

load("//checks/api_contract.star", "register_api_contract_checks")
load("//checks/policy.star", "register_policy_checks")

def _rel(ctx, path):
    """Return path relative to the repository root."""
    root = ctx.scm.root + "/"
    if path.startswith(root):
        return path[len(root):]
    return path

def ruff_format(ctx):
    """Enforce Python formatting with ruff format."""
    for path in ctx.scm.affected_files(glob = "*.py"):
        original = str(ctx.io.read_file(path))
        res = ctx.os.exec(
            ["ruff", "format", "--no-cache", "--quiet", "--stdin-filename", path, "-"],
            stdin = original,
            raise_on_failure = False,
        ).wait()
        if res.retcode != 0:
            ctx.emit.finding(
                level = "error",
                filepath = path,
                message = "ruff format failed: %s" % (res.stderr.strip() or res.stdout.strip())[:400],
            )
        elif res.stdout != original:
            ctx.emit.finding(
                level = "error",
                filepath = path,
                message = "File is not formatted with ruff. Run `shac fmt` or `ruff format`.",
                replacements = [res.stdout],
            )

def ruff_lint(ctx):
    """Enforce Python lint rules with ruff check."""
    files = list(ctx.scm.affected_files(glob = "*.py"))
    if not files:
        return
    res = ctx.os.exec(
        ["ruff", "check", "--no-cache", "--output-format=json"] + files,
        ok_retcodes = [0, 1],
    ).wait()
    for d in json.decode(res.stdout):
        ctx.emit.finding(
            level = "error",
            filepath = _rel(ctx, d["filename"]),
            line = d["location"]["row"],
            col = d["location"]["column"],
            message = "%s (%s)" % (d["message"], d["code"]),
        )

def mypy_typecheck(ctx):
    """Enforce strict Python type checking with mypy."""
    files = list(ctx.scm.affected_files(glob = "*.py"))
    if not files:
        return
    res = ctx.os.exec(
        ["mypy", "--cache-dir=/dev/null", "--strict", "src", "tests"],
        ok_retcodes = [0, 1],
    ).wait()
    if res.retcode != 0:
        ctx.emit.finding(
            level = "error",
            message = "mypy strict typecheck failed:\n%s" % res.stdout[:1000],
        )

shac.register_check(shac.check(ruff_format, formatter = True))
shac.register_check(ruff_lint)
shac.register_check(mypy_typecheck)
register_policy_checks()
register_api_contract_checks()
