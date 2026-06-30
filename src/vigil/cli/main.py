"""Vigil CLI — `vigil {version,db-init,demo,eval,serve,worker}`."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from vigil import __version__
from vigil.config import get_settings
from vigil.config.logging import configure_logging

app = typer.Typer(add_completion=False, help="Vigil — AML alert-triage & SAR-drafting agent.")
console = Console()


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"vigil {__version__}")


@app.command("db-init")
def db_init() -> None:
    """Create the database (if missing) and all tables."""
    from vigil.db.bootstrap import create_all, ensure_database

    created = ensure_database()
    create_all()
    console.print(f"[green]database ready[/green] (created={created})")


@app.command()
def demo(
    reset: bool = typer.Option(
        True,
        "--reset/--keep",
        help="Rebuild the schema for a clean, reproducible run (default). --keep preserves existing data.",
    ),
) -> None:
    """Seed a synthetic bank + alerts, then triage every alert end-to-end."""
    configure_logging()
    settings = get_settings()
    from sqlalchemy import select

    import vigil.models  # noqa: F401 - register all tables before drop/create
    from vigil.agent.runner import resolve_alert
    from vigil.db.base import Base
    from vigil.db.bootstrap import create_all, ensure_database
    from vigil.db.session import get_engine, session_scope
    from vigil.models.aml import Alert
    from vigil.models.tenant import Tenant
    from vigil.synthetic.generator import seed_demo

    ensure_database()
    if reset:
        Base.metadata.drop_all(get_engine())
    create_all()

    with session_scope() as s:
        summary = seed_demo(s, settings)
    console.print(
        f"[seed] bank=[bold]{summary['tenant_slug']}[/bold] "
        f"customers={summary['customers']} alerts={summary['alerts_created']} "
        f"(planted typologies + false positives)"
    )

    table = Table(title="Vigil — alert triage", show_lines=False)
    for col in ("alert", "reason", "typologies", "disposition", "conf", "route"):
        table.add_column(col)

    with session_scope() as s:
        tenant = s.scalars(select(Tenant).where(Tenant.slug == summary["tenant_slug"])).first()
        alerts = list(
            s.scalars(
                select(Alert)
                .where(Alert.tenant_id == tenant.id, Alert.status == "new")
                .order_by(Alert.external_alert_id)
            )
        )
        for alert in alerts:
            result = resolve_alert(s, alert.id)
            sc = result.scope
            disp = sc.disposition.value
            disp_color = "green" if disp == "clear" else ("red" if disp == "escalate" else "yellow")
            typ = ", ".join(h.typology.value for h in sc.evidenced_hypotheses) or "—"
            sar = " · SAR draft ready" if sc.sar else ""
            table.add_row(
                alert.external_alert_id,
                (alert.alert_reason[:34] + "…") if len(alert.alert_reason) > 35 else alert.alert_reason,
                typ,
                f"[{disp_color}]{disp}[/{disp_color}]{sar}",
                f"{sc.confidence:.2f}",
                result.route,
            )

    console.print(table)
    console.print(
        f"\n[bold]done[/bold] — run [cyan]vigil eval[/cyan] for metrics, "
        f"or [cyan]vigil serve[/cyan] then open {settings.app_base_url}"
    )


@app.command()
def eval() -> None:  # noqa: A001 - command name
    """Backtest the agent over labeled synthetic alerts and print metrics."""
    configure_logging()
    settings = get_settings()
    from vigil.db.session import session_scope
    from vigil.eval.harness import run_eval

    with session_scope() as s:
        metrics, records = run_eval(s, settings.demo_brand_slug)

    table = Table(title="Vigil — eval metrics (synthetic-v1)")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for k, v in metrics.items():
        table.add_row(k, f"{v}")
    console.print(table)

    if metrics["false_negatives"]:
        console.print(f"[red]FALSE NEGATIVES (zero-tolerance — recall protection): {metrics['false_negatives']}[/red]")
    else:
        console.print("[green]no false negatives — recall preserved (no suspicious alert cleared)[/green]")
    console.print(
        f"[bold]FP reduction @ fixed FN(0):[/bold] {metrics['fp_reduction'] * 100:.0f}% of false positives auto-cleared"
    )

    route_miss = [r["key"] for r in records if r["pred_route"] != r["gt_route"]]
    if route_miss:
        console.print(f"[yellow]alerts differing from ground-truth route:[/yellow] {', '.join(route_miss)}")
    else:
        console.print("[green]all alerts match ground-truth routing[/green]")


@app.command()
def serve() -> None:
    """Run the FastAPI operator console."""
    import uvicorn

    settings = get_settings()
    uvicorn.run("vigil.api.app:app", host=settings.app_host, port=settings.app_port, reload=False)


@app.command()
def worker() -> None:
    """Run an RQ worker (production async path)."""
    console.print(
        "[yellow]worker mode: production async path. The demo triages alerts inline via `vigil demo`.[/yellow]"
    )


if __name__ == "__main__":
    app()
