from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel

_theme = Theme({
    "info":    "bold cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error":   "bold red",
    "step":    "bold magenta",
    "dim":     "dim white",
    "hi":      "bold white",
})

console = Console(theme=_theme)


def info(msg: str) -> None:
    console.print(f"[info][*][/info] {msg}")


def success(msg: str) -> None:
    console.print(f"[success][+][/success] {msg}")


def warning(msg: str) -> None:
    console.print(f"[warning][!][/warning] {msg}")


def error(msg: str) -> None:
    console.print(f"[error][-][/error] {msg}")


def step(msg: str) -> None:
    console.print(f"[step][>][/step] {msg}")


def banner() -> None:
    console.print(Panel.fit(
        "[bold red]RootDroid[/bold red] [dim]— Android Root Framework[/dim]\n"
        "[dim]For security research on devices you own[/dim]",
        border_style="red",
    ))
