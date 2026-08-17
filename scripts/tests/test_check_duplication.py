from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_duplication import find_repeated_literals


class LiteralPairingTest(unittest.TestCase):
    def test_code_between_two_literals_is_not_reported_as_a_literal(self) -> None:
        """Quotes must pair with their own literal, not with the next one's opener.

        A length-bounded pattern re-pairs the closing quote of one string with the
        opening quote of the following string and reports the code in between, which
        buried the real findings under lines like ``] = relationship(``.
        """
        line = 'brand: Mapped["Brand"] = relationship("Brand", back_populates="items")\n'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("first.py", "second.py"):
                (root / name).write_text(line * 4, encoding="utf-8")

            findings = find_repeated_literals(sorted(root.glob("*.py")), threshold=2)

        reported = [finding.sample for finding in findings]
        self.assertEqual(reported, [], f"фрагменты кода приняты за литералы: {reported}")


if __name__ == "__main__":
    unittest.main()
