import logging
import os

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("pika").setLevel(logging.WARNING)

app = create_app()

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", "8000")), threaded=True)
