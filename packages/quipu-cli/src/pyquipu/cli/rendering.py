from typing import Protocol

import typer


class Renderer(Protocol):
    def success(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def data(self, data_string: str) -> None: ...


class TyperRenderer:
    def success(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.GREEN, err=True)

    def info(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.BLUE, err=True)

    def warning(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.YELLOW, err=True)

    def error(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.RED, err=True)

    def data(self, data_string: str) -> None:
        typer.echo(data_string, err=False)  # Explicitly to stdout
