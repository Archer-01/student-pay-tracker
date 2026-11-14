"""The school's share of the money received, and what is left for the teacher."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.school_share import split, split_months

D = Decimal


def test_a_quarter_goes_to_the_school():
    s = split(D("1560.00"), D("25"))
    assert (s.percent, s.school, s.teacher) == (D("25"), D("390.00"), D("1170.00"))


def test_cents_round_half_up_and_the_two_parts_still_add_up():
    # 25% of 199.50 is 49.875: the school's part rounds to the cent, the teacher keeps the rest.
    s = split(D("199.50"), D("25"))
    assert (s.school, s.teacher) == (D("49.88"), D("149.62"))


@pytest.mark.parametrize(
    ("percent", "school", "teacher"), [("0", "0.00", "300.00"), ("100", "300.00", "0.00")]
)
def test_the_edges(percent: str, school: str, teacher: str):
    s = split(D("300.00"), D(percent))
    assert (s.school, s.teacher) == (D(school), D(teacher))


@given(
    collected=st.decimals(min_value=0, max_value=1_000_000, places=2),
    percent=st.decimals(min_value=0, max_value=100, places=2),
)
def test_the_two_parts_always_add_up_to_what_came_in(collected: Decimal, percent: Decimal):
    s = split(collected, percent)
    assert s.school + s.teacher == collected
    assert D("0") <= s.school <= collected


def test_a_years_share_is_the_sum_of_its_months_not_a_quarter_of_the_total():
    # Each month rounds on its own; the year adds the months up, so the year always equals the
    # sum of the months it shows. 25% of each 199.50 rounds up; 25% of 399.00 wouldn't.
    months, year = split_months([D("199.50"), D("199.50")] + [D("0")] * 10, D("25"))
    assert [m.school for m in months[:2]] == [D("49.88"), D("49.88")]
    assert year.school == D("99.76")
    assert year.teacher == D("299.24")
    assert year.school + year.teacher == D("399.00")
