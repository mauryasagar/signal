import os
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from report import build_report_context, TopicGenerationError
from fetch_trends import TrendFetchError
from generate_topics import generate_topic_ideas, generate_video_script, TopicGenerationError
from cache import get_cache, cache_status

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

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
    except Exception as e:
        logging.exception("Unexpected error in /generate")
        msg = "Something went wrong. Please try again."
        if is_ajax:
            return jsonify({"success": False, "error": msg}), 500
        return render_template("landing.html", error=msg, niche=niche)


@app.route("/generate_script", methods=["POST"])
def generate_script_route():
    """AJAX endpoint to generate a full video script on demand."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Invalid request format."}), 400

    data = request.get_json()
    title = data.get("title", "").strip()
    angle = data.get("angle", "").strip()

    if not title or not angle:
        return jsonify({"success": False, "error": "Missing title or angle."}), 400

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return jsonify({"success": False, "error": "Server missing Groq API key."}), 500

    try:
        script_data = generate_video_script(title, angle, groq_api_key)
        return jsonify({"success": True, "script": script_data}), 200
    except TopicGenerationError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        logging.exception("Unexpected error in /generate_script")
        return jsonify({"success": False, "error": "Failed to generate script."}), 500


@app.route("/health", methods=["GET"])
def health():
    cs = cache_status(_cache)
    return jsonify({
        "status": "ok",
        "app": "signal",
        "cache": cs,
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")