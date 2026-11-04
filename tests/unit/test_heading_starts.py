"""Where chunker C2 may cut: headings and clause numbers in contract text (plan step 3.4).

The texts imitate CUAD's: many contracts have no real line breaks, so headings appear inline.
"""

import pytest

from ragcalibrate.ingest.chunkers import heading_starts


@pytest.mark.parametrize(
    ("text", "headings"),
    [
        # Inline, after a sentence end; a reference inside a sentence is not a heading.
        (
            "as follows: 1. Grant of Rights. Section 1.1. License Grant. Subject to Section 1.2.",
            ["1. Grant", "Section 1.1. License"],
        ),
        # At a line start: Article, a clause number, a letter heading.
        (
            "Recitals\n\nARTICLE IV\nDEFINITIONS\n(a) the Licensee\n   A. Purpose",
            ["ARTICLE IV", "(a) the", "A. Purpose"],
        ),
        # After a layout gap, with no sentence end before it.
        ("MUTUAL RELEASES; INDEMNIFICATION   4.1 Release of Claims.", ["4.1 Release"]),
        # Clause numbers after a colon or a semicolon.
        ("information that: (a) was public; (iv) is known.", ["(a) was", "(iv) is"]),
        # Dotted numbers with and without a final dot, and a closing quote before the heading.
        ('the "Agreement." 8.1.4 Breach. 9.2. Term.', ["8.1.4 Breach", "9.2. Term"]),
        # A curly closing quote, as many contracts have.
        ("the \u201cAgreement.\u201d 1. Term.", ["1. Term"]),
    ],
)
def test_finds_headings(text: str, headings: list[str]) -> None:
    starts = heading_starts(text)
    assert [text[p : p + len(h)] for p, h in zip(starts, headings, strict=True)] == headings


@pytest.mark.parametrize(
    "text",
    [
        "Subject to Section 13 below, the Trust agrees.",  # a reference, not after a sentence end
        "Section 2.1 shall survive. Section 2.2 shall not.",  # followed by a lowercase word
        "Payment is late. 10 Business Days later it lapses.",  # a bare number with no dot
        "The fee is due. 2019. The year ended.",  # four digits: a year, not a section number
        "if (a) such entity ceases to be a subsidiary",  # (a) inside a sentence
        "Facsimile No.: (858) 942-8170",  # three digits in parentheses: an area code
        "signed by J. Smith. A. Jones agreed.",  # a letter after a sentence end: an initial
        "1. Term. The term is one year.",  # a heading at offset 0 is not a cut
    ],
)
def test_ignores_non_headings(text: str) -> None:
    assert heading_starts(text) == []
