import sys
import pandas as pd
import numpy as np
import json

ref_path = sys.argv[1]
new_path = sys.argv[2]
out_json = sys.argv[3]

ref = pd.read_csv(ref_path, sep='\t')
new = pd.read_csv(new_path, sep='\t')

report = {}
report['ref_rows'] = len(ref)
report['new_rows'] = len(new)
report['ref_cols'] = list(ref.columns)
report['new_cols'] = list(new.columns)
report['cols_match'] = list(ref.columns) == list(new.columns)

# Identify an identifier column
id_col = 'Proteins' if 'Proteins' in ref.columns else ref.columns[0]
report['id_col'] = id_col

ref_ids = ref[id_col].astype(str)
new_ids = new[id_col].astype(str)
report['ids_identical_order'] = bool((ref_ids.values == new_ids.values).all()) if len(ref_ids) == len(new_ids) else False
report['ref_id_set_eq_new_id_set'] = set(ref_ids) == set(new_ids)
report['ref_duplicate_ids'] = int(ref_ids.duplicated().sum())
report['new_duplicate_ids'] = int(new_ids.duplicated().sum())

numeric_cols = ['pEC50', 'Curve Slope', 'Curve Front', 'Curve Back', 'Curve Fold Change',
                'Curve F_Value', 'Curve P_Value', 'Curve Relevance Score', 'Curve AUC', 'Curve R2']

numeric_report = {}
if report['ids_identical_order']:
    ref_al = ref
    new_al = new
else:
    ref_al = ref.set_index(id_col)
    new_al = new.set_index(id_col)
    common = ref_al.index.intersection(new_al.index)
    report['n_common_ids'] = len(common)
    ref_al = ref_al.loc[common]
    new_al = new_al.loc[common]

for col in numeric_cols:
    if col not in ref.columns or col not in new.columns:
        numeric_report[col] = 'missing column'
        continue
    a = pd.to_numeric(ref_al[col], errors='coerce').values.astype(float)
    b = pd.to_numeric(new_al[col], errors='coerce').values.astype(float)
    n_nan_mismatch = int((np.isnan(a) != np.isnan(b)).sum())
    valid = ~np.isnan(a) & ~np.isnan(b)
    if valid.sum() == 0:
        numeric_report[col] = {'n_valid': 0, 'n_nan_mismatch': n_nan_mismatch}
        continue
    diff = np.abs(a[valid] - b[valid])
    denom = np.maximum(np.abs(a[valid]), 1e-12)
    reldiff = diff / denom
    idx_worst = int(np.argmax(diff))
    numeric_report[col] = {
        'n_valid': int(valid.sum()),
        'n_nan_mismatch': n_nan_mismatch,
        'max_abs_diff': float(np.max(diff)),
        'max_rel_diff': float(np.max(reldiff)),
        'mean_abs_diff': float(np.mean(diff)),
    }

report['numeric_comparison'] = numeric_report

cat_col = 'Curve Regulation'
if cat_col in ref.columns and cat_col in new.columns:
    a = ref_al[cat_col].astype(str).values
    b = new_al[cat_col].astype(str).values
    match = (a == b)
    report['regulation_exact_match_count'] = int(match.sum())
    report['regulation_total'] = int(len(match))
    if not match.all():
        mismatches = {}
        for av, bv in zip(a[~match], b[~match]):
            key = f"{av}->{bv}"
            mismatches[key] = mismatches.get(key, 0) + 1
        report['regulation_mismatch_breakdown'] = mismatches
    else:
        report['regulation_mismatch_breakdown'] = {}

with open(out_json, 'w') as f:
    json.dump(report, f, indent=2)

print(json.dumps(report, indent=2))
