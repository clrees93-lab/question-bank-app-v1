import random
import time
from typing import List

import streamlit as st

# ============================================================
# Page setup
# Must come before other Streamlit commands
# ============================================================
st.set_page_config(
    page_title="BPT Question Bank",
    layout="wide",
)

from data_management import (
    load_questions_from_json,
    import_from_csv,
)

from logic import (
    QuestionResult,
    calculate_score,
    check_answer,
    list_paper_tags,
    select_questions,
)

from auth import (
    require_login,
    show_user_banner,
    show_logout_button,
)


# ============================================================
# Authentication
# ============================================================
require_login()
show_user_banner()
show_logout_button()


# ============================================================
# Data loading
# ============================================================
questions = load_questions_from_json()

# Sync CSV → JSON whenever the app starts/reruns
questions = import_from_csv(questions)


# ============================================================
# Page title
# ============================================================
st.title("BPT Question Bank")


# ============================================================
# Helper functions
# ============================================================

def list_specialties_local() -> List[str]:
    """
    Return all specialties in alphabetical order.
    """
    return sorted({
        q.specialty
        for q in questions
    })


def get_all_tags() -> List[str]:
    """
    Return all unique question tags in alphabetical order.
    """
    tag_set = set()

    for q in questions:
        for tag in q.tags:
            tag = (tag or "").strip()

            if tag:
                tag_set.add(tag)

    return sorted(tag_set)


def paper_pool_from_selection(
    selection: List[str]
):
    """
    Return questions belonging to any selected paper.
    """
    selected_set = set(selection)

    return [
        q
        for q in questions
        if any(
            tag in selected_set
            for tag in q.tags
        )
    ]


def format_secs(secs: int) -> str:
    """
    Convert seconds into HH:MM:SS.
    """
    secs = max(0, int(secs))

    hours = secs // 3600
    minutes = (secs % 3600) // 60
    seconds = secs % 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds:02d}"
    )


def get_mock_seconds_per_question(
    paper_tag: str
) -> float:
    """
    Calculate approximate exam time per question.

    CA:
        3 hours 10 minutes
        100 questions

    MS:
        2 hours 10 minutes
        70 questions
    """
    paper_tag = (
        paper_tag or ""
    ).upper()

    if paper_tag.endswith("CA"):
        return (
            (3 * 60 + 10) * 60 / 100
        )

    if paper_tag.endswith("MS"):
        return (
            (2 * 60 + 10) * 60 / 70
        )

    return 110.0


def get_mock_duration_secs(
    paper_tag: str,
    num_questions: int,
) -> int:
    """
    Calculate mock duration based on the
    number of available recall questions.
    """
    secs_per_q = (
        get_mock_seconds_per_question(
            paper_tag
        )
    )

    return max(
        60,
        round(
            num_questions * secs_per_q
        ),
    )


# ============================================================
# Session state helpers
# ============================================================

def reset_session_state_for_new_mode():
    """
    Reset all active question-session state.
    """

    st.session_state.exam_questions = []
    st.session_state.current_index = 0
    st.session_state.results = []

    st.session_state.started = False
    st.session_state.session_complete = False

    st.session_state.review_mode = False
    st.session_state.review_index = 0
    st.session_state.review_scope = (
        "incorrect"
    )

    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = (
        None
    )

    st.session_state.mode = None

    # ----------------------------
    # Mock-specific state
    # ----------------------------
    st.session_state.mock_start_time = None
    st.session_state.mock_duration_secs = None
    st.session_state.mock_paper_tag = None

    st.session_state.mock_ready = False
    st.session_state.mock_ready_questions = []
    st.session_state.mock_ready_paper = None


