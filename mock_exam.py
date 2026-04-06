# mock_exam.py
# ------------
# CLI interface for your BPT question bank.
#
# Main features:
#   1. Run mock exam BY PAPER (year + Paper 1/2) with a 3-hour time limit.
#   2. Import/update questions from CSV (IDs controlled in CSV).
#   3. View question stats by specialty.
#   4. Export current questions to CSV.
#
# Note: For mock exams, we do NOT show per-question feedback.
# We just store results and show the score at the end.

from typing import List, Dict, Optional
import time
import re

from data_management import (
    Question,
    load_questions_from_json,
    list_specialties,
    import_from_csv,
    export_to_csv,
)
from logic import QuestionResult, select_questions, check_answer, calculate_score


# =========================================================
# Helpers for PAPER selection (year + Paper 1/2)
# =========================================================
def get_paper_meta(questions: List[Question]) -> dict[str, set[int]]:
    """
    Parse question tags to find papers like '2020 Paper 1'.
    Returns a dict: { '2020': {1, 2}, '2021': {1}, ... }
    """
    meta: dict[str, set[int]] = {}
    pattern = re.compile(r"(\d{4})\s*Paper\s*(\d+)", re.IGNORECASE)

    for q in questions:
        for tag in q.tags:
            m = pattern.search(tag)
            if m:
                year = m.group(1)
                paper_no = int(m.group(2))
                meta.setdefault(year, set()).add(paper_no)

    return meta


def choose_paper_tag_cli(questions: List[Question]) -> Optional[str]:
    """
    CLI prompt to choose a paper by year and paper number.
    Returns a tag like '2020 Paper 1', or None if cancelled/invalid.
    """
    meta = get_paper_meta(questions)
    if not meta:
        print("No papers found (no tags of the form 'YYYY Paper N').")
        return None

    years = sorted(meta.keys())
    print("\nAvailable years:")
    for y in years:
        print(f"  {y}")

    year = input("Enter exam year (e.g. 2020), or press Enter to cancel: ").strip()
    if year == "":
        return None
    if year not in meta:
        print(f"No papers found for year '{year}'.")
        return None

    papers = sorted(meta[year])
    if len(papers) == 1:
        paper_no = papers[0]
        print(f"Using only available paper: {year} Paper {paper_no}")
    else:
        print(f"Available papers for {year}:")
        for p in papers:
            print(f"  Paper {p}")
        paper_str = input("Enter paper number (e.g. 1 or 2), or press Enter to cancel: ").strip()
        if paper_str == "":
            return None
        paper_str = paper_str.lower().replace("paper", "").strip()
        if not paper_str.isdigit():
            print("Invalid paper number.")
            return None
        paper_no = int(paper_str)
        if paper_no not in papers:
            print(f"No 'Paper {paper_no}' for year {year}.")
            return None

    tag = f"{year} Paper {paper_no}"
    return tag


# =========================================================
# Other helpers
# =========================================================
def show_stats(questions: List[Question]) -> None:
    """
    Show basic question stats by specialty.
    """
    print("\n=== Question Bank Stats ===")
    print(f"Total questions: {len(questions)}")
    by_spec: Dict[str, int] = {}
    for q in questions:
        by_spec[q.specialty] = by_spec.get(q.specialty, 0) + 1

    if by_spec:
        print("By specialty:")
        for spec, count in sorted(by_spec.items()):
            print(f"  {spec}: {count}")
    print()


