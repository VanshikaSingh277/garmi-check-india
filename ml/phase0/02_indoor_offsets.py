import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd, numpy as np
D=sys.argv[2]
ind=pd.read_pickle(f"{D}/_ind.pkl"); aws=pd.read_pickle(f"{D}/_aws.pkl"); h=pd.read_pickle(f"{D}/_h.pkl")
meta=['Sr No','DD/MM/YYYY','Time',ind.columns[3],'Hours','Month','Season','dt']
tc=[c for c in ind.columns if c not in meta and '(RH)' not in c and c!='10693000.1']
long=ind[['dt']+tc].melt(id_vars='dt',var_name='logger',value_name='tin')
long['tin']=pd.to_numeric(long['tin'],errors='coerce'); long=long.dropna()
long['logger']=long['logger'].astype(str).str.strip()
# QC: drop physically implausible indoor values for Delhi Apr-Oct
before=len(long); long=long[(long.tin>=15)&(long.tin<=50)]
print("QC removed readings outside 15-50C:", before-len(long), "of", before)
long['hr']=long['dt'].dt.floor('h')
hourly=long.groupby(['logger','hr'])['tin'].mean().reset_index()
a=aws[['dt','Temp Out','Out Hum']].copy(); a['hr']=a['dt'].dt.floor('h')
a['tout']=pd.to_numeric(a['Temp Out'],errors='coerce')
m=hourly.merge(a[['hr','tout']],on='hr',how='inner')
m=m[(m.hr>='2016-04-12')&(m.hr<'2016-07-01')]   # pre-monsoon summer overlap
m['diff']=m['tin']-m['tout']; m['hod']=m['hr'].dt.hour
hh=h.set_index(h['Logger ID'].astype(str).str.strip())
def cat(r):
    rs=str(r['Roof structure']).lower()
    if 'floor on top' in rs or str(r['Floor on top']).lower()=='yes': return 'Not top floor (floor above)'
    if 'tin' in rs: return 'Top floor: TIN / metal sheet'
    return 'Top floor: CONCRETE / stone slab / brick (RCC-type)'
m['roof']=m['logger'].map(lambda L: cat(hh.loc[L]) if L in hh.index else 'unknown')
m['room']=m['logger'].map(lambda L: str(hh.loc[L,'Room type']) if L in hh.index else '?')
m=m[m.room.str.lower()!='outside']
print("summer overlap rows:",len(m),"| loggers:",m.logger.nunique(),"| hours:",m.hr.nunique())
def block(lbl,hours):
    s=m[m.hod.isin(hours)]
    per=s.groupby(['roof','logger'])['diff'].mean().reset_index()
    g=per.groupby('roof')['diff'].agg(['count','mean','median','min','max']).round(2)
    print(f"\n--- Indoor minus outdoor (deg C), {lbl}: per-logger means, then summarised by roof group ---"); print(g.rename(columns={'count':'n_homes'}).to_string())
block("AFTERNOON 14:00-16:59",[14,15,16])
block("NIGHT 02:00-05:59",[2,3,4,5])
block("ALL HOURS",list(range(24)))
pk=m[m.hod.isin([14,15,16])].groupby('roof')['tin'].quantile(.95).round(1); print("\nindoor 95th pct (afternoon):",pk.to_dict())
print("\noutdoor afternoon mean in window: %.1f C | night mean: %.1f C"%(m[m.hod.isin([14,15,16])]['tout'].mean(), m[m.hod.isin([2,3,4,5])]['tout'].mean()))
m.to_pickle(f"{D}/_merged_summer.pkl")
