from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.main import app


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.form_targets = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.forms.append(values.get("data-action"))
            self.form_targets.append((values.get("method"), values.get("action")))
        if tag == "script":
            self.scripts.append(values.get("src"))


def test_account_shell_and_security_headers():
    with TestClient(app) as client:
        response = client.get("/account")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    policy = response.headers["content-security-policy"]
    assert "script-src 'self'" in policy and "'unsafe-inline'" not in policy
    assert "connect-src 'self'" in policy and "frame-ancestors 'none'" in policy
    page = Page()
    page.feed(response.text)
    assert set(page.forms) == {
        "login",
        "register",
        "request-verification",
        "verify-email",
        "forgot-password",
        "reset-password",
        "profile-update",
        "mfa-enroll",
        "mfa-confirm",
        "mfa-verify",
        "mfa-disable",
        "status",
    }
    assert page.scripts == ["/account/assets/account.js"]
    assert set(page.form_targets) == {("post", "/account")}
    assert "https://" not in response.text


def test_local_assets_and_existing_api_csp_are_preserved():
    with TestClient(app) as client:
        script = client.get("/account/assets/account.js")
        css = client.get("/account/assets/account.css")
        health = client.get("/health")
        missing = client.get("/account/assets/missing.js")
        fallback = client.post("/account", data={"password": "script-free-test-password"})
    assert script.status_code == css.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert "localStorage" not in script.text and "sessionStorage" not in script.text
    assert "innerHTML" not in script.text and "X-CSRF-Token" in script.text
    assert "pagehide" in script.text and 'input[type="password"]' in script.text
    assert health.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert missing.status_code == 404
    assert fallback.status_code == 405 and "script-free-test-password" not in fallback.text
