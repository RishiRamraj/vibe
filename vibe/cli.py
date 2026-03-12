"""Vibe CLI - render prompt templates with shared context."""

import os
from pathlib import Path

import click
import jinja2
import jinja2.meta


# Resolve the project root, defaulting to cwd. Override with VIBE_ROOT env var.
def get_root() -> Path:
    return Path(os.environ.get("VIBE_ROOT", "."))


# Recursively flatten a nested dict into dot-separated key paths,
# e.g. {"a": {"b": 1}} -> ["a.b"]. Used to display context variables.
def _flatten_keys(d: dict, prefix: str = "") -> list[str]:
    """Flatten nested dict keys into dot-separated paths."""
    keys = []
    for k, v in sorted(d.items()):
        full = f"{prefix}{k}"
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, f"{full}."))
        else:
            keys.append(full)
    return keys


# Build a nested dict of context variables from .j2 files under context/.
# Directory structure maps to dot-separated template variable names:
# context/company/name.j2 becomes {{ company.name }}.
def load_context(context_dir: Path) -> dict:
    """Load all .j2 files from context/ into nested dicts.

    context/role.j2                -> {{ role }}
    context/company/priorities.j2  -> {{ company.priorities }}
    """
    context: dict = {}
    for path in context_dir.rglob("*.j2"):
        parts = list(path.relative_to(context_dir).with_suffix("").parts)

        # Walk into nested dicts, creating intermediate levels as needed.
        node = context
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = path.read_text().strip()
    return context


# Shell completion callback — returns template names matching the user's input.
def complete_template(ctx, param, incomplete):
    """Provide shell completion for template names."""
    root = get_root()
    templates_dir = root / "templates"
    if not templates_dir.is_dir():
        return []
    names = sorted(
        str(p.relative_to(templates_dir).with_suffix(""))
        for p in templates_dir.rglob("*.j2")
    )
    return [n for n in names if n.startswith(incomplete)]


def _set_nested(d: dict, key: str, value: str) -> None:
    """Set a value in a nested dict using dot-separated key path.

    _set_nested(d, "company.name", "Acme") sets d["company"]["name"].
    """
    parts = key.split(".")
    node = d
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _parse_param(value: str) -> tuple[str, str]:
    """Parse a 'key=value' string, raising click.BadParameter on bad format."""
    if "=" not in value:
        raise click.BadParameter(
            f"Invalid parameter '{value}'. Expected format: key=value"
        )
    k, _, v = value.partition("=")
    if not k:
        raise click.BadParameter(f"Invalid parameter '{value}'. Key must not be empty.")
    return k, v


def _parse_extra_args(args: list[str]) -> dict[str, str]:
    """Parse extra CLI args like --key value or --key=value into a dict."""
    result: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if not arg.startswith("--"):
            raise click.UsageError(f"Unexpected argument '{arg}'.")
        if "=" in arg:
            key, _, value = arg[2:].partition("=")
            result[key] = value
            i += 1
        elif i + 1 < len(args):
            result[arg[2:]] = args[i + 1]
            i += 2
        else:
            raise click.UsageError(f"Option '{arg}' requires a value.")
    return result


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("template", required=False, shell_complete=complete_template)
@click.option(
    "--list", "-l", "list_templates", is_flag=True, help="List available templates."
)
@click.option(
    "--out", "-o", type=click.Path(), help="Write output to file instead of stdout."
)
@click.option(
    "--param",
    "-p",
    "params",
    multiple=True,
    help="Set a template variable as key=value. "
    "Dot notation supported (e.g. -p company.name=Acme).",
)
@click.pass_context
def main(
    ctx: click.Context,
    template: str | None,
    list_templates: bool,
    out: str | None,
    params: tuple[str, ...],
):
    """Render prompt templates with shared context.

    TEMPLATE is the name of a template to render (without .j2 extension).
    Provide template variables as --name value or -p key=value.
    """
    root = get_root()
    templates_dir = root / "templates"
    context_dir = root / "context"

    # Set up Jinja2 with strict undefined to catch missing variables early.
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    context = load_context(context_dir)

    # Merge -p key=value params into context.
    for raw in params:
        key, value = _parse_param(raw)
        _set_nested(context, key, value)

    # Merge --key value extra args into context.
    for key, value in _parse_extra_args(ctx.args).items():
        _set_nested(context, key, value)

    available = sorted(templates_dir.rglob("*.j2"))

    # --list: print all template names and context variable paths, then exit.
    if list_templates:
        click.echo("Templates:")
        for p in available:
            rel = p.relative_to(templates_dir).with_suffix("")
            click.echo(f"  {rel}")
        click.echo("\nContext variables:")
        for key in _flatten_keys(context):
            click.echo(f"  {key}")
        return

    def rel_name(p: Path) -> str:
        return str(p.relative_to(templates_dir).with_suffix(""))

    # Render the named template, validating it exists first.
    if template:
        names = {rel_name(p) for p in available}
        if template not in names:
            raise click.UsageError(
                f"Unknown template '{template}'. Available: {', '.join(sorted(names))}"
            )
        tmpl = env.get_template(f"{template}.j2")
        try:
            output = tmpl.render(context)
        except jinja2.UndefinedError as exc:
            template_src = (templates_dir / f"{template}.j2").read_text()
            ast = env.parse(template_src)
            required = sorted(jinja2.meta.find_undeclared_variables(ast))
            provided = sorted(_flatten_keys(context))
            missing = sorted(set(required) - set(provided))

            lines = template_src.splitlines()
            preview = "\n".join(lines[:3])
            if len(lines) > 3:
                preview += "\n..."

            parts = [
                f"Error: {exc.message}",
                f"\nTemplate: {template}",
                f"\nRequired variables: {', '.join(required)}",
                f"Provided variables: {', '.join(provided) or '(none)'}",
                f"Missing variables:  {', '.join(missing)}",
                f"\nTemplate content:\n{preview}",
            ]
            raise click.UsageError("\n".join(parts)) from None
    else:
        raise click.UsageError("Provide a TEMPLATE name or --list.")

    # Write rendered output to a file or stdout.
    if out:
        Path(out).write_text(output)
        click.echo(f"Written to {out}")
    else:
        click.echo(output)
