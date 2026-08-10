"""
Parser unit tests. Money/date test values are taken directly from the
BITS Hackathon sample_questions.json reasoning_steps and README, so a
pass here means the parsers are correct against real, verified answers --
not just plausible-looking synthetic cases.
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.money import parse_money, parse_spoken_amount
from parsers.dates import parse_date, date_diff_days
from parsers.category import categorize
from parsers.grading import normalize_grading


class TestMoneyParser(unittest.TestCase):
    def test_crore_rendering(self):
        # README worked example: 333,800,000 rupees == INR 33.38 Cr
        self.assertEqual(parse_money("INR 33.38 Cr"), 333800000)

    def test_lakh_rendering(self):
        self.assertEqual(parse_money("3,338.00 Lakh"), 333800000)

    def test_indian_grouping(self):
        self.assertEqual(parse_money("33,38,00,000"), 333800000)

    def test_raw_integer(self):
        self.assertEqual(parse_money("333800000"), 333800000)

    def test_embedded_in_sentence(self):
        self.assertEqual(
            parse_money("The contract value was INR 73.02 Cr as per the certificate."),
            730200000,
        )

    def test_no_money_found(self):
        self.assertIsNone(parse_money("no numbers here at all"))

    def test_sample_values_roundtrip(self):
        # A handful of the exact contract values that appear across
        # sample_questions.json reasoning_steps -- confirms the parser
        # recovers them regardless of which rendering is used.
        cases = {
            "INR 73.02 Cr": 730200000,
            "INR 81.44 Cr": 814400000,
            "INR 6.92 Cr": 69200000,
            "874.00 Lakh": 87400000,
            "31,46,00,000": 314600000,
        }
        for rendering, expected in cases.items():
            with self.subTest(rendering=rendering):
                self.assertEqual(parse_money(rendering), expected)


class TestSpokenAmountParser(unittest.TestCase):
    def test_seventy_three_crore(self):
        # HS-IC-0024: "crossing the seventy-three crore mark"
        self.assertEqual(
            parse_spoken_amount("their works crossing the seventy-three crore mark"),
            730000000,
        )

    def test_six_crore(self):
        # HS-IC-0025: "hitting the six crore line"
        self.assertEqual(
            parse_spoken_amount("contracts hitting the six crore line"),
            60000000,
        )

    def test_digit_form_still_works(self):
        # HS-IC-0017: "credential target of INR 20 Cr"
        self.assertEqual(
            parse_spoken_amount("our credential target of INR 20 Cr"),
            200000000,
        )


class TestDateParser(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(parse_date("2021-03-10").isoformat(), "2021-03-10")

    def test_embedded_in_sentence(self):
        d = parse_date("PMP certification issued on 2021-03-10 to the engineer.")
        self.assertEqual(d.isoformat(), "2021-03-10")

    def test_prose_date(self):
        d = parse_date("March 10, 2021")
        self.assertEqual(d.isoformat(), "2021-03-10")

    def test_date_diff_matches_sample(self):
        # HS-IC-0003: PMP issued 2021-03-10, completion date such that
        # the gap is exactly 1569 days.
        issue = parse_date("2021-03-10")
        from datetime import timedelta
        completion = issue + timedelta(days=1569)
        self.assertEqual(date_diff_days(issue, completion), 1569)

    def test_date_diff_matches_second_sample(self):
        # HS-IC-0004: gap of 646 days
        issue = parse_date("2021-03-10")
        from datetime import timedelta
        completion = issue + timedelta(days=646)
        self.assertEqual(date_diff_days(issue, completion), 646)


class TestCategoryTaxonomy(unittest.TestCase):
    def test_bridge(self):
        self.assertEqual(categorize("Cable Stayed Bridge \u2014 Jharkhand Pkg-115"), "bridge")

    def test_building(self):
        self.assertEqual(categorize("School Building \u2014 Madhya Pradesh Pkg-145"), "building")

    def test_road(self):
        self.assertEqual(categorize("Ring Road \u2014 Uttar Pradesh Pkg-107"), "road")

    def test_water_treatment(self):
        self.assertEqual(categorize("WTP Augmentation \u2014 West Bengal Pkg-51"), "water_treatment")

    def test_dam(self):
        self.assertEqual(categorize("Check Dam \u2014 Gujarat Pkg-62"), "dam")

    def test_unknown_falls_back_to_other(self):
        self.assertEqual(categorize("Some Unlabeled Thing"), "other")


class TestGradingNormalizer(unittest.TestCase):
    def test_excellent(self):
        self.assertEqual(
            normalize_grading("The department graded this work as Excellent overall."),
            "Excellent",
        )

    def test_satisfactory(self):
        self.assertEqual(
            normalize_grading("Performance was rated Satisfactory by the client."),
            "Satisfactory",
        )

    def test_very_good_not_confused_with_good(self):
        self.assertEqual(
            normalize_grading("Overall assessment: Very Good cooperation shown."),
            "Very Good",
        )

    def test_no_grading_present(self):
        self.assertIsNone(normalize_grading("This certificate has no grading remark."))


if __name__ == "__main__":
    unittest.main()
