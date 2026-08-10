#!/usr/bin/env python3
import os
import sys
import json
import csv
import argparse
import subprocess
from pathlib import Path
from utils.logger import setup_logger

# Set up working directory to be the directory containing this script
current_dir = Path(__file__).resolve().parent
os.chdir(current_dir)

# Setup logger to output to both console and a log file
logger = setup_logger(name="vishrut", log_file="logs/run.log")

def run_cmd(cmd, check=True):
    logger.info(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}")
    return res

def convert_jsonl_to_csv(jsonl_path, csv_path):
    logger.info(f"Converting {jsonl_path} to CSV format: {csv_path}")
    if not os.path.exists(jsonl_path):
        logger.error(f"{jsonl_path} does not exist. Cannot convert to CSV.")
        return False
    try:
        with open(jsonl_path, "r", encoding="utf-8-sig") as f_in:
            lines = f_in.readlines()
            
        with open(csv_path, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["question_id", "answer"])
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                line = line.replace('\x00', '')
                line = line.strip('\ufeff')
                try:
                    item = json.loads(line)
                    writer.writerow([item.get("qid"), item.get("answer")])
                except json.JSONDecodeError as je:
                    logger.warning(f"Failed to decode line: {repr(line)}. Error: {je}")
        return True
    except Exception as e:
        logger.error(f"Error during CSV conversion: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description="Run Vishrut Pipeline")
    parser.add_argument(
        "--questions", 
        default="../questions.json", 
        help="Path to questions JSON file (default: ../questions.json)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between proxy requests (default: 0.0)"
    )
    args = parser.parse_args()

    # Create directories for logs and output
    Path("output").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    logger.info("=== Step 1: Install Requirements ===")
    run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    run_cmd([sys.executable, "-m", "pip", "install", "python-dotenv", "openai"])
    
    logger.info("=== Step 2: Build Database ===")
    db_path = "../graph.sqlite"
    try:
        run_cmd([sys.executable, "graph/build_db.py", "--db", db_path])
    except Exception as e:
        logger.warning(f"Database build failed or was locked: {e}. Proceeding with existing database.")
    
    logger.info(f"=== Step 3: Convert {args.questions} to output/questions.jsonl ===")
    src_questions = Path(args.questions)
    out_questions = Path("output/questions.jsonl")
    
    if not src_questions.exists():
        logger.error(f"Questions source path {src_questions} does not exist!")
        sys.exit(1)
        
    with open(src_questions, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    questions = data.get("questions", data.get("answers", []))
    logger.info(f"Loaded {len(questions)} questions from {src_questions}")
    
    with open(out_questions, "w", encoding="utf-8") as f:
        for q in questions:
            json.dump({"qid": q["qid"], "question": q["question"]}, f)
            f.write("\n")
    logger.info(f"Wrote questions to {out_questions}")
    
    logger.info("=== Step 4: Run Pipeline ===")
    submission_jsonl = Path("output/submission.jsonl")
    run_log_json = Path("logs/run_log.json")
    
    run_cmd([
        sys.executable,
        "pipeline.py",
        "--db", db_path,
        "--questions", str(out_questions),
        "--out", str(submission_jsonl),
        "--log", str(run_log_json),
        "--delay", str(args.delay)
    ], check=False)
    
    logger.info("=== Step 5: Convert Output to CSV ===")
    submission_csv = Path("output/submission.csv")
    success = convert_jsonl_to_csv(str(submission_jsonl), str(submission_csv))
    if success and submission_csv.exists():
        # Keep a copy directly in vishrut/ folder as requested: "generated answers will be in vishrut folder only"
        import shutil
        shutil.copy(submission_csv, "submission.csv")
        logger.info("Successfully generated submission.csv in output/ and copied to vishrut/.")
    else:
        logger.error("CSV conversion failed or submission.csv was not found.")
    
    logger.info("=== Step 6: Evaluate Results ===")
    eval_script = Path("../evaluate.py")
    if not eval_script.exists():
        logger.error(f"evaluate.py not found at {eval_script}")
        sys.exit(1)
        
    # First run self-test
    logger.info("Running evaluate.py self-test...")
    run_cmd([sys.executable, str(eval_script), "--self-test"], check=False)
    
    if submission_csv.exists():
        logger.info(f"Evaluating submission against {src_questions}...")
        run_cmd([
            sys.executable,
            str(eval_script),
            "--submission", str(submission_csv),
            "--questions", str(src_questions),
            "--per-question"
        ], check=False)
    else:
        logger.error("submission.csv was not generated.")

if __name__ == "__main__":
    main()
