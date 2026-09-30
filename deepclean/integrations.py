"""Install optional Deep Clean integrations without external dependencies."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from deepclean import __version__


def install_claude_command(target=None):
    target = Path(target or (Path.home() / ".claude" / "commands" / "deepclean.md"))
    target.parent.mkdir(parents=True, exist_ok=True)
    source = resources.files("deepclean").joinpath("assets/claude/deepclean.md")
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def install_vscode_extension(extensions_dir=None):
    root = Path(extensions_dir or (Path.home() / ".vscode" / "extensions"))
    target = root / f"shruthi423.deepclean-context-{__version__}"
    target.mkdir(parents=True, exist_ok=True)

    source_root = resources.files("deepclean").joinpath("assets/vscode")
    for name in ("package.json", "extension.js", "README.md"):
        target.joinpath(name).write_text(
            source_root.joinpath(name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return target
