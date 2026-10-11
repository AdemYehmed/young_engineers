"""Point d'entrée : `python app.py` (développement) ou `gunicorn app:app` (production)."""
import os

from dotenv import load_dotenv

load_dotenv()  # charge .env avant la création de l'application

from yengineers import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("YE_HOST", "127.0.0.1"),
        port=int(os.environ.get("YE_PORT", "5000")),
        debug=(not app.config["PRODUCTION"]) and os.environ.get("YE_DEBUG") == "1",
    )
