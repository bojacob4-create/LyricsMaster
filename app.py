import os
import logging
from flask import Flask, jsonify

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

    @app.route('/')
    @app.route('/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'service': 'lyrics-master-bot',
            'mode': 'background-worker',
            'pid': os.getpid()
        })

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
