import logging
import os
import time
from datetime import date, datetime

from flask import g, jsonify, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

import db

log = logging.getLogger("requests")


class JSONProvider(DefaultJSONProvider):
    # Flask's default turns datetimes into HTTP-date strings; ISO 8601 is easier for the UI.
    # SQL Server returns naive UTC datetimes, so they are marked with Z.
    @staticmethod
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat() + ("Z" if o.tzinfo is None else "")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


def allowed_origins():
    return {o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()}


def install(app):
    """Request logging, CORS restricted to the UI origin, JSON errors and GET /health."""
    origins = allowed_origins()
    app.json = JSONProvider(app)

    @app.before_request
    def start_timer():
        g.start = time.perf_counter()
        if request.method == "OPTIONS":
            return "", 204

    @app.after_request
    def finish(response):
        origin = request.headers.get("Origin")
        if origin and origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        duration_ms = (time.perf_counter() - g.get("start", time.perf_counter())) * 1000
        log.info("%s %s %s %.0fms", request.method, request.path, response.status_code, duration_ms)
        return response

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="not found"), 404

    @app.errorhandler(405)
    def not_allowed(_):
        return jsonify(error="method not allowed"), 405

    @app.errorhandler(Exception)
    def unexpected(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        log.exception("unhandled error")
        return jsonify(error="internal error"), 500

    @app.get("/health")
    def health():
        version = os.environ.get("GIT_SHA", "dev")
        try:
            # few retries: health must answer within the caller's timeout, not wait out a full resume
            conn = db.get_connection(attempts=2)
            try:
                db.can_read_and_write(conn)
            finally:
                conn.close()
        except Exception as exc:
            log.warning("health check failed: %s", exc)
            return jsonify(status="error", db="unavailable", version=version), 503
        return jsonify(status="ok", db="ok", version=version), 200
