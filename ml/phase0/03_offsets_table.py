import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd
m=pd.read_pickle(sys.argv[2]+"/_merged_summer.pkl")
rows=[]
for lbl,hrs in [("afternoon_14_17",[14,15,16]),("night_02_06",[2,3,4,5]),("all_hours",list(range(24)))]:
    per=m[m.hod.isin(hrs)].groupby(['roof','logger'])['diff'].mean().reset_index()
    for r,g in per.groupby('roof'):
        rows.append(dict(window=lbl,roof_group=r,n_homes=len(g),mean_c=round(g['diff'].mean(),2),median_c=round(g['diff'].median(),2),
                         q25_c=round(g['diff'].quantile(.25),2),q75_c=round(g['diff'].quantile(.75),2),min_c=round(g['diff'].min(),2),max_c=round(g['diff'].max(),2)))
out=pd.DataFrame(rows); out.to_csv(sys.argv[3],index=False); print(out.to_string(index=False))
