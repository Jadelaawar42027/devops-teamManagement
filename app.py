import os

from flask import Flask, render_template

from db import init_db
from kpi.routes import kpi_bp
from routing.routes import routing_bp
from seed import seed_demo

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))


def create_app():
    os.makedirs(DATA_DIR, exist_ok=True)
    init_db()
    if os.environ.get("SEED_DEMO") == "1":
        seed_demo()
    app = Flask(__name__)
    app.register_blueprint(kpi_bp)
    app.register_blueprint(routing_bp)

    @app.route("/")
    def index():
        return render_template("home.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
