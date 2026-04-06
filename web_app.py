import random
import re
import time
from typing import List

import streamlit as st

from data_management import load_questions_from_json, import_from_csv
from logic import (
    QuestionResult,
    calculate_score,
    check_answer,
    list_paper_tags,
    select_questions,
)

from auth import require_login, show_user_banner, show_logout_button

require_login()
show_user_banner()
show_logout_button()

# ============================================================
# Data loading
# ============================================================
questions = load_questions_from_json()
questions = import_from_csv(questions)

# ============================================================
# Page setup
# ============================================================
st.set_page_config(page_title="BPT Question Bank", layout="wide")
st.title("BPT Question Bank")

# ============================================================
# Helper functions
# ============================================================
def list_specialties_local() -> List[str]:
    return sorted({q.specialty for q in questions})


def get_all_tags() -> List[str]:
    tag_set = set()
    for q in questions:
        for t in q.tags:
            t = (t or "").strip()
            if t:
                tag_set.add(t)
    return sorted(tag_set)


def search_questions_by_tag_query(query: str):
    tokens = [
        tok.strip().lower()
        for tok in re.split(r"[,\s]+", query)
        if tok.strip()
    ]
    if not tokens:
        return []

    results = []
    for q in questions:
        tags_lower = [t.lower() for t in q.tags]
        if any(any(token in tag for tag in tags_lower) for token in tokens):
            results.append(q)
    return results


def paper_pool_from_selection(selection: List[str]):
    selected_set = set(selection)
    return [
        q for q in questions
        if any(tag in selected_set for tag in q.tags)
    ]


def format_secs(secs: int) -> str:
    secs = max(0, int(secs))
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_mock_seconds_per_question(paper_tag: str) -> float:
    """
    CA = 3h10m for 100 questions
    MS = 2h10m for 70 questions
    """
    paper_tag = (paper_tag or "").upper()

    if paper_tag.endswith("CA"):
        return (3 * 60 + 10) * 60 / 100  # 114 sec/question

    if paper_tag.endswith("MS"):
        return (2 * 60 + 10) * 60 / 70   # ~111.43 sec/question

    return 110.0


def get_mock_duration_secs(paper_tag: str, num_questions: int) -> int:
    secs_per_q = get_mock_seconds_per_question(paper_tag)
    return max(60, round(num_questions * secs_per_q))


def reset_session_state_for_new_mode():
    st.session_state.exam_questions = []
    st.session_state.current_index = 0
    st.session_state.results = []
    st.session_state.started = False
    st.session_state.session_complete = False
    st.session_state.review_mode = False
    st.session_state.review_index = 0
    st.session_state.review_scope = "incorrect"
    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = None
    st.session_state.mode = None

    # Mock-specific
    st.session_state.mock_start_time = None
    st.session_state.mock_duration_secs = None
    st.session_state.mock_paper_tag = None
    st.session_state.mock_ready = False
    st.session_state.mock_ready_questions = []
    st.session_state.mock_ready_paper = None


def start_session(mode: str, exam_questions: list, mock_paper_tag: str | None = None):
    st.session_state.mode = mode
    st.session_state.exam_questions = exam_questions
    st.session_state.current_index = 0
    st.session_state.results = []
    st.session_state.started = True
    st.session_state.session_complete = False
    st.session_state.review_mode = False
    st.session_state.review_index = 0
    st.session_state.review_scope = "incorrect"
    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = None

    if mode == "mock":
        st.session_state.mock_paper_tag = mock_paper_tag
        st.session_state.mock_duration_secs = get_mock_duration_secs(
            mock_paper_tag or "",
            len(exam_questions),
        )
        st.session_state.mock_start_time = time.time()
    else:
        st.session_state.mock_paper_tag = None
        st.session_state.mock_duration_secs = None
        st.session_state.mock_start_time = None

    st.session_state.mock_ready = False
    st.session_state.mock_ready_questions = []
    st.session_state.mock_ready_paper = None


def finish_session():
    st.session_state.session_complete = True
    st.session_state.started = False
    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = None


def go_to_next_question():
    st.session_state.current_index += 1
    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = None


