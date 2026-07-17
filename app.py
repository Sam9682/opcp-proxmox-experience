"""
Flask web application entry point for Proxmox Install Automation.

Serves the skillhub static site and provides API/health endpoints
behind an nginx reverse proxy.
"""

import os
import json
from datetime import datetime

from flask import Flask, jsonify, send_from_directory, render_template

from src.config import PORT, HOST, SECRET_KEY, FLASK_ENV

app = Flask(
    __name__,
    static_folder="skillhub",
    template_folder="templates",
)
app.config["SECRET_KEY"] = SECRET_KEY


@app.route("/health")
def health():
    """Health check endpoint for Docker and nginx."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "opcp-proxmox-experience",
    })


@app.route("/api/info")
def api_info():
    """Application info endpoint."""
    return jsonify({
        "name": "opcp-proxmox-experience",
        "version": "0.1.0",
        "description": os.environ.get(
            "DESCRIPTION", "Proxmox GPU Passthrough Automation"
        ),
        "user": {
            "id": os.environ.get("USER_ID", "0"),
            "name": os.environ.get("USER_NAME", "User"),
            "email": os.environ.get("USER_EMAIL", "user@example.com"),
        },
    })


@app.route("/")
def index():
    """Serve the main index page."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files from skillhub."""
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=(FLASK_ENV != "production"))
