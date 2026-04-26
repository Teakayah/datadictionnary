import pandas as pd
import time
import numpy as np

# Create dummy data
np.random.seed(42)
n_rows = 100000
catalogs = ['catalog_A', 'catalog_B', 'catalog_C']
schemas = [f'schema_{i}' for i in range(50)]
tables = [f'table_{i}' for i in range(1000)]

data = {
    'catalog_name': np.random.choice(catalogs, n_rows),
    'schema_name': np.random.choice(schemas, n_rows),
    'table_name': np.random.choice(tables, n_rows)
}
all_data = pd.DataFrame(data)

def original_method(all_data):
    catalogs = sorted(all_data['catalog_name'].unique().tolist())
    result = []
    for cat in catalogs:
        cat_data = all_data[all_data['catalog_name'] == cat]
        schemas = sorted(cat_data['schema_name'].unique().tolist())
        for sch in schemas:
            sch_data = cat_data[cat_data['schema_name'] == sch]
            tables = sorted(sch_data['table_name'].unique().tolist())
            result.append((cat, sch, len(tables)))
    return result

def optimized_method(all_data):
    catalogs = sorted(all_data['catalog_name'].unique().tolist())
    result = []
    for cat in catalogs:
        cat_data = all_data[all_data['catalog_name'] == cat]
        for sch, sch_data in cat_data.groupby('schema_name'):
            tables = sorted(sch_data['table_name'].unique().tolist())
            result.append((cat, sch, len(tables)))
    # Note: we need to sort the schemas
    # groupby automatically sorts by the key by default (sort=True)
    return result

# Validate correctness
res1 = sorted(original_method(all_data))
res2 = sorted(optimized_method(all_data))
assert res1 == res2, "Results do not match!"

# Benchmark
import timeit
num_runs = 10

orig_time = timeit.timeit(lambda: original_method(all_data), number=num_runs)
opt_time = timeit.timeit(lambda: optimized_method(all_data), number=num_runs)

print(f"Original Time: {orig_time:.4f} seconds")
print(f"Optimized Time: {opt_time:.4f} seconds")
print(f"Improvement: {orig_time / opt_time:.2f}x faster")