def get_wrong_items():
    wrong = []
    exam_questions = st.session_state.exam_questions
    results = st.session_state.results

    for q, r in zip(exam_questions, results):
        if not r.was_correct:
            wrong.append((q, r))
    return wrong


def get_review_items():
    exam_questions = st.session_state.exam_questions
    results = st.session_state.results

    if st.session_state.review_scope == "all":
        return list(zip(exam_questions, results))

    return get_wrong_items()


def render_question(q, q_num: int):
    st.subheader(f"Q{q_num} [{q.specialty}]")
    st.write(q.stem)

    if q.image_path:
        try:
            st.image(q.image_path)
        except Exception:
            st.warning(f"Could not load image: {q.image_path}")

    option_labels = [f"{i+1}. {opt}" for i, opt in enumerate(q.options)]

    chosen_label = st.radio(
        "Select your answer",
        option_labels,
        index=None,
        disabled=st.session_state.answer_submitted,
        key=f"question_radio_{st.session_state.current_index}_{st.session_state.mode}",
    )

    return option_labels, chosen_label


def get_mock_remaining_secs() -> int:
    start = st.session_state.get("mock_start_time")
    duration = st.session_state.get("mock_duration_secs")

    if start is None or duration is None:
        return 0

    elapsed = int(time.time() - start)
    return duration - elapsed


def force_finish_mock_if_expired() -> bool:
    if st.session_state.mode != "mock" or not st.session_state.started:
        return False

    remaining = get_mock_remaining_secs()
    if remaining <= 0:
        finish_session()
        return True
    return False


@st.fragment(run_every=1)
def render_mock_timer():
    if st.session_state.mode != "mock" or not st.session_state.started:
        return

    remaining = get_mock_remaining_secs()
    paper_tag = st.session_state.get("mock_paper_tag", "")
    total_qs = len(st.session_state.get("exam_questions", []))

    if remaining <= 0:
        st.error("Time left: 00:00:00")
        st.warning("Time is up. Please move to the results screen.")
    else:
        st.info(
            f"Time left: {format_secs(remaining)}  |  "
            f"Paper: {paper_tag}  |  "
            f"Questions: {total_qs}"
        )

def build_session_questions(selected_questions: list, shuffle_answers: bool = True):
    """
    Return session-specific copies of questions.
    Optionally shuffles answer order while preserving the correct answer logic.
    """
    session_questions = []

    for q in selected_questions:
        # make a shallow copy of the option list
        options = list(q.options)

        if shuffle_answers and len(options) > 1:
            # pair each option with whether it is the correct one
            paired = [
                (opt, idx == q.correct_index)
                for idx, opt in enumerate(options)
            ]

            random.shuffle(paired)

            new_options = [opt for opt, _ in paired]
            new_correct_index = next(
                i for i, (_, is_correct) in enumerate(paired) if is_correct
            )
        else:
            new_options = options
            new_correct_index = q.correct_index

        # create a session copy of the question
        session_q = q.__class__(
            id=q.id,
            stem=q.stem,
            options=new_options,
            correct_index=new_correct_index,
            explanation=q.explanation,
            specialty=q.specialty,
            tags=list(q.tags),
            image_path=q.image_path,
            explanation_image=q.explanation_image,
            explanation_video=q.explanation_video,
        )

        session_questions.append(session_q)

    return session_questions


# ============================================================
# Session state initialisation
# ============================================================
if "exam_questions" not in st.session_state:
    reset_session_state_for_new_mode()

if "selected_specialties" not in st.session_state:
    st.session_state.selected_specialties = []

if "tag_query" not in st.session_state:
    st.session_state.tag_query = ""

if "selected_papers" not in st.session_state:
    st.session_state.selected_papers = []

if "mock_paper" not in st.session_state:
    st.session_state.mock_paper = None

# ============================================================
# Mock expiry guard
# ============================================================
if force_finish_mock_if_expired():
    st.rerun()

