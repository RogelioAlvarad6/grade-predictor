"""
Grades parser — extracts grade entries from Canvas/LMS PDF exports using Ollama.
"""

import re
from parser.syllabus_parser import (
    extract_text_from_pdf,
    call_ollama,
    parse_llm_json_response,
    MAX_TEXT_CHARS,
)

GRADES_PROMPT_TEMPLATE = """You are an academic assistant that extracts grade data from Canvas/LMS grade export PDFs.

Return ONLY a valid JSON array. No markdown code blocks. No explanation. Just the array.

Each element must have this exact structure:
{{
  "assignment_name": "string",
  "category": "string",
  "score_earned": <number or null>,
  "max_score": <number or null>,
  "status": "<graded|missing|excused|ungraded>",
  "submission_date": "string or null"
}}

Rules:
1. score_earned is null for missing, excused, and ungraded assignments
2. status "excused" means the student was excused (does not count against them)
3. status "missing" means not submitted (usually counts as 0 toward final grade)
4. status "ungraded" means submitted but not yet graded
5. status "graded" means a numeric score is present
6. max_score should be the total possible points; use null if unclear
7. Match the category field to one of these known categories from the syllabus:
   {known_categories}
   If a category is unclear, use your best judgment based on the assignment name
8. Do not invent assignments that are not in the text
9. Ignore summary rows, totals, and header rows

Grade export text to parse:
===
{grades_text}
==="""


def _normalize(s: str) -> str:
    """Lowercase and strip non-alphanumeric characters for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def map_grades_to_categories(grades: list, categories: list) -> dict:
    """
    Group grades by category using fuzzy matching.

    Matching order:
    1. Exact match
    2. Normalized (lowercase, stripped) exact match
    3. Substring match (normalized)
    4. Falls into 'Uncategorized'

    Returns: {category_name: [grade_entry, ...]}
    """
    category_names = [c["name"] for c in categories]
    normalized_map = {_normalize(n): n for n in category_names}

    result = {n: [] for n in category_names}
    result["Uncategorized"] = []

    for grade in grades:
        raw_cat = grade.get("category", "")

        # 1. Exact match
        if raw_cat in result:
            result[raw_cat].append(grade)
            continue

        # 2. Normalized exact match
        norm = _normalize(raw_cat)
        if norm in normalized_map:
            result[normalized_map[norm]].append(grade)
            continue

        # 3. Substring match
        matched = False
        for nn, original in normalized_map.items():
            if norm and (norm in nn or nn in norm):
                result[original].append(grade)
                matched = True
                break

        if not matched:
            result["Uncategorized"].append(grade)

    # Remove empty Uncategorized to keep output clean
    if not result["Uncategorized"]:
        del result["Uncategorized"]

    return result


def parse_grades(file_path: str, known_categories: list) -> list:
    """
    Main entry point for grades parsing.

    file_path: path to grades PDF
    known_categories: list of category name strings from the parsed syllabus

    Returns list of grade entry dicts.
    Raises ConnectionError, TimeoutError, or ValueError.
    """
    text = extract_text_from_pdf(file_path)

    if not text.strip():
        raise ValueError("No text could be extracted from the grades PDF.")

    categories_str = ", ".join(known_categories) if known_categories else "unknown"
    prompt = GRADES_PROMPT_TEMPLATE.format(
        grades_text=text,
        known_categories=categories_str,
    )

    raw_response = call_ollama(prompt)
    grades = parse_llm_json_response(raw_response)

    if grades is None:
        raise ValueError(raw_response)

    if not isinstance(grades, list):
        # LLM may have returned an object with a list inside
        if isinstance(grades, dict):
            for v in grades.values():
                if isinstance(v, list):
                    grades = v
                    break
            else:
                raise ValueError(raw_response)
        else:
            raise ValueError(raw_response)

    # Normalize fields
    for g in grades:
        if "score_earned" in g and g["score_earned"] is not None:
            try:
                g["score_earned"] = float(g["score_earned"])
            except (TypeError, ValueError):
                g["score_earned"] = None
        if "max_score" in g and g["max_score"] is not None:
            try:
                g["max_score"] = float(g["max_score"])
            except (TypeError, ValueError):
                g["max_score"] = None
        if not g.get("status"):
            g["status"] = "graded" if g.get("score_earned") is not None else "ungraded"

    return grades
