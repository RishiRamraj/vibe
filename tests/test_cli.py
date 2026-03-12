"""Tests for the vibe CLI."""

import click
from click.testing import CliRunner

from vibe.cli import (
    _flatten_keys,
    _parse_extra_args,
    _parse_param,
    _set_nested,
    load_context,
    main,
)


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


class TestSetNested:
    def test_flat_key(self):
        d = {}
        _set_nested(d, "name", "Alice")
        assert d == {"name": "Alice"}

    def test_dotted_key(self):
        d = {}
        _set_nested(d, "company.name", "Acme")
        assert d == {"company": {"name": "Acme"}}

    def test_deep_key(self):
        d = {}
        _set_nested(d, "a.b.c", "deep")
        assert d == {"a": {"b": {"c": "deep"}}}

    def test_override_existing(self):
        d = {"name": "old"}
        _set_nested(d, "name", "new")
        assert d == {"name": "new"}

    def test_merge_into_existing(self):
        d = {"company": {"team": "Sling"}}
        _set_nested(d, "company.name", "Toast")
        assert d == {"company": {"team": "Sling", "name": "Toast"}}


class TestParseParam:
    def test_simple(self):
        assert _parse_param("name=Alice") == ("name", "Alice")

    def test_value_with_equals(self):
        assert _parse_param("expr=a=b") == ("expr", "a=b")

    def test_empty_value(self):
        assert _parse_param("name=") == ("name", "")

    def test_no_equals(self):
        import pytest

        with pytest.raises(click.exceptions.BadParameter):
            _parse_param("noequals")

    def test_empty_key(self):
        import pytest

        with pytest.raises(click.exceptions.BadParameter):
            _parse_param("=value")


class TestParseExtraArgs:
    def test_key_value_pairs(self):
        assert _parse_extra_args(["--name", "Alice", "--role", "eng"]) == {
            "name": "Alice",
            "role": "eng",
        }

    def test_equals_syntax(self):
        assert _parse_extra_args(["--name=Alice"]) == {"name": "Alice"}

    def test_mixed_syntax(self):
        assert _parse_extra_args(["--name", "Alice", "--role=eng"]) == {
            "name": "Alice",
            "role": "eng",
        }

    def test_empty(self):
        assert _parse_extra_args([]) == {}

    def test_missing_value(self):
        import pytest

        with pytest.raises(click.UsageError):
            _parse_extra_args(["--name"])

    def test_unexpected_arg(self):
        import pytest

        with pytest.raises(click.UsageError):
            _parse_extra_args(["notanoption"])


class TestParams:
    def test_param_injected(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", "-p", "name=World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello World"

    def test_param_overrides_context(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"name.j2": "FromFile"},
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", "-p", "name=FromCLI", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello FromCLI"

    def test_nested_param(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ company.name }}"},
        )
        result = _invoke("greet", "-p", "company.name=Acme", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello Acme"

    def test_multiple_params(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "{{ greeting }} {{ name }}"},
        )
        result = _invoke("greet", "-p", "greeting=hi", "-p", "name=World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hi World"

    def test_invalid_param_format(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello"},
        )
        result = _invoke("greet", "-p", "noequals", root=root)
        assert result.exit_code != 0


class TestNamedParams:
    def test_named_param(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", "--name", "World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello World"

    def test_named_param_equals(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", "--name=World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello World"

    def test_named_param_overrides_context(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"name.j2": "FromFile"},
            templates={"greet.j2": "hello {{ name }}"},
        )
        result = _invoke("greet", "--name", "FromCLI", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello FromCLI"

    def test_multiple_named_params(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "{{ greeting }} {{ name }}"},
        )
        result = _invoke("greet", "--greeting", "hi", "--name", "World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hi World"

    def test_dotted_named_param(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ company.name }}"},
        )
        result = _invoke("greet", "--company.name", "Acme", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello Acme"

    def test_dotted_named_param_equals(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ company.name }}"},
        )
        result = _invoke("greet", "--company.name=Acme", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hello Acme"

    def test_mixed_named_and_p_params(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "{{ greeting }} {{ name }}"},
        )
        result = _invoke("greet", "-p", "greeting=hi", "--name", "World", root=root)
        assert result.exit_code == 0
        assert result.output.strip() == "hi World"


class TestTemplateErrors:
    def test_missing_variable_shows_friendly_error(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "hello {{ name }} from {{ place }}"},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code != 0
        assert "name" in result.output
        assert "place" in result.output
        assert "Template: greet" in result.output
        assert "Missing variables:" in result.output
        assert "Required variables:" in result.output

    def test_partial_context_shows_missing(self, tmp_path):
        root = _make_project(
            tmp_path,
            context={"name.j2": "World"},
            templates={"greet.j2": "{{ name }} {{ missing_var }}"},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code != 0
        assert "missing_var" in result.output
        assert "Provided variables:" in result.output
        assert "name" in result.output

    def test_error_includes_template_content(self, tmp_path):
        template_content = "hello {{ name }}"
        root = _make_project(
            tmp_path,
            templates={"greet.j2": template_content},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code != 0
        assert template_content in result.output

    def test_template_truncated_to_three_lines(self, tmp_path):
        lines = ["line1 {{ name }}", "line2", "line3", "line4", "line5"]
        root = _make_project(
            tmp_path,
            templates={"long.j2": "\n".join(lines)},
        )
        result = _invoke("long", root=root)
        assert result.exit_code != 0
        assert "line1" in result.output
        assert "line2" in result.output
        assert "line3" in result.output
        assert "line4" not in result.output
        assert "line5" not in result.output
        assert "..." in result.output

    def test_template_no_ellipsis_when_short(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"short.j2": "{{ a }}\n{{ b }}\n{{ c }}"},
        )
        result = _invoke("short", root=root)
        assert result.exit_code != 0
        assert "..." not in result.output

    def test_nested_var_error(self, tmp_path):
        root = _make_project(
            tmp_path,
            templates={"greet.j2": "{{ company.name }}"},
        )
        result = _invoke("greet", root=root)
        assert result.exit_code != 0
        assert "company" in result.output
        assert "Template: greet" in result.output


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