# ============================================================
# Mock ready screen
# ============================================================
if st.session_state.mock_ready:
    mock_paper = st.session_state.mock_ready_paper
    exam_questions = st.session_state.mock_ready_questions
    allocated = get_mock_duration_secs(mock_paper or "", len(exam_questions))

    st.subheader("Mock Exam Ready")
    st.write(f"**Paper:** {mock_paper}")
    st.write(f"**Questions in this recall pool:** {len(exam_questions)}")
    st.write(f"**Allocated time:** {format_secs(allocated)}")

    if (mock_paper or "").upper().endswith("CA"):
        st.caption("CA timing is based on 3 hours 10 minutes for 100 questions.")
    elif (mock_paper or "").upper().endswith("MS"):
        st.caption("MS timing is based on 2 hours 10 minutes for 70 questions.")

    st.warning("The timer will begin only when you click 'Begin Mock Exam'.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Begin Mock Exam", use_container_width=True):
            start_session("mock", exam_questions, mock_paper)
            st.rerun()

    with col2:
        if st.button("Cancel and Return Home", use_container_width=True):
            reset_session_state_for_new_mode()
            st.rerun()

# ============================================================
# Home / Mode selection
# ============================================================
elif not st.session_state.started and not st.session_state.session_complete and not st.session_state.review_mode:
    st.write(f"Loaded {len(questions)} questions.")

    mode = st.radio(
        "Choose mode",
        [
            "Practice Questions (by Specialty)",
            "Practice by Tags",
            "Practice by Papers",
            "Mock Exam",
        ],
    )

    if mode == "Practice Questions (by Specialty)":
        specialties = list_specialties_local()
        selected_specialties = st.multiselect(
            "Select one or more specialties (leave empty for all specialties)",
            options=specialties,
            default=st.session_state.selected_specialties,
        )
        st.session_state.selected_specialties = selected_specialties

        if st.button("Start Practice by Specialty", use_container_width=True):
            if selected_specialties:
                pool = [q for q in questions if q.specialty in selected_specialties]
            else:
                pool = list(questions)

            if not pool:
                st.warning("No questions available for that selection.")
            else:
                exam_questions = select_questions(pool, specialty=None, num_questions=None)
                exam_questions = build_session_questions(exam_questions, shuffle_answers=True)
                start_session("practice", exam_questions)
                st.rerun()

    elif mode == "Practice by Tags":
        all_tags = get_all_tags()
        st.caption("Type one or more terms separated by spaces or commas.")
        st.caption("Example: T1DM, insulin or 2020 MS")

        tag_query = st.text_input(
            "Tag search",
            value=st.session_state.tag_query,
            placeholder="e.g. T1DM, insulin",
        )
        st.session_state.tag_query = tag_query

        if tag_query.strip():
            matches = [t for t in all_tags if tag_query.lower() in t.lower()][:30]
            if matches:
                st.write("Matching tags:")
                st.write(", ".join(matches))

        if st.button("Start Practice by Tags", use_container_width=True):
            pool = search_questions_by_tag_query(tag_query)

            if not pool:
                st.warning("No questions matched your tag search.")
            else:
                exam_questions = select_questions(pool, specialty=None, num_questions=None)
                exam_questions = build_session_questions(exam_questions, shuffle_answers=True)
                start_session("tags", exam_questions)
                st.rerun()

    elif mode == "Practice by Papers":
        paper_tags = list_paper_tags(questions)

        selected_papers = st.multiselect(
            "Select one or more papers (leave empty for all papers)",
            options=paper_tags,
            default=st.session_state.selected_papers,
        )
        st.session_state.selected_papers = selected_papers

        if st.button("Start Practice by Papers", use_container_width=True):
            if selected_papers:
                pool = paper_pool_from_selection(selected_papers)
            else:
                all_papers = list_paper_tags(questions)
                pool = paper_pool_from_selection(all_papers)

            if not pool:
                st.warning("No questions available for that paper selection.")
            else:
                exam_questions = select_questions(pool, specialty=None, num_questions=None)
                exam_questions = build_session_questions(exam_questions, shuffle_answers=True)
                start_session("paper", exam_questions)
                st.rerun()

    elif mode == "Mock Exam":
        paper_tags = list_paper_tags(questions)

        mock_paper = st.selectbox(
            "Select exactly one paper",
            options=paper_tags,
            index=0 if paper_tags else None,
        )
        st.session_state.mock_paper = mock_paper

        if mock_paper:
            pool = [q for q in questions if mock_paper in q.tags]
            allocated = get_mock_duration_secs(mock_paper, len(pool))
            st.caption(
                f"This recall pool has {len(pool)} questions. "
                f"Allocated mock time: {format_secs(allocated)}"
            )

        st.caption("No per-question feedback is shown during mock mode.")

        if st.button("Prepare Mock Exam", use_container_width=True):
            if not mock_paper:
                st.warning("Please select a paper.")
            else:
                pool = [q for q in questions if mock_paper in q.tags]
                if not pool:
                    st.warning(f"No questions found for '{mock_paper}'.")
                else:
                    exam_questions = select_questions(pool, specialty=None, num_questions=None)
                    exam_questions = build_session_questions(exam_questions, shuffle_answers=True)
                    st.session_state.mock_ready = True
                    st.session_state.mock_ready_questions = exam_questions
                    st.session_state.mock_ready_paper = mock_paper
                    st.rerun()

