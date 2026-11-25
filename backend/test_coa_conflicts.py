from app.agents.extract_coa import COAParam, RawCOA, normalize_coa


def test_conflicting_duplicate_measurements_are_not_silently_accepted():
    raw = RawCOA(
        product_ref="CHEM-X01",
        parameters=[
            COAParam(name="purity", value=99.2),
            COAParam(name="purity", value=97.8),
        ],
    )

    result = normalize_coa(raw, db=None)

    assert "purity" not in result["params"]
    assert any("Conflicting measurements for purity" in issue for issue in result["issues"])


def test_identical_duplicate_measurements_remain_usable():
    raw = RawCOA(
        product_ref="CHEM-X01",
        parameters=[
            COAParam(name="purity", value=99.2),
            COAParam(name="purity", value=99.2),
        ],
    )

    result = normalize_coa(raw, db=None)

    assert result["params"]["purity"] == 99.2
    assert not any("Conflicting measurements" in issue for issue in result["issues"])
