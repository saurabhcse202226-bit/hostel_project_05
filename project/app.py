import os
from flask import Flask

from .database import init_db
from .settings import Settings
from .urls import register_legacy_endpoint_aliases, register_routes


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates")),
        static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static")),
    )

    app.secret_key = Settings.SECRET_KEY

    app.config["UPLOAD_FOLDER"] = Settings.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = Settings.MAX_CONTENT_LENGTH
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_db(app)

    register_routes(app)
    register_legacy_endpoint_aliases(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Settings.HOST, port=Settings.PORT, debug=Settings.DEBUG)