def start_session(
    mode: str,
    exam_questions: list,
    mock_paper_tag: str | None = None,
):
    """
    Start a new practice or mock session.
    """

    st.session_state.mode = mode

    st.session_state.exam_questions = (
        exam_questions
    )

    st.session_state.current_index = 0
    st.session_state.results = []

    st.session_state.started = True
    st.session_state.session_complete = False

    st.session_state.review_mode = False
    st.session_state.review_index = 0
    st.session_state.review_scope = (
        "incorrect"
    )

    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = (
        None
    )

    # ----------------------------
    # Mock-specific setup
    # ----------------------------
    if mode == "mock":

        st.session_state.mock_paper_tag = (
            mock_paper_tag
        )

        st.session_state.mock_duration_secs = (
            get_mock_duration_secs(
                mock_paper_tag or "",
                len(exam_questions),
            )
        )

        st.session_state.mock_start_time = (
            time.time()
        )

    else:

        st.session_state.mock_paper_tag = None
        st.session_state.mock_duration_secs = (
            None
        )
        st.session_state.mock_start_time = None

    # Clear mock preparation state
    st.session_state.mock_ready = False
    st.session_state.mock_ready_questions = []
    st.session_state.mock_ready_paper = None


def finish_session():
    """
    End the current question session.
    """

    st.session_state.session_complete = True
    st.session_state.started = False

    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = (
        None
    )


def go_to_next_question():
    """
    Move to the next question.
    """

    st.session_state.current_index += 1

    st.session_state.answer_submitted = False
    st.session_state.selected_option_index = (
        None
    )


# ============================================================
# Review helpers
# ============================================================

def get_wrong_items():
    """
    Return incorrect questions with their results.
    """

    wrong = []

    exam_questions = (
        st.session_state.exam_questions
    )

    results = st.session_state.results

    for q, result in zip(
        exam_questions,
        results,
    ):
        if not result.was_correct:
            wrong.append(
                (q, result)
            )

    return wrong


def get_review_items():
    """
    Return either all answered questions
    or only incorrect questions.
    """

    exam_questions = (
        st.session_state.exam_questions
    )

    results = st.session_state.results

    if (
        st.session_state.review_scope
        == "all"
    ):
        return list(
            zip(
                exam_questions,
                results,
            )
        )

    return get_wrong_items()


# ============================================================
# Question rendering
# ============================================================

def render_question(
    q,
    q_num: int,
):
    """
    Display one question and its answer options.
    """

    st.subheader(
        f"Q{q_num} [{q.specialty}]"
    )

    st.write(q.stem)

    # ----------------------------
    # Question image
    # ----------------------------
    if q.image_path:

        try:
            st.image(
                q.image_path
            )

        except Exception:
            st.warning(
                "Could not load image: "
                f"{q.image_path}"
            )

    # ----------------------------
    # Answer options
    # ----------------------------
    option_labels = [
        f"{i + 1}. {option}"
        for i, option
        in enumerate(q.options)
    ]

    chosen_label = st.radio(
        "Select your answer",
        option_labels,
        index=None,
        disabled=(
            st.session_state.answer_submitted
        ),
        key=(
            "question_radio_"
            f"{st.session_state.current_index}_"
            f"{st.session_state.mode}"
        ),
    )

    return (
        option_labels,
        chosen_label,
    )


# ============================================================
# Mock timer
# ============================================================

def get_mock_remaining_secs() -> int:
    """
    Calculate remaining mock exam time.
    """

    start = st.session_state.get(
        "mock_start_time"
    )

    duration = st.session_state.get(
        "mock_duration_secs"
    )

    if (
        start is None
        or duration is None
    ):
        return 0

    elapsed = int(
        time.time() - start
    )

    return duration - elapsed


def force_finish_mock_if_expired() -> bool:
    """
    Automatically finish the mock
    if its timer has expired.
    """

    if (
        st.session_state.mode != "mock"
        or not st.session_state.started
    ):
        return False

    remaining = (
        get_mock_remaining_secs()
    )

    if remaining <= 0:

        finish_session()

        return True

    return False


@st.fragment(run_every=1)
def render_mock_timer():
    """
    Display the live mock timer.
    """

    if (
        st.session_state.mode != "mock"
        or not st.session_state.started
    ):
        return

    remaining = (
        get_mock_remaining_secs()
    )

    paper_tag = st.session_state.get(
        "mock_paper_tag",
        "",
    )

    total_qs = len(
        st.session_state.get(
            "exam_questions",
            [],
        )
    )

    if remaining <= 0:

        st.error(
            "Time left: 00:00:00"
        )

        st.warning(
            "Time is up. Please move "
            "to the results screen."
        )

    else:

        st.info(
            f"Time left: "
            f"{format_secs(remaining)}"
            f"  |  Paper: {paper_tag}"
            f"  |  Questions: {total_qs}"
        )


