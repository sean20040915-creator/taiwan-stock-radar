import pandas as pd
import pytest
from scripts.import_csv import import_history


def test_import_rejects_fake_provenance(tmp_path):
    file=tmp_path/"hist.csv"
    pd.DataFrame([{"day":"2023-01-03","market":"TWSE","code":"2330","name":"test","open":100,"high":100,"low":99,"close":99,"volume":10000,"amount":1000000}]).to_csv(file,index=False)
    with pytest.raises(ValueError):import_history(file,"demo")
