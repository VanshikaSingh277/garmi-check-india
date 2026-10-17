import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd, numpy as np
exec(open(sys.argv[3]).read().split("for s in [0,-1]:")[0])   # reuse loaders + run() from review_checks.py
m0=run(0); m1=run(-1)
rows=[]
for lbl,hrs in [('afternoon_14_17',[14,15,16]),('night_02_06',[2,3,4,5]),('all_hours',list(range(24)))]:
    p0=m0[m0.hod.isin(hrs)].groupby(['grp','logger'])['diff'].mean().reset_index()
    p1=m1[m1.hod.isin(hrs)].groupby(['grp','logger'])['diff'].mean().reset_index()
    for g,x in p0.groupby('grp'):
        alt=p1[p1.grp==g]['diff'].median()
        rows.append(dict(window=lbl,roof_group=g,n_homes=len(x),median_c=round(x['diff'].median(),2),q25_c=round(x['diff'].quantile(.25),2),q75_c=round(x['diff'].quantile(.75),2),
                         min_c=round(x['diff'].min(),2),max_c=round(x['diff'].max(),2),median_if_aws_stamp_is_hour_end=round(alt,2)))
    errs=[];e0=[]
    for _,r in p0.iterrows():
        o=p0[(p0.grp==r.grp)&(p0.logger!=r.logger)]['diff']; errs.append(abs(r['diff']-o.median()))
        e0.append(abs(r['diff']-p0[p0.logger!=r.logger]['diff'].median()))
    print(f"LOHO 4-group {lbl}: MAE {np.mean(errs):.2f} C (p90 {np.percentile(errs,90):.2f}) | no-roof baseline MAE {np.mean(e0):.2f} C")
out=pd.DataFrame(rows); out.to_csv(sys.argv[4],index=False); print(out.to_string(index=False))
