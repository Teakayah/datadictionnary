import pandas as pd

df = pd.DataFrame()
print("empty df index test:", getattr(df, "columns", []), df.empty)
