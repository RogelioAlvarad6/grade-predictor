"""
Grade calculation engine — pure logic, no external dependencies.
"""

DEFAULT_GRADE_SCALE = {"A": 93, "B": 83, "C": 73, "D": 63, "F": 0}


def apply_drop_policy(assignments: list, drop_policy: dict) -> list:
    """
    Remove lowest or highest N scores from a list of graded assignments.
    Only operates on assignments with status='graded'.
    Returns the subset that counts toward the grade.
    """
    if not drop_policy or drop_policy.get("type") == "none" or drop_policy.get("count", 0) == 0:
        return assignments

    drop_type = drop_policy.get("type", "none")
    drop_count = int(drop_policy.get("count", 0))

    if len(assignments) <= drop_count:
        # Keep at least 1
        drop_count = len(assignments) - 1
        if drop_count <= 0:
            return assignments

    if drop_type == "drop_lowest":
        sorted_asgn = sorted(
            assignments,
            key=lambda a: (a["score_earned"] / a["max_score"]) if a["max_score"] else 0
        )
        return sorted_asgn[drop_count:]
    elif drop_type == "drop_highest":
        sorted_asgn = sorted(
            assignments,
            key=lambda a: (a["score_earned"] / a["max_score"]) if a["max_score"] else 0,
            reverse=True
        )
        return sorted_asgn[drop_count:]

    return assignments


def calculate_category_grade(assignments: list, drop_policy: dict = None) -> dict:
    """
    Calculate grade for a single category.

    Returns:
        earned, possible, percentage, graded_count, dropped_count, missing_count, ungraded_count
    """
    graded = [
        a for a in assignments
        if a.get("status") == "graded" and a.get("score_earned") is not None
    ]
    excused = [a for a in assignments if a.get("status") == "excused"]
    missing = [a for a in assignments if a.get("status") == "missing"]
    ungraded = [a for a in assignments if a.get("status") == "ungraded"]

    after_drops = apply_drop_policy(graded, drop_policy or {"type": "none", "count": 0})
    dropped_count = len(graded) - len(after_drops)

    earned = sum(a["score_earned"] for a in after_drops)
    possible = sum(a["max_score"] for a in after_drops if a.get("max_score"))

    # Missing count as 0/max_score
    for a in missing:
        if a.get("max_score"):
            possible += a["max_score"]

    percentage = (earned / possible * 100) if possible > 0 else None

    return {
        "earned": earned,
        "possible": possible,
        "percentage": percentage,
        "graded_count": len(graded),
        "dropped_count": dropped_count,
        "missing_count": len(missing),
        "ungraded_count": len(ungraded),
        "excused_count": len(excused),
    }


def get_letter_grade(percentage: float, grade_scale: dict = None) -> str:
    """Map a percentage to a letter grade using the provided scale."""
    scale = grade_scale or DEFAULT_GRADE_SCALE
    if percentage is None:
        return "N/A"

    # Build sorted list of (min_percentage, letter) descending
    thresholds = sorted(scale.items(), key=lambda x: x[1], reverse=True)

    for letter, min_pct in thresholds:
        if percentage >= min_pct:
            return letter

    return "F"


