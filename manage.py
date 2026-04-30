from project.app import create_app
from project.database import db

app = create_app()


@app.shell_context_processor
def _shell_context():
    return {"app": app, "db": db}
