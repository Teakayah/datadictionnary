from unittest.mock import MagicMock
import duckdb
import pandas as pd

class MockCursor:
    def __init__(self):
        self._con = MagicMock()

class MockConn:
    def cursor(self):
        return MockCursor()

conn = MockConn()
with conn.cursor() as cur:
    print(cur._con)
