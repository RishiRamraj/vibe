# vibe

A CLI tool to template and generate prompts for agents.

## Installation

```bash
pip install -e /path/to/vibe
```

## Usage

Vibe looks for `templates/` and `context/` directories relative to the current
directory. Override this with the `VIBE_ROOT` environment variable.

### Directory structure

```
my-prompts/
├── context/
│   ├── role.j2
│   ├── priorities.j2
│   └── company/
│       └── name.j2          # available as {{ company.name }}
└── templates/
    ├── attention.j2
    └── slack/
        └── summary.j2       # rendered with: vibe slack/summary
```

Context files (`.j2`) are loaded as template variables. Subdirectories become
dot-separated names: `context/company/name.j2` → `{{ company.name }}`.

### Commands

```bash
# Render a single template
vibe attention

# Render all templates
vibe --all

# List available templates and context variables
vibe --list

# Write output to a file
vibe attention --out /tmp/prompt.md
```

### Environment variables

| Variable    | Default | Description                              |
|-------------|---------|------------------------------------------|
| `VIBE_ROOT` | `.`     | Root directory containing templates and context |

## Shell completion

### Bash

Add to `~/.bashrc`:

```bash
eval "$(_VIBE_COMPLETE=bash_source vibe)"
```

### Zsh

Add to `~/.zshrc`:

```bash
eval "$(_VIBE_COMPLETE=zsh_source vibe)"
```

### Fish

Add to `~/.config/fish/completions/vibe.fish`:

```fish
_VIBE_COMPLETE=fish_source vibe | source
```

After adding the completion line, restart your shell or source the config file.

## License

MIT
