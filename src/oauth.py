"""Garage61 OAuth2 authorization-code flow with a local redirect server.

Flow:
  1. Start a temporary HTTP server on localhost:REDIRECT_PORT
  2. Open the Garage61 authorize URL in the system browser
  3. User logs in and approves → Garage61 redirects to http://localhost:PORT/callback?code=...
  4. Exchange the code for access + refresh tokens
  5. Return the token dict
"""
import threading
import urllib.parse
import webbrowser
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_PORT = 9876
REDIRECT_URI  = f"http://localhost:{REDIRECT_PORT}/callback"
AUTHORIZE_URL = "https://garage61.net/oauth/authorize"
TOKEN_URL     = "https://garage61.net/api/oauth/token"


class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth callback code."""

    code:  str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        _CallbackHandler.code  = params.get("code")
        _CallbackHandler.error = params.get("error")

        body = (
            b"<h2>pyracing-coach</h2><p>Authorisation complete. You can close this tab.</p>"
            if _CallbackHandler.code
            else b"<h2>pyracing-coach</h2><p>Authorisation failed. Please try again.</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_) -> None:  # suppress server log output
        pass


def run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Open the browser, wait for the redirect, exchange code for tokens.

    Returns a dict with keys: access_token, refresh_token, expires_in.
    Raises RuntimeError on failure.
    """
    _CallbackHandler.code  = None
    _CallbackHandler.error = None

    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.timeout = 120  # 2-minute window for the user to log in

    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "driving_data",
    })
    webbrowser.open(f"{AUTHORIZE_URL}?{params}")

    # Handle one request (the callback), then shut down
    server.handle_request()
    server.server_close()

    if _CallbackHandler.error:
        raise RuntimeError(f"Garage61 denied access: {_CallbackHandler.error}")
    if not _CallbackHandler.code:
        raise RuntimeError("No authorisation code received (timed out?)")

    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "code":          _CallbackHandler.code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()
