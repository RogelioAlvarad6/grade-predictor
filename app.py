"""
Grade Predictor & What-If Analyzer — Flask application.
"""

import json
import os
import tempfile

from flask import Flask, jsonify, render_template, request

from engine.grade_calculator import (
    calculate_needed_scores,
    calculate_weighted_grade,
    calculate_what_if,
    generate_scenarios,
)
from parser.grades_parser import map_grades_to_categories, parse_grades
from parser.syllabus_parser import call_ollama, parse_syllabus

app = Flask(__name__)


def _warm_up_ollama():
    """Send a tiny prompt to load the model into memory before the first real request."""
    try:
        call_ollama("Say OK", retries=1)
        print("[startup] Ollama model warmed up successfully.")
    except Exception as e:
        print(f"[startup] Ollama warm-up skipped: {e}")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

ALLOWED_SYLLABUS_EXTENSIONS = {"pdf", "txt"}
ALLOWED_GRADES_EXTENSIONS = {"pdf"}


def _allowed(filename: str, allowed: set) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _ok(data):
    return jsonify({"status": "ok", "data": data}), 200


def _err(code: str, message: str, status: int, **extra):
    body = {"status": "error", "code": code, "message": message, **extra}
    return jsonify(body), status


# ── Routes ────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload-syllabus", methods=["POST"])
def upload_syllabus():
    if "file" not in request.files:
        return _err("NO_FILE", "No file uploaded.", 400)

    file = request.files["file"]
    if not file.filename:
        return _err("NO_FILE", "Empty filename.", 400)

    if not _allowed(file.filename, ALLOWED_SYLLABUS_EXTENSIONS):
        return _err(
            "INVALID_FILE",
            "Only PDF and TXT files are accepted for the syllabus.",
            400,
        )

    ext = file.filename.rsplit(".", 1)[1].lower()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        policy = parse_syllabus(tmp_path, ext)
        return _ok(policy)

    except ConnectionError as e:
        return _err("OLLAMA_UNAVAILABLE", str(e), 503)
    except TimeoutError as e:
        return _err("OLLAMA_TIMEOUT", str(e), 503)
    except ValueError as e:
        return _err("PARSE_FAILURE", "LLM could not parse the syllabus.", 422, raw_response=str(e))
    except Exception as e:
        return _err("SERVER_ERROR", str(e), 500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/api/upload-grades", methods=["POST"])
def upload_grades():
    if "file" not in request.files:
        return _err("NO_FILE", "No file uploaded.", 400)

    file = request.files["file"]
    if not file.filename:
        return _err("NO_FILE", "Empty filename.", 400)

    if not _allowed(file.filename, ALLOWED_GRADES_EXTENSIONS):
        return _err(
            "INVALID_FILE",
            "Only PDF files are accepted for grades.",
            400,
        )

    # grading_policy must be sent as a JSON form field alongside the file
    grading_policy_raw = request.form.get("grading_policy")
    if not grading_policy_raw:
        return _err("NO_POLICY", "grading_policy form field is required.", 400)

    try:
        grading_policy = json.loads(grading_policy_raw)
    except json.JSONDecodeError:
        return _err("INVALID_POLICY", "grading_policy is not valid JSON.", 400)

    known_categories = [c["name"] for c in grading_policy.get("categories", [])]

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        grades = parse_grades(tmp_path, known_categories)
        grades_by_category = map_grades_to_categories(grades, grading_policy.get("categories", []))

        return _ok(
            {
                "grades": grades,
                "grades_by_category": grades_by_category,
            }
        )

    except ConnectionError as e:
        return _err("OLLAMA_UNAVAILABLE", str(e), 503)
    except TimeoutError as e:
        return _err("OLLAMA_TIMEOUT", str(e), 503)
    except ValueError as e:
        return _err("PARSE_FAILURE", "LLM could not parse the grades.", 422, raw_response=str(e))
    except Exception as e:
        return _err("SERVER_ERROR", str(e), 500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/api/calculate", methods=["POST"])
def calculate():
    body = request.get_json(silent=True)
    if not body:
        return _err("INVALID_BODY", "JSON body required.", 400)

    grading_policy = body.get("grading_policy")
    grades_by_category = body.get("grades_by_category")

    if not grading_policy or not grades_by_category:
        return _err("MISSING_DATA", "grading_policy and grades_by_category are required.", 400)

    try:
        result = calculate_weighted_grade(
            grading_policy.get("categories", []),
            grades_by_category,
            grading_policy.get("grade_scale"),
        )
        # Also generate scenarios
        scenarios = generate_scenarios(grading_policy, grades_by_category)
        result["scenarios"] = scenarios
        return _ok(result)
    except Exception as e:
        return _err("CALCULATION_ERROR", str(e), 500)


@app.route("/api/what-if", methods=["POST"])
def what_if():
    body = request.get_json(silent=True)
    if not body:
        return _err("INVALID_BODY", "JSON body required.", 400)

    grading_policy = body.get("grading_policy")
    grades_by_category = body.get("grades_by_category")
    hypothetical_scores = body.get("hypothetical_scores", {})

    if not grading_policy or not grades_by_category:
        return _err("MISSING_DATA", "grading_policy and grades_by_category are required.", 400)

    try:
        result = calculate_what_if(grading_policy, grades_by_category, hypothetical_scores)
        return _ok(result)
    except Exception as e:
        return _err("CALCULATION_ERROR", str(e), 500)


@app.route("/api/needed-scores", methods=["POST"])
def needed_scores():
    body = request.get_json(silent=True)
    if not body:
        return _err("INVALID_BODY", "JSON body required.", 400)

    grading_policy = body.get("grading_policy")
    grades_by_category = body.get("grades_by_category")
    target_grade = body.get("target_grade", "A")
    remaining_assignments = body.get("remaining_assignments")

    if not grading_policy or not grades_by_category:
        return _err("MISSING_DATA", "grading_policy and grades_by_category are required.", 400)

    try:
        result = calculate_needed_scores(
            grading_policy,
            grades_by_category,
            target_grade,
            remaining_assignments,
        )
        return _ok(result)
    except Exception as e:
        return _err("CALCULATION_ERROR", str(e), 500)


@app.route("/api/scenarios", methods=["POST"])
def scenarios():
    body = request.get_json(silent=True)
    if not body:
        return _err("INVALID_BODY", "JSON body required.", 400)

    grading_policy = body.get("grading_policy")
    grades_by_category = body.get("grades_by_category")

    if not grading_policy or not grades_by_category:
        return _err("MISSING_DATA", "grading_policy and grades_by_category are required.", 400)

    try:
        result = generate_scenarios(grading_policy, grades_by_category)
        return _ok(result)
    except Exception as e:
        return _err("CALCULATION_ERROR", str(e), 500)


if __name__ == "__main__":
    _warm_up_ollama()
    app.run(debug=True, port=5000)