# ============================================================
# Session question builder
# ============================================================

def build_session_questions(
    selected_questions: list,
    shuffle_answers: bool = True,
):
    """
    Make session-specific copies of questions.

    This allows answer options to be shuffled
    without modifying the original question bank.
    """

    session_questions = []

    for q in selected_questions:

        options = list(q.options)

        # ----------------------------
        # Shuffle answer options
        # ----------------------------
        if (
            shuffle_answers
            and len(options) > 1
        ):

            paired = [
                (
                    option,
                    index
                    == q.correct_index,
                )
                for index, option
                in enumerate(options)
            ]

            random.shuffle(paired)

            new_options = [
                option
                for option, _
                in paired
            ]

            new_correct_index = next(
                index
                for index, (
                    _,
                    is_correct,
                )
                in enumerate(paired)
                if is_correct
            )

        else:

            new_options = options

            new_correct_index = (
                q.correct_index
            )

        # ----------------------------
        # Create session copy
        # ----------------------------
        session_q = q.__class__(
            id=q.id,
            stem=q.stem,
            options=new_options,
            correct_index=(
                new_correct_index
            ),
            explanation=q.explanation,
            specialty=q.specialty,
            tags=list(q.tags),
            image_path=q.image_path,
            explanation_image=(
                q.explanation_image
            ),
            explanation_video=(
                q.explanation_video
            ),
        )

        session_questions.append(
            session_q
        )

    return session_questions


# ============================================================
# Session state initialisation
# ============================================================

if (
    "exam_questions"
    not in st.session_state
):
    reset_session_state_for_new_mode()


if (
    "selected_specialties"
    not in st.session_state
):
    st.session_state.selected_specialties = []


if (
    "selected_papers"
    not in st.session_state
):
    st.session_state.selected_papers = []


if (
    "mock_paper"
    not in st.session_state
):
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

    mock_paper = (
        st.session_state.mock_ready_paper
    )

    exam_questions = (
        st.session_state
        .mock_ready_questions
    )

    allocated = (
        get_mock_duration_secs(
            mock_paper or "",
            len(exam_questions),
        )
    )

    st.subheader(
        "Mock Exam Ready"
    )

    st.write(
        f"**Paper:** {mock_paper}"
    )

    st.write(
        "**Questions in this recall pool:** "
        f"{len(exam_questions)}"
    )

    st.write(
        "**Allocated time:** "
        f"{format_secs(allocated)}"
    )

    if (
        mock_paper or ""
    ).upper().endswith("CA"):

        st.caption(
            "CA timing is based on "
            "3 hours 10 minutes for "
            "100 questions."
        )

    elif (
        mock_paper or ""
    ).upper().endswith("MS"):

        st.caption(
            "MS timing is based on "
            "2 hours 10 minutes for "
            "70 questions."
        )

    st.warning(
        "The timer will begin only "
        "when you click "
        "'Begin Mock Exam'."
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "Begin Mock Exam",
            use_container_width=True,
        ):

            start_session(
                "mock",
                exam_questions,
                mock_paper,
            )

            st.rerun()

    with col2:

        if st.button(
            "Cancel and Return Home",
            use_container_width=True,
        ):

            reset_session_state_for_new_mode()

            st.rerun()


# ============================================================
# Home / mode selection
# ============================================================

