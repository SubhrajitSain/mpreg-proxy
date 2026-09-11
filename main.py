import os
from urllib.parse import urlsplit, urlunsplit
from flask import Flask, request, Response, render_template
import requests

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

class PrefixMiddleware:
    def __init__(self, app, prefixes):
        self.app = app
        self.prefixes = prefixes

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "") or ""
        for p in self.prefixes:
            if path == p or path.startswith(p + "/"):
                new_path = path[len(p):] or "/"
                environ["PATH_INFO"] = new_path
                break
        return self.app(environ, start_response)

app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefixes=["/api/index", "/api"])

MPREG_HOST = "http://45.84.196.237:3141"
ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

def _proxy_to_mpreg(path=""):
    path = (path or "").lstrip("/")
    target_url = f"{MPREG_HOST}/{path}" if path else f"{MPREG_HOST}/"
    if request.query_string:
        target_url = f"{target_url}?{request.query_string.decode()}"

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    try:
        res = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=10,
        )
    except requests.RequestException as exc:
        return Response(f"Upstream request failed: {exc}", status=502, mimetype="text/plain")

    excluded = {"content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "upgrade"}
    response_headers = []

    for k, v in res.headers.items():
        if k.lower() in excluded:
            continue
        if k.lower() == "location":
            loc = v
            parts = urlsplit(loc)
            if not parts.netloc and not parts.scheme:
                new_loc = MPREG_HOST + (parts.path or "/")
                if parts.query:
                    new_loc += "?" + parts.query
                if parts.fragment:
                    new_loc += "#" + parts.fragment
                response_headers.append((k, new_loc))
                continue
            upstream_netloc = urlsplit(MPREG_HOST).netloc
            if parts.netloc == upstream_netloc:
                response_headers.append((k, v))
                continue
            response_headers.append((k, v))
            continue
        response_headers.append((k, v))
    return Response(res.content, status=res.status_code, headers=response_headers)


@app.route("/", methods=ALL_METHODS)
def root():
    return _proxy_to_mpreg("")


@app.route("/<path:path>", methods=ALL_METHODS)
def catch_all(path):
    return _proxy_to_mpreg(path)
