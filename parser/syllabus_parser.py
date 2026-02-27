"""
Syllabus parser — extracts grading policy from PDF or text files using Ollama.
"""

import json
import re
import pdfplumber
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"
MAX_TEXT_CHARS = 12000

SYLLABUS_PROMPT_TEMPLATE = """You are an academic assistant that extracts grading policies from course syllabi.

Return ONLY a valid JSON object. No markdown code blocks. No explanation text. Just the JSON.

Required JSON structure:
{{
  "course_name": "string",
  "categories": [
    {{
      "name": "string",
      "weight": <number between 0 and 100>,
      "num_items": <integer or null>,
      "drop_policy": {{
        "type": "<drop_lowest|drop_highest|none>",
        "count": <integer>
      }}
    }}
  ],
  "grade_scale": {{
    "A": <minimum percentage for A>,
    "B": <minimum percentage for B>,
    "C": <minimum percentage for C>,
    "D": <minimum percentage for D>,
    "F": 0
  }},
  "extra_credit_possible": <true or false>
}}

Important rules:
1. Category weights must be numbers (e.g., 20 not "20%")
2. All weights should sum to approximately 100
3. If drop policy not mentioned, use {{"type": "none", "count": 0}}
4. If grade scale not mentioned, use: A=93, B=83, C=73, D=63, F=0
5. Common category names: Homework, Quizzes, Midterm, Final, Labs, Participation, Projects
6. If a category says "lowest X dropped", set drop_policy type to "drop_lowest" and count to X
7. num_items is the total number of assignments/quizzes in that category, or null if not stated

Syllabus text to parse:
===
{syllabus_text}
==="""


def extract_text_from_pdf(file_path: str) -> str:
    """Extract all text from a PDF using pdfplumber, truncated to MAX_TEXT_CHARS."""
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    full_text = "\n".join(text_parts)
    if len(full_text) > MAX_TEXT_CHARS:
        full_text = full_text[:MAX_TEXT_CHARS] + "\n[... text truncated for length ...]"
    return full_text


def extract_text_from_txt(file_path: str) -> str:
    """Read a plain text file with UTF-8 fallback to latin-1."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as f:
            text = f.read()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n[... text truncated for length ...]"
    return text


def call_ollama(prompt: str, retries: int = 2) -> str:
    """
    Call the local Ollama API and return the model's text response.
    Retries up to `retries` times on timeout (model may be loading).
    Raises ConnectionError if Ollama is not running.
    Raises TimeoutError if all attempts time out.
    """
    TIMEOUT = 300  # 5 minutes — llama3.2 can be slow on first load

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            return response.json()["response"]
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                "Cannot connect to Ollama at http://localhost:11434. "
                "Start it with: ollama serve"
            )
        except requests.exceptions.Timeout:
            if attempt < retries:
                # Model is still loading — wait a moment and retry
                import time
                time.sleep(5)
                continue
            raise TimeoutError(
                f"Ollama did not respond after {TIMEOUT}s ({retries} attempts). "
                "Try running: ollama pull llama3.2 — then restart the app."
            )
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama returned an error: {e}")


def parse_llm_json_response(raw: str):
    """
    Robustly extract a JSON object or array from an LLM response.
    Attempts: direct parse → strip markdown fences → extract {…} → extract […]
    Returns parsed dict/list or None on failure.
    """
    if not raw:
        return None

    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown code fences
    stripped = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Attempt 3: extract first { ... } block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Attempt 4: extract first [ ... ] block
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _validate_policy(policy: dict) -> dict:
    """Add validation metadata to grading policy."""
    categories = policy.get("categories", [])
    total_weight = sum(c.get("weight", 0) for c in categories)
    policy["total_weight"] = round(total_weight, 1)

    if abs(total_weight - 100) > 2:
        policy["weight_warning"] = (
            f"Category weights sum to {total_weight:.1f}%, not 100%. "
            "Please review and adjust in the editor."
        )

    # Ensure grade_scale exists
    if not policy.get("grade_scale"):
        policy["grade_scale"] = {"A": 93, "B": 83, "C": 73, "D": 63, "F": 0}

    # Ensure each category has a drop_policy
    for cat in categories:
        if not cat.get("drop_policy"):
            cat["drop_policy"] = {"type": "none", "count": 0}

    return policy


def parse_syllabus(file_path: str, file_type: str) -> dict:
    """
    Main entry point. Extracts grading policy from a syllabus file.

    file_type: 'pdf' or 'txt'
    Returns grading policy dict.
    Raises ConnectionError, TimeoutError, or ValueError.
    """
    if file_type == "pdf":
        text = extract_text_from_pdf(file_path)
    elif file_type == "txt":
        text = extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")

    if not text.strip():
        raise ValueError("No text could be extracted from the file.")

    prompt = SYLLABUS_PROMPT_TEMPLATE.format(syllabus_text=text)
    raw_response = call_ollama(prompt)

    policy = parse_llm_json_response(raw_response)
    if policy is None:
        raise ValueError(raw_response)  # caller will return 422 with raw

    return _validate_policy(policy)