elif (
    not st.session_state.started
    and not st.session_state.session_complete
    and not st.session_state.review_mode
):

    st.write(
        f"Loaded {len(questions)} questions."
    )

    mode = st.radio(
        "Choose mode",
        [
            "Practice Questions (by Specialty)",
            "Practice by Tags",
            "Practice by Papers",
            "Mock Exam",
        ],
    )

    # ========================================================
    # Practice by Specialty
    # ========================================================

    if (
        mode
        == "Practice Questions (by Specialty)"
    ):

        specialties = (
            list_specialties_local()
        )

        selected_specialties = st.multiselect(
            (
                "Select one or more specialties "
                "(leave empty for all specialties)"
            ),
            options=specialties,
            default=(
                st.session_state
                .selected_specialties
            ),
        )

        st.session_state.selected_specialties = (
            selected_specialties
        )

        if st.button(
            "Start Practice by Specialty",
            use_container_width=True,
        ):

            if selected_specialties:

                pool = [
                    q
                    for q in questions
                    if q.specialty
                    in selected_specialties
                ]

            else:

                pool = list(
                    questions
                )

            if not pool:

                st.warning(
                    "No questions available "
                    "for that selection."
                )

            else:

                exam_questions = (
                    select_questions(
                        pool,
                        specialty=None,
                        num_questions=None,
                    )
                )

                exam_questions = (
                    build_session_questions(
                        exam_questions,
                        shuffle_answers=True,
                    )
                )

                start_session(
                    "practice",
                    exam_questions,
                )

                st.rerun()


    # ========================================================
    # Practice by Tags
    # ========================================================

    elif mode == "Practice by Tags":

        all_tags = get_all_tags()

        selected_tags = st.multiselect(
            "Select one or more tags",
            options=all_tags,
            placeholder=(
                "Type to search tags..."
            ),
            key="selected_tags",
        )

        # --------------------------------
        # Find questions matching ANY tag
        # --------------------------------
        if selected_tags:

            selected_set = {
                tag.lower()
                for tag in selected_tags
            }

            pool = [
                q
                for q in questions
                if any(
                    tag.lower()
                    in selected_set
                    for tag in q.tags
                )
            ]

            st.caption(
                f"{len(pool)} question(s) "
                "match your selected tags."
            )

        else:

            pool = []

        # --------------------------------
        # Start tag practice
        # --------------------------------
        if st.button(
            "Start Practice by Tags",
            use_container_width=True,
        ):

            if not selected_tags:

                st.warning(
                    "Please select at least "
                    "one tag."
                )

            elif not pool:

                st.warning(
                    "No questions matched "
                    "your selected tags."
                )

            else:

                exam_questions = (
                    select_questions(
                        pool,
                        specialty=None,
                        num_questions=None,
                    )
                )

                exam_questions = (
                    build_session_questions(
                        exam_questions,
                        shuffle_answers=True,
                    )
                )

                start_session(
                    "tags",
                    exam_questions,
                )

                st.rerun()


    # ========================================================
    # Practice by Papers
    # ========================================================

    elif mode == "Practice by Papers":

        paper_tags = list_paper_tags(
            questions
        )

        selected_papers = st.multiselect(
            (
                "Select one or more papers "
                "(leave empty for all papers)"
            ),
            options=paper_tags,
            default=(
                st.session_state
                .selected_papers
            ),
        )

        st.session_state.selected_papers = (
            selected_papers
        )

        if st.button(
            "Start Practice by Papers",
            use_container_width=True,
        ):

            if selected_papers:

                pool = (
                    paper_pool_from_selection(
                        selected_papers
                    )
                )

            else:

                all_papers = (
                    list_paper_tags(
                        questions
                    )
                )

                pool = (
                    paper_pool_from_selection(
                        all_papers
                    )
                )

            if not pool:

                st.warning(
                    "No questions available "
                    "for that paper selection."
                )

            else:

                exam_questions = (
                    select_questions(
                        pool,
                        specialty=None,
                        num_questions=None,
                    )
                )

                exam_questions = (
                    build_session_questions(
                        exam_questions,
                        shuffle_answers=True,
                    )
                )

                start_session(
                    "paper",
                    exam_questions,
                )

                st.rerun()


    # ========================================================
    # Mock Exam
    # ========================================================

    elif mode == "Mock Exam":

        paper_tags = list_paper_tags(
            questions
        )

        mock_paper = st.selectbox(
            "Select exactly one paper",
            options=paper_tags,
            index=(
                0
                if paper_tags
                else None
            ),
        )

        st.session_state.mock_paper = (
            mock_paper
        )

        if mock_paper:

            pool = [
                q
                for q in questions
                if mock_paper
                in q.tags
            ]

            allocated = (
                get_mock_duration_secs(
                    mock_paper,
                    len(pool),
                )
            )

            st.caption(
                f"This recall pool has "
                f"{len(pool)} questions. "
                f"Allocated mock time: "
                f"{format_secs(allocated)}"
            )

        st.caption(
            "No per-question feedback "
            "is shown during mock mode."
        )

        if st.button(
            "Prepare Mock Exam",
            use_container_width=True,
        ):

            if not mock_paper:

                st.warning(
                    "Please select a paper."
                )

            else:

                pool = [
                    q
                    for q in questions
                    if mock_paper
                    in q.tags
                ]

                if not pool:

                    st.warning(
                        "No questions found "
                        f"for '{mock_paper}'."
                    )

                else:

                    exam_questions = (
                        select_questions(
                            pool,
                            specialty=None,
                            num_questions=None,
                        )
                    )

                    exam_questions = (
                        build_session_questions(
                            exam_questions,
                            shuffle_answers=True,
                        )
                    )

                    st.session_state.mock_ready = (
                        True
                    )

                    st.session_state.mock_ready_questions = (
                        exam_questions
                    )

                    st.session_state.mock_ready_paper = (
                        mock_paper
                    )

                    st.rerun()


