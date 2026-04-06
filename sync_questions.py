from data_management import load_questions_from_json, import_from_csv

def main():
    questions = load_questions_from_json()
    questions = import_from_csv(questions)
    print(f"Question bank synced. Total questions: {len(questions)}")

if __name__ == "__main__":
    main()
