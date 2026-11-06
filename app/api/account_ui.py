"""Same-origin browser shell; all identity mutations use existing JSON APIs."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
templates = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
router = APIRouter(include_in_schema=False)


@router.get("/account", response_class=HTMLResponse)
def account_page() -> HTMLResponse:
    return HTMLResponse(templates.get_template("account.html").render())


@router.get("/account/assets/account.js")
def account_script() -> Response:
    return Response(
        (ROOT / "static" / "account.js").read_text(encoding="utf-8"), media_type="text/javascript"
    )


@router.get("/account/assets/account.css")
def account_style() -> Response:
    return Response(
        (ROOT / "static" / "account.css").read_text(encoding="utf-8"), media_type="text/css"
    )