# ============================================================
# Active session
# ============================================================

elif st.session_state.started:

    exam_questions = (
        st.session_state.exam_questions
    )

    current_index = (
        st.session_state.current_index
    )

    mode = st.session_state.mode

    if not exam_questions:

        st.warning(
            "No questions available."
        )

        if st.button(
            "Return to Home"
        ):

            reset_session_state_for_new_mode()

            st.rerun()

    else:

        total = len(
            exam_questions
        )

        # --------------------------------
        # Mock timer
        # --------------------------------
        if mode == "mock":
            render_mock_timer()

        # --------------------------------
        # Progress
        # --------------------------------
        progress_fraction = (
            (current_index + 1)
            / total
        )

        st.progress(
            progress_fraction
        )

        st.caption(
            f"Question "
            f"{current_index + 1} "
            f"of {total}"
        )

        # --------------------------------
        # Practice accuracy
        # --------------------------------
        if (
            mode != "mock"
            and st.session_state.results
        ):

            (
                correct_so_far,
                answered_so_far,
                percent_so_far,
            ) = calculate_score(
                st.session_state.results
            )

            accuracy_text = (
                f"Current accuracy: "
                f"{percent_so_far:.1f}% "
                f"({correct_so_far}/"
                f"{answered_so_far})"
            )

            if percent_so_far >= 80:

                st.success(
                    accuracy_text
                )

            elif percent_so_far >= 60:

                st.warning(
                    accuracy_text
                )

            else:

                st.error(
                    accuracy_text
                )

        # --------------------------------
        # Current question
        # --------------------------------
        q = exam_questions[
            current_index
        ]

        (
            option_labels,
            chosen_label,
        ) = render_question(
            q,
            current_index + 1,
        )

        # --------------------------------
        # Submit / Home buttons
        # --------------------------------
        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "Submit Answer",
                use_container_width=True,
                disabled=(
                    st.session_state
                    .answer_submitted
                ),
            ):

                if chosen_label is None:

                    st.warning(
                        "Please select "
                        "an answer."
                    )

                else:

                    chosen_index = (
                        option_labels.index(
                            chosen_label
                        )
                    )

                    is_correct = (
                        check_answer(
                            q,
                            chosen_index,
                        )
                    )

                    st.session_state.results.append(
                        QuestionResult(
                            question_id=q.id,
                            chosen_index=(
                                chosen_index
                            ),
                            was_correct=(
                                is_correct
                            ),
                        )
                    )

                    st.session_state.selected_option_index = (
                        chosen_index
                    )

                    st.session_state.answer_submitted = (
                        True
                    )

                    st.rerun()

        with col2:

            if st.button(
                "Return to Home",
                use_container_width=True,
            ):

                reset_session_state_for_new_mode()

                st.rerun()

        # --------------------------------
        # Feedback after submission
        # --------------------------------
        if (
            st.session_state
            .answer_submitted
        ):

            chosen_index = (
                st.session_state
                .selected_option_index
            )

            is_correct = check_answer(
                q,
                chosen_index,
            )

            correct_opt = (
                q.options[
                    q.correct_index
                ]
            )

            # --------------------------------
            # Practice-mode feedback
            # --------------------------------
            if mode in (
                "practice",
                "tags",
                "paper",
            ):

                if is_correct:

                    st.success(
                        "Correct. "
                        f"Answer: "
                        f"{q.correct_index + 1}. "
                        f"{correct_opt}"
                    )

                else:

                    st.error(
                        "Incorrect. "
                        "Correct answer: "
                        f"{q.correct_index + 1}. "
                        f"{correct_opt}"
                    )

                # ----------------------------
                # Written explanation
                # ----------------------------
                if q.explanation:

                    st.write(
                        "### Explanation"
                    )

                    st.write(
                        q.explanation
                    )

                # ----------------------------
                # Explanation image
                # ----------------------------
                if getattr(
                    q,
                    "explanation_image",
                    None,
                ):

                    try:

                        st.image(
                            q.explanation_image
                        )

                    except Exception:

                        st.warning(
                            "Could not load "
                            "explanation image: "
                            f"{q.explanation_image}"
                        )

                # ----------------------------
                # Explanation video
                # ----------------------------
                if getattr(
                    q,
                    "explanation_video",
                    None,
                ):

                    try:

                        st.video(
                            q.explanation_video
                        )

                    except Exception:

                        st.warning(
                            "Could not load "
                            "explanation video: "
                            f"{q.explanation_video}"
                        )

            # --------------------------------
            # Mock mode
            # --------------------------------
            else:

                st.info(
                    "Answer recorded."
                )

            # --------------------------------
            # Next / Finish
            # --------------------------------
            next_label = (
                "Finish"
                if current_index
                == total - 1
                else "Next"
            )

            if st.button(
                next_label,
                use_container_width=True,
            ):

                if (
                    current_index
                    < total - 1
                ):

                    go_to_next_question()

                else:

                    finish_session()

                st.rerun()