# ============================================================
# Active session
# ============================================================
elif st.session_state.started:
    exam_questions = st.session_state.exam_questions
    current_index = st.session_state.current_index
    mode = st.session_state.mode

    if not exam_questions:
        st.warning("No questions available.")
        if st.button("Return to Home"):
            reset_session_state_for_new_mode()
            st.rerun()
    else:
        total = len(exam_questions)

        if mode == "mock":
            render_mock_timer()

        progress_fraction = (current_index + 1) / total
        st.progress(progress_fraction)
        st.caption(f"Question {current_index + 1} of {total}")

        if mode != "mock" and st.session_state.results:
            correct_so_far, answered_so_far, percent_so_far = calculate_score(st.session_state.results)

            if percent_so_far >= 80:
                st.success(f"Current accuracy: {percent_so_far:.1f}% ({correct_so_far}/{answered_so_far})")
            elif percent_so_far >= 60:
                st.warning(f"Current accuracy: {percent_so_far:.1f}% ({correct_so_far}/{answered_so_far})")
            else:
                st.error(f"Current accuracy: {percent_so_far:.1f}% ({correct_so_far}/{answered_so_far})")

        q = exam_questions[current_index]
        option_labels, chosen_label = render_question(q, current_index + 1)

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Submit Answer", use_container_width=True, disabled=st.session_state.answer_submitted):
                if chosen_label is None:
                    st.warning("Please select an answer.")
                else:
                    chosen_index = option_labels.index(chosen_label)
                    is_correct = check_answer(q, chosen_index)

                    st.session_state.results.append(
                        QuestionResult(
                            question_id=q.id,
                            chosen_index=chosen_index,
                            was_correct=is_correct,
                        )
                    )
                    st.session_state.selected_option_index = chosen_index
                    st.session_state.answer_submitted = True
                    st.rerun()

        with col2:
            if st.button("Return to Home", use_container_width=True):
                reset_session_state_for_new_mode()
                st.rerun()

        if st.session_state.answer_submitted:
            chosen_index = st.session_state.selected_option_index
            is_correct = check_answer(q, chosen_index)
            correct_opt = q.options[q.correct_index]

            if mode in ("practice", "tags", "paper"):
                if is_correct:
                    st.success(f"Correct. Answer: {q.correct_index + 1}. {correct_opt}")
                else:
                    st.error(f"Incorrect. Correct answer: {q.correct_index + 1}. {correct_opt}")

                if q.explanation:
                    st.write("### Explanation")
                    st.write(q.explanation)
                
                if getattr(q, "explanation_image", None):
                    try:
                        st.image(q.explanation_image)
                    except Exception:
                        st.warning(f"Could not load explanation image: {q.explanation_image}")
                
                if getattr(q, "explanation_video", None):
                    try:
                        st.video(q.explanation_video)
                    except Exception:
                        st.warning(f"Could not load explanation video: {q.explanation_video}")
            else:
                st.info("Answer recorded.")

            next_label = "Finish" if current_index == total - 1 else "Next"

            if st.button(next_label, use_container_width=True):
                if current_index < total - 1:
                    go_to_next_question()
                else:
                    finish_session()
                st.rerun()

