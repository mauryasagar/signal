import os
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from report import build_report_context, TopicGenerationError
from fetch_trends import TrendFetchError
from cache import get_cache, cache_status

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Single shared cache client (safe: redis-py is thread-safe)
_cache = get_cache()


@app.route("/", methods=["GET"])
def landing():
    return render_template("landing.html")


@app.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@app.route("/generate", methods=["POST"])
def generate():
    if request.is_json:
        data = request.get_json() or {}
        niche = data.get("niche", "").strip()
    else:
        niche = request.form.get("niche", "").strip()

    is_ajax = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept") == "application/json"
    )

    if not niche:
        if is_ajax:
            return jsonify({"success": False, "error": "Please enter a niche or topic area."}), 400
        return render_template("landing.html", error="Please enter a niche or topic area.")

    try:
        context = build_report_context(niche, cache_client=_cache)
        if is_ajax:
            return jsonify({
                "success": True,
                "context": context,
                "html": render_template("report.html", **context)
            }), 200
        return render_template("report.html", **context)
    except (TopicGenerationError, TrendFetchError) as e:
        if is_ajax:
            return jsonify({"success": False, "error": str(e)}), 400
        return render_template("landing.html", error=str(e), niche=niche)


@app.route("/health", methods=["GET"])
def health():
    """
    Health check — useful for Zerops uptime monitoring and judging verification.
    Returns cache connectivity status so it's easy to confirm Valkey is wired up.
    """
    cs = cache_status(_cache)
    return jsonify({
        "status": "ok",
        "app": "signal",
        "cache": cs,
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
