#!/usr/bin/env python3
import os
import sys
import json
import csv
import argparse
import subprocess
from pathlib import Path

# Set up working directory to be the directory containing this script
current_dir = Path(__file__).resolve().parent
os.chdir(current_dir)

def run_cmd(cmd, check=True):
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print("Error/Warning output:", res.stderr)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}")
    return res

def convert_jsonl_to_csv(jsonl_path, csv_path):
    print(f"Converting {jsonl_path} to CSV format: {csv_path}")
    if not os.path.exists(jsonl_path):
        print(f"Error: {jsonl_path} does not exist. Cannot convert to CSV.")
        return False
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f_in, open(csv_path, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["question_id", "answer"])
            for line in f_in:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    writer.writerow([item.get("qid"), item.get("answer")])
                except json.JSONDecodeError as je:
                    print(f"Warning: failed to decode line: {line}. Error: {je}")
        return True
    except Exception as e:
        print(f"Error during CSV conversion: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run Vishrut Pipeline")
    parser.add_argument(
        "--questions", 
        default="../sample_questions.json", 
        help="Path to questions JSON file (default: ../sample_questions.json)"
    )
    args = parser.parse_args()

    print("=== Step 1: Install Requirements ===")
    run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    run_cmd([sys.executable, "-m", "pip", "install", "python-dotenv", "openai"])
    
    print("\n=== Step 2: Build Database ===")
    run_cmd([sys.executable, "graph/build_db.py", "--db", "graph.sqlite"])
    
    print(f"\n=== Step 3: Convert {args.questions} to questions.jsonl ===")
    src_questions = Path(args.questions)
    out_questions = Path("questions.jsonl")
    
    if not src_questions.exists():
        print(f"Error: {src_questions} does not exist!")
        sys.exit(1)
        
    with open(src_questions, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    questions = data.get("questions", data.get("answers", []))
    print(f"Loaded {len(questions)} questions from {src_questions}")
    
    with open(out_questions, "w", encoding="utf-8") as f:
        for q in questions:
            json.dump({"qid": q["qid"], "question": q["question"]}, f)
            f.write("\n")
    print(f"Wrote questions to {out_questions}")
    
    print("\n=== Step 4: Run Pipeline ===")
    from dotenv import load_dotenv
    load_dotenv(current_dir / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("[Warning] OPENROUTER_API_KEY is not set in vishrut/.env")
        print("Please edit vishrut/.env and set your OPENROUTER_API_KEY first.")
        print("Pipeline run will be executed, but LLM calls will fail if required.")
    
    run_cmd([
        sys.executable,
        "pipeline.py",
        "--db", "graph.sqlite",
        "--questions", "questions.jsonl",
        "--out", "submission.jsonl"
    ], check=False)
    
    print("\n=== Step 5: Convert Output to CSV ===")
    success = convert_jsonl_to_csv("submission.jsonl", "submission.csv")
    if not success:
        print("Error: CSV conversion failed.")
    
    print("\n=== Step 6: Evaluate Results ===")
    eval_script = Path("../evaluate.py")
    if not eval_script.exists():
        print(f"Error: evaluate.py not found at {eval_script}")
        sys.exit(1)
        
    if os.path.exists("submission.csv"):
        # Run evaluate.py
        run_cmd([
            sys.executable,
            str(eval_script),
            "--submission", "submission.csv",
            "--questions", str(src_questions),
            "--per-question"
        ], check=False)
    else:
        print("Error: submission.csv was not generated.")

if __name__ == "__main__":
    main()
