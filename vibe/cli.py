"""Vibe CLI - render prompt templates with shared context."""

import os
from pathlib import Path

import click
import jinja2


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


@click.command()
@click.argument("template", required=False, shell_complete=complete_template)
@click.option(
    "--list", "-l", "list_templates", is_flag=True, help="List available templates."
)
@click.option(
    "--out", "-o", type=click.Path(), help="Write output to file instead of stdout."
)
def main(template: str | None, list_templates: bool, out: str | None):
    """Render prompt templates with shared context.

    TEMPLATE is the name of a template to render (without .j2 extension).
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
        output = tmpl.render(context)
    else:
        raise click.UsageError("Provide a TEMPLATE name or --list.")

    # Write rendered output to a file or stdout.
    if out:
        Path(out).write_text(output)
        click.echo(f"Written to {out}")
    else:
        click.echo(output)
