import unittest

from app.main import normalize_csv_header, parse_csv_metric


class YouTubeCsvMetricTests(unittest.TestCase):
    def test_duration_mm_ss(self):
        self.assertEqual(parse_csv_metric("1:23", duration=True), 83)

    def test_duration_hh_mm_ss(self):
        self.assertEqual(parse_csv_metric("1:02:03", duration=True), 3723)

    def test_decimal_comma(self):
        self.assertEqual(parse_csv_metric("72,5%"), 72.5)

    def test_thousands_separator_for_integer(self):
        self.assertEqual(parse_csv_metric("1,234", integer_only=True), 1234)

    def test_swedish_header_normalization(self):
        self.assertEqual(normalize_csv_header("Genomsnittlig visningsprocent (%)"), "genomsnittligvisningsprocent")


if __name__ == "__main__":
    unittest.main()