# =========================================================
# MOCK EXAM (CLI) – by paper, 3-hour time limit
# =========================================================
def run_mock_exam_cli(questions: List[Question]) -> None:
    """
    Run a mock exam in the terminal:
      - Choose paper by year + Paper 1/2
      - Use only questions tagged with that paper
      - 3-hour time limit (no per-question feedback)
    """
    if not questions:
        print("No questions found. Import from CSV or add some first.\n")
        return

    chosen_tag = choose_paper_tag_cli(questions)
    if not chosen_tag:
        return

    paper_questions = [q for q in questions if chosen_tag in q.tags]
    if not paper_questions:
        print(f"No questions found for '{chosen_tag}'.\n")
        return

    # For mock exam we usually want the full paper set (no manual limit)
    exam_questions = select_questions(
        paper_questions,
        specialty=None,
        num_questions=None,
    )

    print(f"\nStarting mock exam for {chosen_tag} with {len(exam_questions)} questions.")
    print("You have 3 hours. Type 'q' as an answer to finish early.\n")

    # 3-hour time limit
    time_limit_secs = 3 * 60 * 60
    start_time = time.time()

    results: List[QuestionResult] = []

    for i, q in enumerate(exam_questions, start=1):
        # Check time remaining
        elapsed = time.time() - start_time
        remaining = time_limit_secs - elapsed
        if remaining <= 0:
            print("\nTime is up! 3 hours have elapsed.\n")
            break

        # Show approximate remaining time each question
        rem_h = int(remaining // 3600)
        rem_m = int((remaining % 3600) // 60)
        rem_s = int(remaining % 60)
        print(f"Time remaining: {rem_h:02d}:{rem_m:02d}:{rem_s:02d}")

        # NOTE: we do NOT show ID, only question number + specialty
        print(f"Q{i} [{q.specialty}]")
        print(q.stem)
        for j, opt in enumerate(q.options, start=1):
            print(f"  {j}. {opt}")

        # Get user answer
        while True:
            ans = input("Your answer (number, or 'q' to finish exam): ").strip().lower()
            if ans == "q":
                print("\nExam finished early by user.\n")
                # We'll score what has been answered so far
                # (Don't process this question)
                # Exit outer loop
                i = len(exam_questions)  # just to break outer loop cleanly
                break
            if not ans.isdigit():
                print("Please enter a number or 'q'.")
                continue
            idx = int(ans) - 1
            if 0 <= idx < len(q.options):
                # Record the result
                is_correct = check_answer(q, idx)
                results.append(
                    QuestionResult(
                        question_id=q.id,
                        chosen_index=idx,
                        was_correct=is_correct,
                    )
                )
                break
            else:
                print("Answer out of range.")

        # If user entered 'q', we break from outer loop
        if ans == "q":
            break

    # End of exam (time up, finished questions, or user quit)
        correct, total, percent = calculate_score(results)
    print("=== Mock exam complete ===")
    print(f"Questions answered: {total}")
    print(f"Score: {correct}/{total} ({percent:.1f}%)\n")

    # Offer review of incorrect questions
    wrong = [
        (q, r)
        for q, r in zip(exam_questions, results)
        if not r.was_correct
    ]
    if not wrong:
        print("You answered all questions correctly – nothing to review.\n")
        return

    choice = input("Review incorrect questions? (y/n): ").strip().lower()
    if choice != "y":
        return

    print("\n=== Review of incorrect questions ===\n")
    for idx, (q, r) in enumerate(wrong, start=1):
        print(f"--- {idx}/{len(wrong)} ---")
        print(f"[{q.specialty}]")
        print(q.stem)
        print()
        if 0 <= r.chosen_index < len(q.options):
            your_answer = q.options[r.chosen_index]
            your_idx = r.chosen_index + 1
        else:
            your_answer = "(No answer recorded)"
            your_idx = None

        correct_answer = q.options[q.correct_index]
        correct_idx = q.correct_index + 1

        print(f"Your answer:   {your_idx if your_idx is not None else '-'}. {your_answer}")
        print(f"Correct answer:{correct_idx}. {correct_answer}")
        if q.explanation:
            print("\nExplanation:")
            print(q.explanation)
        input("\nPress Enter for next...\n")



# =========================================================
# MAIN MENU
# =========================================================
def main_menu() -> None:
    """
    Main CLI menu entry point.
    """
    questions = load_questions_from_json()

    while True:
        print("=== BPT Mock Exam CLI ===")
        print("1. Run mock exam (by paper, 3-hour limit)")
        print("2. Import/update from CSV")
        print("3. View stats")
        print("4. Export current questions to CSV")
        print("5. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            run_mock_exam_cli(questions)
        elif choice == "2":
            questions = import_from_csv(questions)
        elif choice == "3":
            show_stats(questions)
        elif choice == "4":
            export_to_csv(questions)
        elif choice == "5":
            print("Good luck with study! 👋\n")
            break
        else:
            print("Invalid choice.\n")


if __name__ == "__main__":
    main_menu()