# ============================================================
# Session complete
# ============================================================

elif st.session_state.session_complete:

    (
        correct,
        total,
        percent,
    ) = calculate_score(
        st.session_state.results
    )

    mode = st.session_state.mode

    mode_name = {
        "practice": (
            "Practice session complete"
        ),
        "tags": (
            "Tag practice complete"
        ),
        "paper": (
            "Paper practice complete"
        ),
        "mock": (
            "Mock exam complete"
        ),
    }.get(
        mode or "",
        "Session complete",
    )

    st.success(
        mode_name
    )

    st.write(
        f"### Score: "
        f"{correct}/{total} "
        f"({percent:.1f}%)"
    )

    # ========================================================
    # Mock results
    # ========================================================

    if mode == "mock":

        wrong_items = (
            get_wrong_items()
        )

        col1, col2, col3 = (
            st.columns(3)
        )

        with col1:

            if st.button(
                "Review Incorrect Questions",
                use_container_width=True,
                disabled=(
                    len(wrong_items)
                    == 0
                ),
            ):

                st.session_state.review_mode = (
                    True
                )

                st.session_state.review_scope = (
                    "incorrect"
                )

                st.session_state.review_index = (
                    0
                )

                st.session_state.session_complete = (
                    False
                )

                st.rerun()

        with col2:

            if st.button(
                "Review All Answers",
                use_container_width=True,
            ):

                st.session_state.review_mode = (
                    True
                )

                st.session_state.review_scope = (
                    "all"
                )

                st.session_state.review_index = (
                    0
                )

                st.session_state.session_complete = (
                    False
                )

                st.rerun()

        with col3:

            if st.button(
                "Return to Home",
                use_container_width=True,
            ):

                reset_session_state_for_new_mode()

                st.rerun()

        if not wrong_items:

            st.info(
                "You answered all "
                "questions correctly."
            )

    # ========================================================
    # Practice results
    # ========================================================

    else:

        col1, col2 = (
            st.columns(2)
        )

        with col1:

            if st.button(
                "Do Another Session",
                use_container_width=True,
            ):

                reset_session_state_for_new_mode()

                st.rerun()

        with col2:

            if st.button(
                "Return to Home",
                use_container_width=True,
            ):

                reset_session_state_for_new_mode()

                st.rerun()


