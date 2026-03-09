"""Tests for the vibe CLI."""

from pathlib import Path

from click.testing import CliRunner

from vibe.cli import _flatten_keys, load_context, main


def _make_project(tmp_path, context=None, templates=None):
    """Create a minimal vibe project in tmp_path."""
    ctx_dir = tmp_path / "context"
    tmpl_dir = tmp_path / "templates"
    ctx_dir.mkdir()
    tmpl_dir.mkdir()
    for name, content in (context or {}).items():
        p = ctx_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for name, content in (templates or {}).items():
        p = tmpl_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def _invoke(*args, root):
    runner = CliRunner()
    return runner.invoke(main, list(args), env={"VIBE_ROOT": str(root)})


class TestLoadContext:
    def test_flat(self, tmp_path):
        ctx_dir = tmp_path / "context"
        ctx_dir.mkdir()
        (ctx_dir / "role.j2").write_text("engineer")
        (ctx_dir / "team.j2").write_text("sling")

        result = load_context(ctx_dir)
        assert result == {"role": "engineer", "team": "sling"}

    def test_nested(self, tmp_path):
        ctx_dir = tmp_path / "context"
        (ctx_dir / "company").mkdir(parents=True)
        (ctx_dir / "company" / "name.j2").write_text("Toast")
        (ctx_dir / "company" / "team.j2").write_text("Sling")
        (ctx_dir / "role.j2").write_text("engineer")

        result = load_context(ctx_dir)
        assert result == {
            "role": "engineer",
            "company": {"name": "Toast", "team": "Sling"},
        }

    def test_strips_whitespace(self, tmp_path):
        ctx_dir = tmp_path / "context"
        ctx_dir.mkdir()
        (ctx_dir / "name.j2").write_text("  hello  \n\n")

        result = load_context(ctx_dir)
        assert result == {"name": "hello"}

    def test_empty_dir(self, tmp_path):
        ctx_dir = tmp_path / "context"
        ctx_dir.mkdir()
        assert load_context(ctx_dir) == {}


class TestFlattenKeys:
    def test_flat(self):
        assert _flatten_keys({"a": 1, "b": 2}) == ["a", "b"]

    def test_nested(self):
        assert _flatten_keys({"a": {"b": 1, "c": 2}, "d": 3}) == [
            "a.b",
            "a.c",
            "d",
        ]

    def test_deeply_nested(self):
        assert _flatten_keys({"a": {"b": {"c": 1}}}) == ["a.b.c"]

    def test_empty(self):
        assert _flatten_keys({}) == []


class TestRenderTemplate:
    def test_single_template(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"name.j2": "world"},
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello world"

    def test_nested_context_in_template(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"company/name.j2": "Toast"},
            templates={"greet.j2": "hello {{ company.name }}"},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello Toast"

    def test_unknown_template(self, tmp_path):
        root = _make_project(tmp_path, templates={"a.j2": "hi"})
        result = _invoke("nope", root=root)
        assert result.exit_code != 0
        assert "Unknown template" in result.output

    def test_no_args(self, tmp_path):
        root = _make_project(tmp_path, templates={"a.j2": "hi"})
        result = _invoke(root=root)
        assert result.exit_code != 0



class TestList:
    def test_lists_templates_and_context(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"role.j2": "eng", "company/name.j2": "Toast"},
            templates={"greet.j2": "hi", "slack/summary.j2": "bye"},
        )
        result = _invoke("--list", root=root)
        assert result.exit_code == 0
        assert "greet" in result.output
        assert "slack/summary" in result.output
        assert "company.name" in result.output
        assert "role" in result.output


class TestOutFile:
    def test_writes_to_file(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"x.j2": "world"},
            templates={"hi.j2": "hello {{ x }}"},
        )
        out = tmp_path / "out.txt"
        result = _invoke("hi", "--out", str(out), root=root)
        assert result.exit_code == 0
        assert out.read_text().strip() == "hello world"


class TestNestedTemplates:
    def test_render_nested_template(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"name.j2": "world"},
            templates={"sub/greet.j2": "hello {{ name }}"},
        )
        result = _invoke("sub/greet", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello world"