def calculate_weighted_grade(categories: list, grades_by_category: dict, grade_scale: dict = None) -> dict:
    """
    Calculate overall weighted grade.

    categories: list of {name, weight, drop_policy, ...} from grading policy
    grades_by_category: {category_name: [assignment_dicts]}
    grade_scale: {letter: min_percentage}

    Returns:
        overall_percentage, letter_grade, per_category, points_buffer_before_drop,
        current_grade_points, grade_scale
    """
    scale = grade_scale or DEFAULT_GRADE_SCALE
    per_category = {}
    total_weight_used = 0.0
    weighted_sum = 0.0

    for cat in categories:
        name = cat["name"]
        weight = cat.get("weight", 0) / 100.0  # convert from % to decimal
        assignments = grades_by_category.get(name, [])
        drop_policy = cat.get("drop_policy", {"type": "none", "count": 0})

        cat_grade = calculate_category_grade(assignments, drop_policy)

        per_category[name] = {
            **cat_grade,
            "weight": cat.get("weight", 0),
            "weighted_contribution": (cat_grade["percentage"] * weight) if cat_grade["percentage"] is not None else None,
        }

        if cat_grade["percentage"] is not None:
            weighted_sum += cat_grade["percentage"] * weight
            total_weight_used += weight

    # Normalize if some categories have no grades yet
    if total_weight_used > 0 and total_weight_used < 1.0:
        overall_percentage = (weighted_sum / total_weight_used) * 100 / 100
        # Re-express as if total weight = 100%
        overall_percentage = weighted_sum / total_weight_used
    else:
        overall_percentage = weighted_sum

    letter = get_letter_grade(overall_percentage, scale)

    # Calculate buffer before dropping a letter grade
    sorted_thresholds = sorted(scale.items(), key=lambda x: x[1], reverse=True)
    buffer = None
    for ltr, min_pct in sorted_thresholds:
        if min_pct < overall_percentage:
            buffer = overall_percentage - min_pct
            break

    return {
        "overall_percentage": round(overall_percentage, 2) if overall_percentage else None,
        "letter_grade": letter,
        "per_category": per_category,
        "points_buffer_before_drop": round(buffer, 2) if buffer is not None else None,
        "grade_scale": scale,
        "total_weight_counted": round(total_weight_used * 100, 1),
    }


def calculate_what_if(grading_policy: dict, grades_by_category: dict, hypothetical_scores: dict) -> dict:
    """
    Merge hypothetical scores into current grades and recalculate.

    hypothetical_scores: {assignment_name: {score_earned, max_score, category}}
    """
    import copy
    merged = copy.deepcopy(grades_by_category)

    for asgn_name, hyp in hypothetical_scores.items():
        category = hyp.get("category")
        if not category:
            continue

        if category not in merged:
            merged[category] = []

        # Check if assignment exists and update; otherwise append
        found = False
        for existing in merged[category]:
            if existing.get("assignment_name") == asgn_name:
                existing["score_earned"] = hyp["score_earned"]
                existing["max_score"] = hyp.get("max_score", existing.get("max_score", 100))
                existing["status"] = "graded"
                found = True
                break

        if not found:
            merged[category].append({
                "assignment_name": asgn_name,
                "score_earned": hyp["score_earned"],
                "max_score": hyp.get("max_score", 100),
                "status": "graded",
            })

    categories = grading_policy.get("categories", [])
    grade_scale = grading_policy.get("grade_scale", DEFAULT_GRADE_SCALE)
    return calculate_weighted_grade(categories, merged, grade_scale)


def _get_remaining_assignments(grading_policy: dict, grades_by_category: dict) -> list:
    """Return list of ungraded/future assignments based on num_items in policy."""
    remaining = []
    for cat in grading_policy.get("categories", []):
        name = cat["name"]
        num_items = cat.get("num_items")
        if num_items is None:
            continue

        existing = grades_by_category.get(name, [])
        graded_or_missing = [
            a for a in existing
            if a.get("status") in ("graded", "missing")
        ]
        remaining_count = max(0, num_items - len(graded_or_missing))

        for i in range(remaining_count):
            remaining.append({
                "assignment_name": f"{name} (remaining {i + 1})",
                "category": name,
                "max_score": 100,
                "status": "ungraded",
                "score_earned": None,
            })

    return remaining


