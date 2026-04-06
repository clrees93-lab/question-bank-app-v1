# gui_app.py
# ----------
# Tkinter GUI for your BPT question bank.
#
# HOME SCREEN MODES:
#   - Practice Questions (by Specialty) → choose one/many specialties (or all), immediate feedback + explanation
#   - Practice by Tags                  → search tags with live suggestions, immediate feedback + explanation
#   - Practice by Papers                → choose one/many papers (or all papers), immediate feedback + explanation
#   - Mock Exam                         → choose exactly ONE paper, 3-hour timer, NO per-question feedback, score at end,
#                                          with optional review of incorrect questions.
#
# Images:
#   - If Question.image_path is set (e.g. "images/q0001.png") and exists,
#     the image will be shown under the question stem in all modes.
#
# Review behaviour:
#   - After a mock exam, if you choose to review, a dedicated window opens.
#   - It shows incorrect questions one-by-one with:
#       * stem
#       * your answer
#       * correct answer
#       * explanation
#     and buttons:
#       * "Next" / "Finish"
#       * "Return to Home"

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional
import os
import re

from PIL import Image, ImageTk

from data_management import (
    Question,
    load_questions_from_json,
    list_specialties,
    import_from_csv,   # sync CSV → JSON on startup
)
from logic import (
    QuestionResult,
    select_questions,
    check_answer,
    calculate_score,
    list_paper_tags,
)


class MockExamGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("BPT Question Bank")

        # Load all questions once at startup
        self.questions: List[Question] = load_questions_from_json()

        # Sync from CSV into JSON at startup (if questions.csv exists)
        self.questions = import_from_csv(self.questions)

        # State for a running session (practice / tags / paper / mock)
        self.exam_questions: List[Question] = []
        self.current_index: int = 0
        self.results: List[QuestionResult] = []
        self.mode: Optional[str] = None  # "practice", "tags", "paper", "mock"

        # Timer state (for mock exams only)
        self.time_remaining_secs: int = 0
        self.timer_active: bool = False

        # For image display
        self.current_image = None  # keep reference to avoid GC

        # ---------------------------------------------------
        # 1) HOME SCREEN
        # ---------------------------------------------------
        self.home_frame = ttk.Frame(root, padding=20)
        title_label = ttk.Label(
            self.home_frame,
            text="BPT Question Bank",
            font=("TkDefaultFont", 16, "bold"),
        )
        title_label.pack(pady=(0, 10))

        subtitle_label = ttk.Label(
            self.home_frame,
            text="Choose a mode:",
        )
        subtitle_label.pack(pady=(0, 15))

        practice_btn = ttk.Button(
            self.home_frame,
            text="Practice Questions (by Specialty)",
            command=self.start_practice_questions,
            width=30,
        )
        practice_btn.pack(pady=5)

        tags_btn = ttk.Button(
            self.home_frame,
            text="Practice by Tags",
            command=self.start_practice_by_tags,
            width=30,
        )
        tags_btn.pack(pady=5)

        papers_btn = ttk.Button(
            self.home_frame,
            text="Practice by Papers",
            command=self.start_practice_by_papers,
            width=30,
        )
        papers_btn.pack(pady=5)

        mock_btn = ttk.Button(
            self.home_frame,
            text="Mock Exam",
            command=self.start_mock_exam,
            width=30,
        )
        mock_btn.pack(pady=5)

        quit_btn = ttk.Button(
            self.home_frame,
            text="Quit",
            command=self.root.destroy,
            width=30,
        )
        quit_btn.pack(pady=(20, 0))

        # ---------------------------------------------------
        # 2) QUESTION FRAME (shared by all modes)
        # ---------------------------------------------------
        self.question_frame = ttk.Frame(root, padding=10)

        self.question_label = ttk.Label(
            self.question_frame,
            text="",
            wraplength=600,
            justify="left",
        )
        self.question_label.pack(anchor="w", pady=(0, 10))

        # Image label (optional per question)
        self.image_label = ttk.Label(self.question_frame)
        self.image_label.pack(anchor="w", pady=(0, 10))

        self.selected_option = tk.IntVar(value=-1)
        self.option_buttons: List[ttk.Radiobutton] = []
        for i in range(8):
            rb = ttk.Radiobutton(
                self.question_frame,
                text="",
                variable=self.selected_option,
                value=i,
            )
            rb.pack(anchor="w")
            self.option_buttons.append(rb)

        # ---------------------------------------------------
        # 3) NAVIGATION FRAME (bottom bar)
        # ---------------------------------------------------
        self.nav_frame = ttk.Frame(root, padding=10)

        self.timer_label = ttk.Label(self.nav_frame, text="")
        self.timer_label.pack(side="left", padx=10)

        self.home_button = ttk.Button(
            self.nav_frame,
            text="Back to Home",
            command=self.show_home,
        )
        self.home_button.pack(side="left")

        self.next_button = ttk.Button(
            self.nav_frame,
            text="Next",
            command=self.submit_and_next,
            state="disabled",
        )
        self.next_button.pack(side="right")

        # Start on home
        self.show_home()

    # =====================================================
    # Helpers: tags, specialties, papers
    # =====================================================
    def get_all_tags(self) -> List[str]:
        """
        Return a sorted list of all unique tags across the question bank.
        """
        tag_set = set()
        for q in self.questions:
            for t in q.tags:
                t = t.strip()
                if t:
                    tag_set.add(t)
        return sorted(tag_set)

    def search_questions_by_tag_query(self, query: str) -> List[Question]:
        """
        Filter questions by a free-text query over tags.

        Behaviour:
          - query is split on commas and whitespace
          - each token is lowercased
          - a question matches if ANY token is a substring of ANY of its tags (case-insensitive)

        Example:
          query = "T1DM, insulin"
          → tokens = ["t1dm", "insulin"]
          → match if a tag contains "t1dm" or "insulin".
        """
        tokens = [
            tok.strip().lower()
            for tok in re.split(r"[,\s]+", query)
            if tok.strip()
        ]
        if not tokens:
            return []

        results: List[Question] = []
        for q in self.questions:
            tags_lower = [t.lower() for t in q.tags]
            if any(any(token in tag for tag in tags_lower) for token in tokens):
                results.append(q)

        return results

    # =====================================================
    # Specialty selection via checkboxes (with All)
    # =====================================================
    def choose_specialties_gui(self) -> Optional[List[str]]:
        """
        Show a modal window with checkboxes for specialties and an
        'All specialties' option.

        Returns:
          - None      → user cancelled (do NOT start questions)
          - []        → All specialties
          - [list...] → selected specialties
        """
        specs = list_specialties(self.questions)
        if not specs:
            return []

        top = tk.Toplevel(self.root)
        top.title("Choose specialties")
        top.transient(self.root)
        top.grab_set()  # modal

        label = ttk.Label(
            top,
            text="Select one or more specialties to practice,\n"
                 "or tick 'All specialties'.",
            justify="left",
        )
        label.pack(padx=10, pady=(10, 5), anchor="w")

        specs_frame = ttk.Frame(top, padding=(10, 0, 10, 5))
        specs_frame.pack(fill="both", expand=True)

        spec_vars: dict[str, tk.BooleanVar] = {}
        for s in specs:
            var = tk.BooleanVar(value=False)
            spec_vars[s] = var

        all_var = tk.BooleanVar(value=True)

        def on_spec_toggled():
            # Any individual → uncheck All
            if any(v.get() for v in spec_vars.values()):
                all_var.set(False)

        def on_all_toggled():
            # All checked → uncheck individuals
            if all_var.get():
                for v in spec_vars.values():
                    v.set(False)

        for s, var in spec_vars.items():
            chk = ttk.Checkbutton(
                specs_frame,
                text=s,
                variable=var,
                command=on_spec_toggled,
            )
            chk.pack(anchor="w")

        all_chk = ttk.Checkbutton(
            top,
            text="All specialties",
            variable=all_var,
            command=on_all_toggled,
        )
        all_chk.pack(padx=10, pady=(5, 5), anchor="w")

        result: dict[str, Optional[List[str]]] = {"value": None}

        def on_start():
            if all_var.get():
                result["value"] = []
                top.destroy()
                return
            selected = [s for s, v in spec_vars.items() if v.get()]
            if not selected:
                messagebox.showwarning(
                    "No selection",
                    "Select at least one specialty or choose 'All specialties'.",
                    parent=top,
                )
                return
            result["value"] = selected
            top.destroy()

        def on_cancel():
            result["value"] = None
            top.destroy()

        btn_frame = ttk.Frame(top, padding=(10, 10))
        btn_frame.pack(fill="x")
        start_btn = ttk.Button(btn_frame, text="Start", command=on_start)
        start_btn.pack(side="right", padx=5)
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right")

        # Position near main window
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + 50
        y = self.root.winfo_rooty() + 50
        top.geometry(f"+{x}+{y}")

        self.root.wait_window(top)
        return result["value"]

    # =====================================================
    # Tag search dialog with live suggestions
    # =====================================================
    def ask_tag_search_gui(self) -> Optional[str]:
        """
        Show a modal dialog asking for a free-text tag search query,
        with live tag suggestions as you type.

        Returns:
          - None  → user cancelled
          - str   → search query (non-empty)
        """
        top = tk.Toplevel(self.root)
        top.title("Search by tags")
        top.transient(self.root)
        top.grab_set()  # modal

        all_tags = self.get_all_tags()

        label = ttk.Label(
            top,
            text=(
                "Type one or more terms to search in tags.\n"
                "Examples:\n"
                "  T1DM\n"
                "  insulin, ketoacidosis\n"
                "  2020 MS\n"
                "\n"
                "Suggestions update as you type; double-click a tag\n"
                "to use it immediately."
            ),
            justify="left",
        )
        label.pack(padx=10, pady=(10, 5), anchor="w")

        entry = ttk.Entry(top, width=50)
        entry.pack(padx=10, pady=(5, 5), fill="x")
        entry.focus_set()

        sugg_label = ttk.Label(top, text="Matching tags:")
        sugg_label.pack(padx=10, pady=(5, 0), anchor="w")

        sugg_frame = ttk.Frame(top)
        sugg_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)

        sugg_listbox = tk.Listbox(sugg_frame, height=8, exportselection=False)
        sugg_listbox.pack(side="left", fill="both", expand=True)

        sugg_scroll = ttk.Scrollbar(sugg_frame, orient="vertical", command=sugg_listbox.yview)
        sugg_scroll.pack(side="right", fill="y")
        sugg_listbox.config(yscrollcommand=sugg_scroll.set)

        result: dict[str, Optional[str]] = {"value": None}

        def update_suggestions(*args) -> None:
            """
            Update the suggestion list based on the current entry text.

            - If entry is empty → show all tags (capped).
            - Else → show tags containing the typed text (case-insensitive).
            """
            text = entry.get().strip().lower()
            sugg_listbox.delete(0, tk.END)

            if not all_tags:
                return

            if not text:
                to_show = all_tags[:100]
            else:
                matches = [t for t in all_tags if text in t.lower()]
                to_show = matches[:100]

            for t in to_show:
                sugg_listbox.insert(tk.END, t)

        def on_start() -> None:
            q = entry.get().strip()
            if not q:
                messagebox.showwarning(
                    "Empty search",
                    "Please enter at least one search term.",
                    parent=top,
                )
                return
            result["value"] = q
            top.destroy()

        def on_cancel() -> None:
            result["value"] = None
            top.destroy()

        def use_selected_and_start(event=None) -> None:
            """
            Use the selected suggestion as the full query
            and immediately run the search.
            """
            selection = sugg_listbox.curselection()
            if not selection:
                return
            tag = sugg_listbox.get(selection[0])
            entry.delete(0, tk.END)
            entry.insert(0, tag)
            on_start()

        # Wire up events
        entry.bind("<KeyRelease>", lambda event: update_suggestions())
        entry.bind("<Return>", lambda event: on_start())

        sugg_listbox.bind("<Double-Button-1>", use_selected_and_start)
        sugg_listbox.bind("<Return>", use_selected_and_start)

        # Buttons at the bottom
        btn_frame = ttk.Frame(top, padding=(10, 10))
        btn_frame.pack(fill="x")
        start_btn = ttk.Button(btn_frame, text="Search", command=on_start)
        start_btn.pack(side="right", padx=5)
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right")

        # Position near main window
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + 50
        y = self.root.winfo_rooty() + 50
        top.geometry(f"+{x}+{y}")

        # Initial suggestion list
        update_suggestions()

        self.root.wait_window(top)
        return result["value"]

    # =====================================================
    # Paper selection via checkboxes (practice vs mock)
    # =====================================================
    def choose_papers_gui(
        self,
        allow_multiple: bool,
        allow_all: bool,
        title: str,
        prompt: str,
    ) -> Optional[List[str]]:
        """
        Generic checkbox dialog for paper selection.

        Returns:
          - None      → user cancelled
          - []        → All papers (if allow_all=True)
          - [list...] → selected paper tags
        """
        paper_tags = list_paper_tags(self.questions)
        if not paper_tags:
            messagebox.showwarning("No papers", "No tags of the form 'YYYY MS' or 'YYYY CA' found.")
            return None

        top = tk.Toplevel(self.root)
        top.title(title)
        top.transient(self.root)
        top.grab_set()

        label = ttk.Label(top, text=prompt, justify="left")
        label.pack(padx=10, pady=(10, 5), anchor="w")

        papers_frame = ttk.Frame(top, padding=(10, 0, 10, 5))
        papers_frame.pack(fill="both", expand=True)

        paper_vars: dict[str, tk.BooleanVar] = {}
        for tag in paper_tags:
            var = tk.BooleanVar(value=False)
            paper_vars[tag] = var

        all_var = tk.BooleanVar(value=True if allow_all else False)

        def on_paper_toggled():
            if allow_all and any(v.get() for v in paper_vars.values()):
                all_var.set(False)

        def on_all_toggled():
            if allow_all and all_var.get():
                for v in paper_vars.values():
                    v.set(False)

        for tag, var in paper_vars.items():
            chk = ttk.Checkbutton(
                papers_frame,
                text=tag,
                variable=var,
                command=on_paper_toggled,
            )
            chk.pack(anchor="w")

        if allow_all:
            all_chk = ttk.Checkbutton(
                top,
                text="All papers",
                variable=all_var,
                command=on_all_toggled,
            )
            all_chk.pack(padx=10, pady=(5, 5), anchor="w")

        result: dict[str, Optional[List[str]]] = {"value": None}

        def on_start():
            if allow_all and all_var.get():
                result["value"] = []
                top.destroy()
                return

            selected = [tag for tag, v in paper_vars.items() if v.get()]
            if not selected:
                messagebox.showwarning(
                    "No selection",
                    "Select at least one paper"
                    + (" or choose 'All papers'." if allow_all else "."),
                    parent=top,
                )
                return

            if not allow_multiple and len(selected) != 1:
                messagebox.showwarning(
                    "Invalid selection",
                    "Please select exactly one paper.",
                    parent=top,
                )
                return

            result["value"] = selected
            top.destroy()

        def on_cancel():
            result["value"] = None
            top.destroy()

        btn_frame = ttk.Frame(top, padding=(10, 10))
        btn_frame.pack(fill="x")
        start_btn = ttk.Button(btn_frame, text="Start", command=on_start)
        start_btn.pack(side="right", padx=5)
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel)
        cancel_btn.pack(side="right")

        self.root.update_idletasks()
        x = self.root.winfo_rootx() + 50
        y = self.root.winfo_rooty() + 50
        top.geometry(f"+{x}+{y}")

        self.root.wait_window(top)
        return result["value"]

    # =====================================================
    # Layout: show home vs show exam view
    # =====================================================
    def show_home(self) -> None:
        """Show home screen and reset session state."""
        # Unbind Enter from Next when back at home
        self.root.unbind("<Return>")

        self.exam_questions = []
        self.results = []
        self.current_index = 0
        self.mode = None

        self.timer_active = False
        self.timer_label.config(text="")

        self.question_frame.pack_forget()
        self.nav_frame.pack_forget()

        self.home_frame.pack(fill="both", expand=True)

    def show_exam_area(self) -> None:
        """Show question view and nav bar, hide home."""
        self.home_frame.pack_forget()
        self.question_frame.pack(fill="both", expand=True)
        self.nav_frame.pack(fill="x")

        # Bind Return/Enter to Next/Finish button while in-question
        self.root.bind("<Return>", lambda event: self.submit_and_next())

    # =====================================================
    # Mode-specific starters
    # =====================================================
    def start_practice_questions(self) -> None:
        """Practice mode by specialties, with explanations."""
        if not self.questions:
            messagebox.showwarning("No questions", "No questions found in questions.json.")
            return

        selection = self.choose_specialties_gui()
        if selection is None:
            self.show_home()
            return

        if selection == []:
            pool = list(self.questions)
        else:
            pool = [q for q in self.questions if q.specialty in selection]

        if not pool:
            messagebox.showwarning("No questions", "No questions available for that choice.")
            return

        self.mode = "practice"
        self.exam_questions = select_questions(pool, specialty=None, num_questions=None)

        self.current_index = 0
        self.results = []
        self.next_button.config(text="Next", state="normal")

        self.show_exam_area()
        self.show_current_question()

    def start_practice_by_tags(self) -> None:
        """Practice mode by tags, with explanations using search + suggestions."""
        if not self.questions:
            messagebox.showwarning("No questions", "No questions found in questions.json.")
            return

        query = self.ask_tag_search_gui()
        if query is None:
            self.show_home()
            return

        pool = self.search_questions_by_tag_query(query)
        if not pool:
            messagebox.showwarning(
                "No questions",
                "No questions matched your tag search. Try different terms.",
            )
            return

        self.mode = "tags"
        self.exam_questions = select_questions(pool, specialty=None, num_questions=None)

        self.current_index = 0
        self.results = []
        self.next_button.config(text="Next", state="normal")

        self.show_exam_area()
        self.show_current_question()

    def start_practice_by_papers(self) -> None:
        """Practice mode by paper tag(s), with explanations."""
        if not self.questions:
            messagebox.showwarning("No questions", "No questions found in questions.json.")
            return

        selection = self.choose_papers_gui(
            allow_multiple=True,
            allow_all=True,
            title="Choose papers",
            prompt="Select one or more papers to practice,\n"
                   "or tick 'All papers'.",
        )
        if selection is None:
            self.show_home()
            return

        if selection == []:
            paper_tags = set(list_paper_tags(self.questions))
            pool = [
                q for q in self.questions
                if any(tag in paper_tags for tag in q.tags)
            ]
        else:
            selected_set = set(selection)
            pool = [
                q for q in self.questions
                if any(tag in selected_set for tag in q.tags)
            ]

        if not pool:
            messagebox.showwarning("No questions", "No questions available for that paper selection.")
            return

        self.mode = "paper"
        self.exam_questions = select_questions(pool, specialty=None, num_questions=None)

        self.current_index = 0
        self.results = []
        self.next_button.config(text="Next", state="normal")

        self.show_exam_area()
        self.show_current_question()

    def start_mock_exam(self) -> None:
        """
        Mock exam:
          - choose exactly one paper
          - 3-hour timer
          - no per-question feedback
          - optional review of incorrect questions at end
        """
        if not self.questions:
            messagebox.showwarning("No questions", "No questions found in questions.json.")
            return

        selection = self.choose_papers_gui(
            allow_multiple=False,
            allow_all=False,
            title="Choose mock exam paper",
            prompt="Select exactly one paper for the mock exam.",
        )
        if selection is None:
            self.show_home()
            return

        paper_tag = selection[0]
        pool = [q for q in self.questions if paper_tag in q.tags]

        if not pool:
            messagebox.showwarning("No questions", f"No questions found for '{paper_tag}'.")
            return

        self.mode = "mock"
        self.exam_questions = select_questions(pool, specialty=None, num_questions=None)

        self.current_index = 0
        self.results = []
        self.next_button.config(text="Next", state="normal")

        self.show_exam_area()
        self.show_current_question()

        # Start 3-hour timer
        self.start_timer(3 * 60 * 60)

    # =====================================================
    # Timer helpers (mock exam only)
    # =====================================================
    def start_timer(self, seconds: int) -> None:
        self.time_remaining_secs = seconds
        self.timer_active = True
        self.update_timer()

    def update_timer(self) -> None:
        if not self.timer_active:
            return

        if self.time_remaining_secs <= 0:
            self.timer_label.config(text="Time left: 00:00:00")
            self.timer_active = False
            self.on_time_up()
            return

        hours = self.time_remaining_secs // 3600
        minutes = (self.time_remaining_secs % 3600) // 60
        seconds = self.time_remaining_secs % 60

        self.timer_label.config(
            text=f"Time left: {hours:02d}:{minutes:02d}:{seconds:02d}"
        )

        self.time_remaining_secs -= 1
        self.root.after(1000, self.update_timer)

    def on_time_up(self) -> None:
        """Called automatically when mock exam timer expires."""
        if not self.exam_questions or self.mode != "mock":
            return

        messagebox.showinfo("Time's up", "The 3-hour mock exam time has elapsed.")
        self.finish_session_and_maybe_review()

    # =====================================================
    # Review for mock exam
    # =====================================================
    def review_incorrect_questions(self) -> None:
        """
        Show incorrect mock-exam questions in a dedicated window:
          - stem
          - your answer
          - correct answer
          - explanation
        With:
          - Next / Finish button
          - Return to Home button
        """
        wrong = [
            (q, r)
            for q, r in zip(self.exam_questions, self.results)
            if not r.was_correct
        ]

        if not wrong:
            messagebox.showinfo(
                "Review",
                "You answered all questions correctly – nothing to review."
            )
            self.show_home()
            return

        total_wrong = len(wrong)

        top = tk.Toplevel(self.root)
        top.title("Review incorrect questions")
        top.transient(self.root)
        top.grab_set()

        content_label = ttk.Label(
            top,
            text="",
            wraplength=600,
            justify="left",
            anchor="w",
        )
        content_label.pack(padx=10, pady=10, fill="both", expand=True)

        btn_frame = ttk.Frame(top, padding=(10, 10))
        btn_frame.pack(fill="x")

        next_btn = ttk.Button(btn_frame, text="Next")
        next_btn.pack(side="right", padx=5)

        home_btn = ttk.Button(btn_frame, text="Return to Home")
        home_btn.pack(side="right")

        idx = 0  # index into wrong list

        def update_view() -> None:
            nonlocal idx
            q, r = wrong[idx]

            if 0 <= r.chosen_index < len(q.options):
                your_answer = q.options[r.chosen_index]
            else:
                your_answer = "(No answer recorded)"

            correct_answer = q.options[q.correct_index]

            text = (
                f"{idx + 1}/{total_wrong}\n\n"
                f"Q [{q.specialty}]\n"
                f"{q.stem}\n\n"
                f"Your answer:\n{your_answer}\n\n"
                f"Correct answer:\n{correct_answer}\n"
            )
            if q.explanation:
                text += f"\nExplanation:\n{q.explanation}"

            content_label.config(text=text)

            if idx == total_wrong - 1:
                next_btn.config(text="Finish")
            else:
                next_btn.config(text="Next")

        def on_next() -> None:
            nonlocal idx
            if idx < total_wrong - 1:
                idx += 1
                update_view()
            else:
                top.destroy()
                self.show_home()

        def on_home() -> None:
            top.destroy()
            self.show_home()

        next_btn.config(command=on_next)
        home_btn.config(command=on_home)
        top.protocol("WM_DELETE_WINDOW", on_home)

        update_view()

    # =====================================================
    # Question display + navigation
    # =====================================================
    def show_current_question(self) -> None:
        """Display the current question in the main question frame."""
        q = self.exam_questions[self.current_index]
        header = f"Q{self.current_index + 1} [{q.specialty}]"
        self.question_label.config(text=f"{header}\n\n{q.stem}")

        # --- Image handling ---
        if q.image_path:
            path = q.image_path
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    # resize to max width to fit nicely
                    max_width = 600
                    w, h = img.size
                    if w > max_width:
                        new_h = int(h * (max_width / w))
                        img = img.resize((max_width, new_h), Image.LANCZOS)
                    self.current_image = ImageTk.PhotoImage(img)
                    self.image_label.config(image=self.current_image)
                    self.image_label.pack(anchor="w", pady=(0, 10))
                except Exception as e:
                    print(f"Could not load image for question {q.id}: {e}")
                    self.image_label.config(image="")
                    self.image_label.pack_forget()
            else:
                # Path doesn't exist on disk
                self.image_label.config(image="")
                self.image_label.pack_forget()
        else:
            # No image for this question
            self.image_label.config(image="")
            self.image_label.pack_forget()

        # --- Options ---
        self.selected_option.set(-1)

        for i, rb in enumerate(self.option_buttons):
            if i < len(q.options):
                rb.config(text=q.options[i])
                rb.pack(anchor="w")
            else:
                rb.pack_forget()

        if self.current_index == len(self.exam_questions) - 1:
            self.next_button.config(text="Finish")
        else:
            self.next_button.config(text="Next")

    def submit_and_next(self) -> None:
        """Handle Next/Finish click: record answer, feedback (if practice), move on or finish."""
        if not self.exam_questions:
            return

        chosen = self.selected_option.get()
        if chosen < 0:
            messagebox.showwarning("No answer", "Please select an answer.")
            return

        q = self.exam_questions[self.current_index]
        is_correct = check_answer(q, chosen)

        self.results.append(
            QuestionResult(
                question_id=q.id,
                chosen_index=chosen,
                was_correct=is_correct,
            )
        )

        # Practice modes → immediate feedback with explanation
        if self.mode in ("practice", "tags", "paper"):
            correct_opt = q.options[q.correct_index]
            if is_correct:
                msg = f"✅ Correct.\n\nAnswer: {q.correct_index + 1}. {correct_opt}"
            else:
                msg = f"❌ Incorrect.\n\nCorrect answer: {q.correct_index + 1}. {correct_opt}"
            if q.explanation:
                msg += f"\n\nExplanation:\n{q.explanation}"
            messagebox.showinfo("Result", msg)

        # Move to next question or end
        if self.current_index < len(self.exam_questions) - 1:
            self.current_index += 1
            self.show_current_question()
        else:
            self.timer_active = False
            self.finish_session_and_maybe_review()

    def finish_session_and_maybe_review(self) -> None:
        """
        Called when any mode finishes.
        - Shows score.
        - For mock: offers review, else home.
        - For practice modes: loops back to selection screens.
        """
        correct, total, percent = calculate_score(self.results)
        mode_name = {
            "practice": "Practice session complete",
            "tags": "Tag practice complete",
            "paper": "Paper practice complete",
            "mock": "Mock exam complete",
        }.get(self.mode or "", "Session complete")

        msg = f"{mode_name}\n\nScore: {correct}/{total} ({percent:.1f}%)"
        messagebox.showinfo("Session complete", msg)

        self.next_button.config(state="disabled")

        if self.mode == "mock":
            wrong_count = sum(1 for r in self.results if not r.was_correct)
            if wrong_count > 0:
                do_review = messagebox.askyesno(
                    "Review incorrect questions?",
                    f"You answered {wrong_count} question(s) incorrectly.\n\n"
                    "Would you like to review them now?",
                )
                if do_review:
                    self.review_incorrect_questions()
                    return
            self.show_home()
        elif self.mode == "practice":
            self.start_practice_questions()
        elif self.mode == "tags":
            self.start_practice_by_tags()
        elif self.mode == "paper":
            self.start_practice_by_papers()
        else:
            self.show_home()


if __name__ == "__main__":
    root = tk.Tk()
    app = MockExamGUI(root)
    root.mainloop()
