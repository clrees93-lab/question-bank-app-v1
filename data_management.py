# data_management.py
# -------------------
# Handles:
#   - Question dataclass (including optional image_path)
#   - Loading/saving questions to JSON
#   - Importing questions from CSV (IDs controlled in CSV)
#   - Exporting questions to CSV
#   - Listing specialties
#
# CSV <-> JSON behaviour:
#   - You control IDs in questions.csv
#   - Import will REPLACE existing questions with the same ID
#   - New IDs are added
#   - image_path is an optional column in the CSV

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import json
import csv
import os

# Filenames used by the app
JSON_FILE = "questions.json"
CSV_FILE = "questions.csv"


# =====================================================
# Core Question model
# =====================================================
@dataclass
class Question:
    """
    Core question model used throughout the project.

    Fields:
      id            - integer ID you control (e.g. 1, 2, 3)
      stem          - question text
      options       - list of answer options (strings)
      correct_index - index into options list (0-based)
      explanation   - explanation shown after answering
      specialty     - e.g. "Endocrine", "Oncology"
      tags          - list of tags, e.g. ["T1DM", "2020 Paper 1"]
      image_path    - optional path to an associated image file
                      (e.g. "images/q0001.png")
      explanation_image - optional path to an explanation image file
      explanation_video - optional path to an explanation video file
    """
    id: int
    stem: str
    options: List[str]
    correct_index: int
    explanation: str
    specialty: str
    tags: List[str]
    image_path: Optional[str] = None
    explanation_image: Optional[str] = None
    explanation_video: Optional[str] = None


# =====================================================
# JSON load/save
# =====================================================
def load_questions_from_json(json_file: str = JSON_FILE) -> List[Question]:
    """
    Load the current question bank from JSON_FILE.

    If the file doesn't exist, returns an empty list.
    """
    if not os.path.exists(json_file):
        return []

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions: List[Question] = []
    for item in data:
        questions.append(
            Question(
                id=item["id"],
                stem=item["stem"],
                options=item["options"],
                correct_index=item["correct_index"],
                explanation=item.get("explanation", ""),
                specialty=item.get("specialty", "General"),
                tags=item.get("tags", []),
                image_path=item.get("image_path"),  # may be None / missing
                explanation_image=item.get("explanation_image"),  # may be None / missing
                explanation_video=item.get("explanation_video"),  # may be None / missing
            )
        )

    return questions


def save_questions_to_json(
    questions: List[Question],
    json_file: str = JSON_FILE,
) -> None:
    """
    Save the question bank to JSON_FILE.
    """
    data = [asdict(q) for q in questions]
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =====================================================
# Helpers
# =====================================================
def list_specialties(questions: List[Question]) -> List[str]:
    """
    Return a sorted list of unique specialties present in the questions.
    """
    return sorted({q.specialty for q in questions})


# =====================================================
# CSV import/export
# =====================================================
def import_from_csv(
    existing_questions: List[Question],
    csv_file: str = CSV_FILE,
    json_file: str = JSON_FILE,
) -> List[Question]:
    """
    Import/update questions from a CSV file.

    - IDs are controlled in the CSV.
    - If a row has an ID that already exists, it REPLACES that question.
    - If it's a new ID, it is added.
    - At the end, questions are saved back to JSON_FILE.

    CSV expected columns (header):
      id, stem, option1..option6, correct, explanation, specialty, tags, image_path

    - tags is a comma-separated list.
    - image_path is optional (e.g. "images/q0001.png").
    """
    existing_by_id: Dict[int, Question] = {q.id: q for q in existing_questions}

    if not os.path.exists(csv_file):
        print(f"No CSV file found at {csv_file}.")
        return existing_questions

    imported = 0
    skipped = 0

    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):  # row 1 = header
            # --- ID is required and must be an integer ---
            id_raw = (row.get("id") or "").strip()
            if not id_raw.isdigit():
                print(f"Row {row_num}: missing or invalid ID → skipping.")
                skipped += 1
                continue
            q_id = int(id_raw)

            # --- Stem is required ---
            stem = (row.get("stem") or "").strip()
            if not stem:
                print(f"Row {row_num}: empty stem → skipping.")
                skipped += 1
                continue

            # --- Options (option1..option6) ---
            options: List[str] = []
            for i in range(1, 9):
                opt = (row.get(f"option{i}") or "").strip()
                if opt:
                    options.append(opt)

            if not options:
                print(f"Row {row_num}: no options provided → skipping.")
                skipped += 1
                continue

            # --- Correct: 1-based index for human readability ---
            correct_raw = (row.get("correct") or "").strip()
            if not correct_raw.isdigit():
                print(f"Row {row_num}: invalid 'correct' (must be 1..N) → skipping.")
                skipped += 1
                continue

            correct_index_1based = int(correct_raw)
            if not 1 <= correct_index_1based <= len(options):
                print(f"Row {row_num}: 'correct' out of range → skipping.")
                skipped += 1
                continue

            correct_index = correct_index_1based - 1

            # --- Explanation / specialty / tags / image_path ---
            explanation = (row.get("explanation") or "").strip()
            specialty = (row.get("specialty") or "General").strip() or "General"

            tags_raw = (row.get("tags") or "").strip()
            if tags_raw:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            else:
                tags = []

            image_path = (row.get("image_path") or "").strip() or None
            explanation_image = (row.get("explanation_image") or "").strip() or None
            explanation_video = (row.get("explanation_video") or "").strip() or None

            q = Question(
                id=q_id,
                stem=stem,
                options=options,
                correct_index=correct_index,
                explanation=explanation,
                specialty=specialty,
                tags=tags,
                image_path=image_path,
                explanation_image=explanation_image,
                explanation_video=explanation_video,
            )

            # Replace or add
            existing_by_id[q_id] = q
            imported += 1

    new_questions = sorted(existing_by_id.values(), key=lambda q: q.id)
    save_questions_to_json(new_questions, json_file=json_file)

    print(f"Imported/updated {imported} questions from {csv_file}. Skipped {skipped} row(s).")
    return new_questions


def export_to_csv(
    questions: List[Question],
    csv_file: str = CSV_FILE,
) -> None:
    """
    Export the current questions to CSV.

    Columns:
      id, stem, option1..option6, correct, explanation, specialty, tags, image_path
    """
    fieldnames = [
        "id",
        "stem",
        "option1",
        "option2",
        "option3",
        "option4",
        "option5",
        "option6",
        "correct",
        "explanation",
        "specialty",
        "tags",
        "image_path",
        "explanation_image",
        "explanation_video",
    ]

    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for q in questions:
            row: Dict[str, str] = {
                "id": str(q.id),
                "stem": q.stem,
                "explanation": q.explanation,
                "specialty": q.specialty,
                "tags": ",".join(q.tags),
                "image_path": q.image_path or "",
                "explanation_image": q.explanation_image or "",
                "explanation_video": q.explanation_video or "",
            }

            # Write options into option1..option6
            for i in range(6):
                row[f"option{i+1}"] = q.options[i] if i < len(q.options) else ""

            # correct is 1-based index for human readability
            row["correct"] = str(q.correct_index + 1)

            writer.writerow(row)

    print(f"Exported {len(questions)} questions to {csv_file}.")
