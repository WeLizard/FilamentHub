"""Weighted-median recommender: robust "wisdom of the crowd" aggregation."""

from app.services.preset_recommender import (
    confidence_from_sample_size,
    weighted_median,
)


def test_weighted_median_rejects_outlier():
    # Four presets agree ~210 °C, one mistyped 400. The median stays put; a
    # weighted mean would be dragged to ~248.
    data = [(210.0, 1.0), (212.0, 1.0), (208.0, 1.0), (211.0, 1.0), (400.0, 1.0)]
    assert weighted_median(data) == 211.0


def test_weighted_median_respects_weights():
    # A heavily-weighted (trusted) value pulls the median to itself.
    assert weighted_median([(200.0, 1.0), (220.0, 10.0)]) == 220.0


def test_weighted_median_empty_or_all_none_is_none():
    assert weighted_median([]) is None
    assert weighted_median([(None, 5.0)]) is None
    # Zero-weight entries are ignored.
    assert weighted_median([(200.0, 0.0)]) is None


def test_confidence_thresholds():
    assert confidence_from_sample_size(4) == "low"
    assert confidence_from_sample_size(7) == "low"
    assert confidence_from_sample_size(8) == "medium"
    assert confidence_from_sample_size(19) == "medium"
    assert confidence_from_sample_size(20) == "high"
