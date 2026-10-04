import os

from flask import Flask

from db import init_db
from kpi.routes import kpi_bp
from routing.routes import routing_bp

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "./data")


def create_app():
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    app = Flask(__name__)
    app.register_blueprint(kpi_bp)
    app.register_blueprint(routing_bp)

    @app.route("/")
    def index():
        return "<h1>Brokerage Team KPI & Lead Routing</h1><p>Coming soon.</p>"

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