def calculate_needed_scores(
    grading_policy: dict,
    grades_by_category: dict,
    target_letter: str,
    remaining_assignments: list = None,
) -> dict:
    """
    Determine what average score is needed on remaining work to achieve target_letter.

    Returns:
        target_percentage, required_average, is_achievable, per_category_needed,
        remaining_assignments (list)
    """
    scale = grading_policy.get("grade_scale", DEFAULT_GRADE_SCALE)
    target_pct = scale.get(target_letter.upper(), 90)

    if remaining_assignments is None:
        remaining_assignments = _get_remaining_assignments(grading_policy, grades_by_category)

    if not remaining_assignments:
        # No remaining work — check if current grade already meets target
        current = calculate_weighted_grade(
            grading_policy.get("categories", []),
            grades_by_category,
            scale,
        )
        current_pct = current["overall_percentage"] or 0
        return {
            "target_percentage": target_pct,
            "required_average": None,
            "is_achievable": current_pct >= target_pct,
            "current_percentage": current_pct,
            "per_category_needed": {},
            "remaining_assignments": [],
        }

    # Binary search / algebraic solve:
    # Find what uniform score (0-100) on all remaining assignments hits target_pct
    def simulate(score_pct: float) -> float:
        hyp = {
            a["assignment_name"]: {
                "score_earned": score_pct / 100 * a.get("max_score", 100),
                "max_score": a.get("max_score", 100),
                "category": a["category"],
            }
            for a in remaining_assignments
        }
        result = calculate_what_if(grading_policy, grades_by_category, hyp)
        return result["overall_percentage"] or 0

    best_possible = simulate(100)
    worst_possible = simulate(0)

    if best_possible < target_pct:
        # Can't reach target even with 100% on everything
        return {
            "target_percentage": target_pct,
            "required_average": None,
            "is_achievable": False,
            "best_possible": round(best_possible, 2),
            "current_percentage": worst_possible,
            "per_category_needed": {},
            "remaining_assignments": remaining_assignments,
        }

    # Binary search for required score
    lo, hi = 0.0, 100.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if simulate(mid) >= target_pct:
            hi = mid
        else:
            lo = mid

    required_average = round(hi, 1)

    # Per-category breakdown
    per_category_needed = {}
    for cat in grading_policy.get("categories", []):
        name = cat["name"]
        cat_remaining = [a for a in remaining_assignments if a["category"] == name]
        if cat_remaining:
            per_category_needed[name] = {
                "remaining_count": len(cat_remaining),
                "required_score_each": required_average,
            }

    return {
        "target_percentage": target_pct,
        "required_average": required_average,
        "is_achievable": True,
        "best_possible": round(best_possible, 2),
        "per_category_needed": per_category_needed,
        "remaining_assignments": remaining_assignments,
    }


def generate_scenarios(grading_policy: dict, grades_by_category: dict, remaining_assignments: list = None) -> dict:
    """
    Generate best_case, worst_case, and current_pace scenario grades.
    """
    scale = grading_policy.get("grade_scale", DEFAULT_GRADE_SCALE)

    if remaining_assignments is None:
        remaining_assignments = _get_remaining_assignments(grading_policy, grades_by_category)

    def simulate(score_pct: float) -> dict:
        hyp = {
            a["assignment_name"]: {
                "score_earned": score_pct / 100 * a.get("max_score", 100),
                "max_score": a.get("max_score", 100),
                "category": a["category"],
            }
            for a in remaining_assignments
        }
        return calculate_what_if(grading_policy, grades_by_category, hyp)

    # Current pace: compute current average across all graded work
    all_graded = []
    for asgns in grades_by_category.values():
        for a in asgns:
            if a.get("status") == "graded" and a.get("score_earned") is not None and a.get("max_score"):
                all_graded.append(a["score_earned"] / a["max_score"] * 100)

    current_avg = sum(all_graded) / len(all_graded) if all_graded else 75.0

    best = simulate(100)
    worst = simulate(0)
    pace = simulate(current_avg)

    return {
        "best_case": {
            "percentage": best["overall_percentage"],
            "letter": best["letter_grade"],
            "score_on_remaining": 100,
        },
        "worst_case": {
            "percentage": worst["overall_percentage"],
            "letter": worst["letter_grade"],
            "score_on_remaining": 0,
        },
        "current_pace": {
            "percentage": pace["overall_percentage"],
            "letter": pace["letter_grade"],
            "score_on_remaining": round(current_avg, 1),
        },
        "remaining_count": len(remaining_assignments),
    }