# ============================================================
# Session complete
# ============================================================
elif st.session_state.session_complete:
    correct, total, percent = calculate_score(st.session_state.results)
    mode = st.session_state.mode

    mode_name = {
        "practice": "Practice session complete",
        "tags": "Tag practice complete",
        "paper": "Paper practice complete",
        "mock": "Mock exam complete",
    }.get(mode or "", "Session complete")

    st.success(f"{mode_name}")
    st.write(f"### Score: {correct}/{total} ({percent:.1f}%)")

    if mode == "mock":
        wrong_items = get_wrong_items()

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Review Incorrect Questions", use_container_width=True, disabled=(len(wrong_items) == 0)):
                st.session_state.review_mode = True
                st.session_state.review_scope = "incorrect"
                st.session_state.review_index = 0
                st.session_state.session_complete = False
                st.rerun()

        with col2:
            if st.button("Review All Answers", use_container_width=True):
                st.session_state.review_mode = True
                st.session_state.review_scope = "all"
                st.session_state.review_index = 0
                st.session_state.session_complete = False
                st.rerun()

        with col3:
            if st.button("Return to Home", use_container_width=True):
                reset_session_state_for_new_mode()
                st.rerun()

        if not wrong_items:
            st.info("You answered all questions correctly.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Do Another Session", use_container_width=True):
                reset_session_state_for_new_mode()
                st.rerun()
        with col2:
            if st.button("Return to Home", use_container_width=True):
                reset_session_state_for_new_mode()
                st.rerun()

# ============================================================
# Review mode
# ============================================================
elif st.session_state.review_mode:
    review_items = get_review_items()

    if not review_items:
        st.info("No questions available to review.")
        if st.button("Return to Home", use_container_width=True):
            reset_session_state_for_new_mode()
            st.rerun()
    else:
        idx = st.session_state.review_index
        q, r = review_items[idx]

        review_title = "All Answers" if st.session_state.review_scope == "all" else "Incorrect Questions"
        st.subheader(f"Review: {review_title}")
        st.write(f"{idx + 1} of {len(review_items)}")
        st.write(f"[{q.specialty}]")
        st.write(q.stem)

        if q.image_path:
            try:
                st.image(q.image_path)
            except Exception:
                st.warning(f"Could not load image: {q.image_path}")

        if 0 <= r.chosen_index < len(q.options):
            your_answer = q.options[r.chosen_index]
            your_num = r.chosen_index + 1
        else:
            your_answer = "(No answer recorded)"
            your_num = "-"

        correct_answer = q.options[q.correct_index]
        was_correct = r.was_correct

        if was_correct:
            st.success("You answered this correctly.")
        else:
            st.error("You answered this incorrectly.")

        st.write(f"**Your answer:** {your_num}. {your_answer}")
        st.write(f"**Correct answer:** {q.correct_index + 1}. {correct_answer}")

        if q.explanation:
            st.write("### Explanation")
            st.write(q.explanation)

        if getattr(q, "explanation_image", None):
            try:
                st.image(q.explanation_image)
            except Exception:
                st.warning(f"Could not load explanation image: {q.explanation_image}")

        if getattr(q, "explanation_video", None):
            try:
                st.video(q.explanation_video)
            except Exception:
                st.warning(f"Could not load explanation video: {q.explanation_video}")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Previous", use_container_width=True, disabled=(idx == 0)):
                st.session_state.review_index -= 1
                st.rerun()

        with col2:
            if idx < len(review_items) - 1:
                if st.button("Next", use_container_width=True):
                    st.session_state.review_index += 1
                    st.rerun()
            else:
                if st.button("Finish Review", use_container_width=True):
                    reset_session_state_for_new_mode()
                    st.rerun()

        with col3:
            if st.button("Return to Results", use_container_width=True):
                st.session_state.review_mode = False
                st.session_state.session_complete = True
                st.rerun()