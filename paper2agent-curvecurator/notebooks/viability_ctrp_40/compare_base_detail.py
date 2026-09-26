import pandas as pd
import numpy as np
import json

REF = "/home/user/test100/paper2agent-curvecurator/repo/curve_curator/example_datasets/viability_CTRP_40/curves_40.0.txt"
NEW = "/home/user/test100/paper2agent-curvecurator/notebooks/viability_ctrp_40/work/base/curves_40.0.txt"

ref = pd.read_csv(REF, sep='\t', low_memory=False).sort_values('Name').reset_index(drop=True)
new = pd.read_csv(NEW, sep='\t', low_memory=False).sort_values('Name').reset_index(drop=True)

assert ref['Name'].tolist() == new['Name'].tolist()

numeric_cols = ['pEC50', 'Curve Slope', 'Curve Front', 'Curve Back', 'Curve Fold Change',
                'Curve F_Value', 'Curve P_Value', 'Curve Relevance Score', 'Curve AUC', 'Curve R2']

thresholds = {
    'pEC50': 1e-4,
    'Curve Slope': 1e-4,
    'Curve Front': 1e-4,
    'Curve Back': 1e-4,
    'Curve Fold Change': 1e-4,
    'Curve F_Value': 1e-4,
    'Curve P_Value': 1e-4,
    'Curve Relevance Score': 1e-4,
    'Curve AUC': 1e-6,
    'Curve R2': 1e-6,
}

out = {}
for col in numeric_cols:
    a = pd.to_numeric(ref[col], errors='coerce').values
    b = pd.to_numeric(new[col], errors='coerce').values
    diff = np.abs(a - b)
    thr = thresholds[col]
    n_exceed = int((diff > thr).sum())
    out[col] = {
        'threshold': thr,
        'n_rows_exceeding': n_exceed,
        'n_rows_total': len(diff),
        'median_abs_diff': float(np.median(diff)),
        'p99_abs_diff': float(np.percentile(diff, 99)),
        'max_abs_diff': float(np.max(diff)),
        'names_exceeding': ref.loc[diff > thr, 'Name'].tolist()[:20],
    }

print(json.dumps(out, indent=2))

# Detail on the outlier row(s)
outlier_names = set()
for col in numeric_cols:
    outlier_names.update(out[col]['names_exceeding'])

print("\n=== Outlier row details ===")
for nm in outlier_names:
    r = ref[ref['Name']==nm].iloc[0]
    n = new[new['Name']==nm].iloc[0]
    print(f"\n--- {nm} ---")
    for col in ['Signal Quality','pEC50','Curve Slope','Curve Front','Curve Back','Curve Fold Change',
                'Curve RMSE','Curve R2','Null RMSE','Curve F_Value','Curve P_Value','Curve Relevance Score','Curve Regulation']:
        print(f"  {col}: ref={r[col]}  new={n[col]}")
