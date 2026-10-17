import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd, numpy as np
D=sys.argv[2]
ind=pd.read_pickle(f"{D}/_ind.pkl"); aws=pd.read_pickle(f"{D}/_aws.pkl"); h=pd.read_pickle(f"{D}/_h.pkl")
meta=['Sr No','DD/MM/YYYY','Time',ind.columns[3],'Hours','Month','Season','dt']
tc=[c for c in ind.columns if c not in meta and '(RH)' not in c and c!='10693000.1']
long=ind[['dt']+tc].melt(id_vars='dt',var_name='logger',value_name='tin'); long['tin']=pd.to_numeric(long['tin'],errors='coerce'); long=long.dropna()
long['logger']=long['logger'].astype(str).str.strip(); long['hr']=long['dt'].dt.floor('h')
hourly=long.groupby(['logger','hr'])['tin'].mean().reset_index()
hh=h.set_index(h['Logger ID'].astype(str).str.strip())
def cat4(L):
    r=hh.loc[L]; rs=str(r['Roof structure']).lower()
    if 'floor on top' in rs or str(r['Floor on top']).lower()=='yes': return 'lower_floor'
    if 'tin' in rs: return 'tin_top'
    if 'stone' in rs: return 'stone_slab_top'
    return 'rcc_brick_top'
def run(shift_h):
    a=aws[['dt','Temp Out']].copy(); a['tout']=pd.to_numeric(a['Temp Out'],errors='coerce')
    a['hr']=a['dt'].dt.floor('h')+pd.Timedelta(hours=shift_h)   # shift=-1: AWS stamp = END of averaged hour
    m=hourly.merge(a[['hr','tout']],on='hr'); m=m[(m.hr>='2016-04-12')&(m.hr<'2016-07-01')]
    m=m[m.logger.map(lambda L: L in hh.index and str(hh.loc[L,'Room type']).lower()!='outside')]
    m['grp']=m.logger.map(cat4); m['diff']=m.tin-m.tout; m['hod']=m.hr.dt.hour
    return m
for s in [0,-1]:
    m=run(s); print(f"\n=== AWS shift {s} h ===")
    for lbl,hrs in [('afternoon',[14,15,16]),('night',[2,3,4,5])]:
        per=m[m.hod.isin(hrs)].groupby(['grp','logger'])['diff'].mean().reset_index()
        print(lbl, per.groupby('grp')['diff'].agg(['count','median']).round(2).to_dict('index'))
# leave-one-home-out: predict each home's afternoon & night mean offset with median of OTHER homes in its 3-group
m=run(0); 
m['g3']=m['grp'].replace({'stone_slab_top':'rcc_type_top','rcc_brick_top':'rcc_type_top'})
for lbl,hrs in [('afternoon',[14,15,16]),('night',[2,3,4,5])]:
    per=m[m.hod.isin(hrs)].groupby(['g3','logger'])['diff'].mean().reset_index()
    errs=[]
    for i,r in per.iterrows():
        others=per[(per.g3==r.g3)&(per.logger!=r.logger)]['diff']
        errs.append(abs(r['diff']-others.median()))
    errs=np.array(errs); print(f"LOHO {lbl}: MAE {errs.mean():.2f} C, 90th pct abs err {np.percentile(errs,90):.2f} C, n={len(errs)}")
    # baseline: no roof info (overall median)
    e0=[abs(r['diff']-per[per.logger!=r.logger]['diff'].median()) for _,r in per.iterrows()]
    print(f"   baseline without roof group: MAE {np.mean(e0):.2f} C")