# ============================================================
# Review mode
# ============================================================

elif st.session_state.review_mode:

    review_items = (
        get_review_items()
    )

    if not review_items:

        st.info(
            "No questions available "
            "to review."
        )

        if st.button(
            "Return to Home",
            use_container_width=True,
        ):

            reset_session_state_for_new_mode()

            st.rerun()

    else:

        idx = (
            st.session_state
            .review_index
        )

        q, result = review_items[
            idx
        ]

        review_title = (
            "All Answers"
            if (
                st.session_state
                .review_scope
                == "all"
            )
            else "Incorrect Questions"
        )

        st.subheader(
            f"Review: {review_title}"
        )

        st.write(
            f"{idx + 1} "
            f"of {len(review_items)}"
        )

        st.write(
            f"[{q.specialty}]"
        )

        st.write(
            q.stem
        )

        # --------------------------------
        # Question image
        # --------------------------------
        if q.image_path:

            try:

                st.image(
                    q.image_path
                )

            except Exception:

                st.warning(
                    "Could not load image: "
                    f"{q.image_path}"
                )

        # --------------------------------
        # User answer
        # --------------------------------
        if (
            0
            <= result.chosen_index
            < len(q.options)
        ):

            your_answer = (
                q.options[
                    result.chosen_index
                ]
            )

            your_num = (
                result.chosen_index
                + 1
            )

        else:

            your_answer = (
                "(No answer recorded)"
            )

            your_num = "-"

        # --------------------------------
        # Correct answer
        # --------------------------------
        correct_answer = (
            q.options[
                q.correct_index
            ]
        )

        was_correct = (
            result.was_correct
        )

        if was_correct:

            st.success(
                "You answered this "
                "correctly."
            )

        else:

            st.error(
                "You answered this "
                "incorrectly."
            )

        st.write(
            "**Your answer:** "
            f"{your_num}. "
            f"{your_answer}"
        )

        st.write(
            "**Correct answer:** "
            f"{q.correct_index + 1}. "
            f"{correct_answer}"
        )

        # --------------------------------
        # Explanation
        # --------------------------------
        if q.explanation:

            st.write(
                "### Explanation"
            )

            st.write(
                q.explanation
            )

        # --------------------------------
        # Explanation image
        # --------------------------------
        if getattr(
            q,
            "explanation_image",
            None,
        ):

            try:

                st.image(
                    q.explanation_image
                )

            except Exception:

                st.warning(
                    "Could not load "
                    "explanation image: "
                    f"{q.explanation_image}"
                )

        # --------------------------------
        # Explanation video
        # --------------------------------
        if getattr(
            q,
            "explanation_video",
            None,
        ):

            try:

                st.video(
                    q.explanation_video
                )

            except Exception:

                st.warning(
                    "Could not load "
                    "explanation video: "
                    f"{q.explanation_video}"
                )

        # --------------------------------
        # Review navigation
        # --------------------------------
        col1, col2, col3 = (
            st.columns(3)
        )

        with col1:

            if st.button(
                "Previous",
                use_container_width=True,
                disabled=(
                    idx == 0
                ),
            ):

                st.session_state.review_index -= 1

                st.rerun()

        with col2:

            if (
                idx
                < len(review_items) - 1
            ):

                if st.button(
                    "Next",
                    use_container_width=True,
                ):

                    st.session_state.review_index += 1

                    st.rerun()

            else:

                if st.button(
                    "Finish Review",
                    use_container_width=True,
                ):

                    reset_session_state_for_new_mode()

                    st.rerun()

        with col3:

            if st.button(
                "Return to Results",
                use_container_width=True,
            ):

                st.session_state.review_mode = (
                    False
                )

                st.session_state.session_complete = (
                    True
                )

                st.rerun()