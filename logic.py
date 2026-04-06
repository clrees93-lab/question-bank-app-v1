# logic.py
# --------
# Core logic for:
#   - Selecting questions
#   - Checking answers
#   - Calculating scores
#   - Listing paper tags (shared helper)

from dataclasses import dataclass
from typing import List, Optional, Iterable, Tuple
import random
import re

from data_management import Question


# =====================================================
# Dataclass for tracking the outcome of answered questions
# =====================================================
@dataclass
class QuestionResult:
    """
    Stores the outcome of a single answered question.
    """
    question_id: int
    chosen_index: int
    was_correct: bool


# =====================================================
# Shared helper: list all exam-source tags
# New format: "YYYY MS" or "YYYY CA"
# Legacy format still supported: "YYYY Paper 1/2"
# =====================================================

# Matches:
#   "2024 MS", "2024 CA"
#   "2024MS", "2024-CA", "2024_CA"  (tolerant)
EXAM_TAG_PATTERN = re.compile(r"(\d{4})\s*[-_ ]?\s*(MS|CA)\b", re.IGNORECASE)

# Matches legacy:
#   "2024 Paper 1", "2024 paper2", "2024  Paper   2"
LEGACY_PAPER_TAG_PATTERN = re.compile(r"(\d{4})\s*Paper\s*(\d+)\b", re.IGNORECASE)

# Your chosen mapping (based on your earlier comment):
# Paper 1 -> CA
# Paper 2 -> MS
LEGACY_MAP = {1: "CA", 2: "MS"}


def list_paper_tags(questions: Iterable[Question]) -> List[str]:
    """
    Extract all unique exam-source tags from the question bank.
    Returns canonical tags like "2024 MS" or "2024 CA".

    (Function name kept as list_paper_tags because the GUI imports it.)
    """
    tags_set = set()

    for q in questions:
        for tag in q.tags:
            t = (tag or "").strip()

            # New format first
            m = EXAM_TAG_PATTERN.search(t)
            if m:
                year = m.group(1)
                typ = m.group(2).upper()
                tags_set.add(f"{year} {typ}")
                continue

            # Legacy format fallback
            m2 = LEGACY_PAPER_TAG_PATTERN.search(t)
            if m2:
                year = m2.group(1)
                try:
                    num = int(m2.group(2))
                except ValueError:
                    continue

                mapped = LEGACY_MAP.get(num)
                if mapped:
                    tags_set.add(f"{year} {mapped}")
                else:
                    # If someone had Paper 3 etc, keep something sensible
                    tags_set.add(f"{year} Paper {num}")

    return sorted(tags_set)


# =====================================================
# Selecting questions
# =====================================================
def select_questions(
    questions: List[Question],
    specialty: Optional[str] = None,
    num_questions: Optional[int] = None,
    *,
    shuffle: bool = True,
) -> List[Question]:
    """
    Select a subset of questions.

    Parameters:
      questions     - list of Question objects
      specialty     - if provided, filter to this specialty
      num_questions - if provided, limit the selection
      shuffle       - if True, randomise question order

    Returns:
      A (possibly shuffled) list of Question objects.
    """
    if specialty:
        pool = [q for q in questions if q.specialty == specialty]
    else:
        pool = list(questions)

    if shuffle:
        random.shuffle(pool)

    if num_questions is not None and num_questions < len(pool):
        pool = pool[:num_questions]

    return pool


# =====================================================
# Answer checking
# =====================================================
def check_answer(question: Question, chosen_index: int) -> bool:
    """
    Return True if the chosen index is the correct answer.
    """
    return chosen_index == question.correct_index


# =====================================================
# Scoring
# =====================================================
def calculate_score(results: List[QuestionResult]) -> Tuple[int, int, float]:
    """
    Calculate (correct, total, percent) from the results list.
    """
    total = len(results)
    correct = sum(1 for r in results if r.was_correct)
    percent = (correct / total * 100.0) if total > 0 else 0.0
    return correct, total, percent
