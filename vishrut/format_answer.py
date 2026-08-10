"""
Stage 6: format a raw computed answer per the submission rules.

    money:   plain integer rupees, no units, no commas
    count:   integer
    percent: number out of 100, 2 decimal places (matches sample_questions.json,
             e.g. 33.33)
    days:    integer

Kept isolated from Stage 5's math so rounding/precision tuning never
touches computation logic.
"""


def format_answer(raw_value, answer_type: str):
    if answer_type == "money":
        return int(round(raw_value))
    if answer_type == "count":
        return int(round(raw_value))
    if answer_type == "days":
        return int(round(raw_value))
    if answer_type == "percent":
        return round(float(raw_value), 2)
    raise ValueError(f"unknown answer_type: {answer_type!r}")
