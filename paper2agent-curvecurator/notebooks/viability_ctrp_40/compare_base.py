import pandas as pd
import numpy as np
import hashlib, json, sys

REF = "/home/user/test100/paper2agent-curvecurator/repo/curve_curator/example_datasets/viability_CTRP_40/curves_40.0.txt"
NEW = "/home/user/test100/paper2agent-curvecurator/notebooks/viability_ctrp_40/work/base/curves_40.0.txt"

ref = pd.read_csv(REF, sep='\t', low_memory=False)
new = pd.read_csv(NEW, sep='\t', low_memory=False)

report = {}
report['ref_rows'] = len(ref)
report['new_rows'] = len(new)
report['ref_cols'] = list(ref.columns)
report['new_cols'] = list(new.columns)
report['cols_match'] = list(ref.columns) == list(new.columns)

# Identifier agreement
ref_ids = ref['Name'].tolist()
new_ids = new['Name'].tolist()
report['ids_identical_order'] = ref_ids == new_ids
report['ids_same_set'] = set(ref_ids) == set(new_ids)

# Align on Name for safety (sort both by Name) in case order differs
ref_sorted = ref.sort_values('Name').reset_index(drop=True)
new_sorted = new.sort_values('Name').reset_index(drop=True)
report['ids_identical_after_sort'] = ref_sorted['Name'].tolist() == new_sorted['Name'].tolist()

numeric_cols = ['pEC50', 'Curve Slope', 'Curve Front', 'Curve Back', 'Curve Fold Change',
                'Curve F_Value', 'Curve P_Value', 'Curve Relevance Score', 'Curve AUC', 'Curve R2']

num_report = {}
for col in numeric_cols:
    if col not in ref_sorted.columns or col not in new_sorted.columns:
        num_report[col] = {'error': 'column missing'}
        continue
    a = pd.to_numeric(ref_sorted[col], errors='coerce').values
    b = pd.to_numeric(new_sorted[col], errors='coerce').values
    both_nan = np.isnan(a) & np.isnan(b)
    mismatch_nan = np.isnan(a) != np.isnan(b)
    diff = np.abs(a - b)
    diff[both_nan] = 0.0
    # relative diff, guard div by zero
    denom = np.maximum(np.abs(a), 1e-300)
    reldiff = diff / denom
    reldiff[both_nan] = 0.0
    max_abs = float(np.nanmax(diff)) if len(diff) else None
    max_rel = float(np.nanmax(reldiff)) if len(reldiff) else None
    idx_max_abs = int(np.nanargmax(diff)) if len(diff) else None
    num_report[col] = {
        'max_abs_diff': max_abs,
        'max_rel_diff': max_rel,
        'n_nan_mismatch': int(mismatch_nan.sum()),
        'n_both_nan': int(both_nan.sum()),
        'example_at_max_abs': {
            'Name': str(ref_sorted['Name'].iloc[idx_max_abs]) if idx_max_abs is not None else None,
            'ref': float(a[idx_max_abs]) if idx_max_abs is not None and not np.isnan(a[idx_max_abs]) else None,
            'new': float(b[idx_max_abs]) if idx_max_abs is not None and not np.isnan(b[idx_max_abs]) else None,
        }
    }

report['numeric_columns'] = num_report

# Categorical: Curve Regulation
if 'Curve Regulation' in ref_sorted.columns and 'Curve Regulation' in new_sorted.columns:
    r = ref_sorted['Curve Regulation'].fillna('NA_SENTINEL')
    n = new_sorted['Curve Regulation'].fillna('NA_SENTINEL')
    exact_match = (r == n)
    report['curve_regulation'] = {
        'n_total': len(r),
        'n_exact_match': int(exact_match.sum()),
        'n_mismatch': int((~exact_match).sum()),
    }
    if (~exact_match).sum() > 0:
        mism = ref_sorted.loc[~exact_match, ['Name']].copy()
        mism['ref_reg'] = r[~exact_match].values
        mism['new_reg'] = n[~exact_match].values
        report['curve_regulation']['mismatches'] = mism.head(50).to_dict(orient='records')
        # breakdown by pair
        from collections import Counter
        pairs = Counter(zip(r[~exact_match].values, n[~exact_match].values))
        report['curve_regulation']['mismatch_breakdown'] = {f"{k[0]}->{k[1]}": v for k, v in pairs.items()}

print(json.dumps(report, indent=2, default=str))
