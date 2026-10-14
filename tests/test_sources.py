import pytest
from src.sources import parse_day, parse_snapshot, valid_code


def test_roc_date():
    assert parse_day("1151013")=="2026-10-13"
    assert parse_day("20261013")=="2026-10-13"
    with pytest.raises(ValueError):parse_day("115-13-33")


def row_twse(code):
    return dict(Date="1151013",Code=str(code),Name="測試",OpeningPrice="10",HighestPrice="11",LowestPrice="9",ClosingPrice="10.5",TradeVolume="1,000,000",TradeValue="10,500,000")


def row_tpex(code):
    return dict(Date="1151013",SecuritiesCompanyCode=str(code),CompanyName="測試",Open="10",High="11",Low="9",Close="10.5",TradingShares="1,000,000",TransactionAmount="10,500,000")


def test_twse_tpex_exact_schema():
    a=parse_snapshot([row_twse(x) for x in range(1100,1201)],"TWSE")
    b=parse_snapshot([row_tpex(x) for x in range(6100,6201)],"TPEX")
    assert len(a)==len(b)==101
    assert a[0]["day"]=="2026-10-13"
    assert a[0]["amount"]==10_500_000
    assert b[0]["volume"]==1_000_000


def test_reject_bad_prices_and_securities():
    assert not valid_code("0050")
    assert not valid_code("9101")
    assert not valid_code("12345")
    vals=[row_twse(x) for x in range(1100,1201)]
    vals[0]["LowestPrice"]="12"
    with pytest.raises(ValueError,match="only 0 usable rows"):
        parse_snapshot(vals[:1],"TWSE")
