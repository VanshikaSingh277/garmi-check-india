import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd, numpy as np
D=sys.argv[2]; MISS=['NA','','-','na','N/A','nan']
h=pd.read_csv(f"{D}/delhi_housing.csv",na_values=MISS,dtype=str,encoding='latin-1'); h.columns=[c.strip() for c in h.columns]
ind=pd.read_csv(f"{D}/delhi_indoor.csv", na_values=MISS, low_memory=False)
s=ind['DD/MM/YYYY'].astype(str)+' '+ind['Time'].astype(str)
dt=pd.to_datetime(s,format='%m/%d/%Y %I:%M:%S %p',errors='coerce'); m=dt.isna()
dt.loc[m]=pd.to_datetime(s[m],format='%m-%d-%Y %I:%M:%S %p',errors='coerce')
ind['dt']=dt
print("unparsed:",int(dt.isna().sum()),"| range:",dt.min(),"->",dt.max())
print(ind.groupby('Season')['dt'].agg(['min','max','count']).to_string())
step=ind['dt'].sort_values().diff().value_counts().head(3); print("steps:",step.to_dict())
meta=['Sr No','DD/MM/YYYY','Time',ind.columns[3],'Hours','Month','Season','dt']
tc=[c for c in ind.columns if c not in meta and '(RH)' not in c]
v=ind[tc].apply(pd.to_numeric,errors='coerce')
q=v.stack(); print("indoor temp percentiles: p0.1 %.1f p1 %.1f p50 %.1f p99 %.1f p99.9 %.1f max %.1f"%tuple(q.quantile([.001,.01,.5,.99,.999,1]).values))
print("readings >50C:",int((q>50).sum()),"| <15C:",int((q<15).sum()))
ids_h=set(h['Logger ID'].astype(str).str.strip()); ids_i=set(c.split('.')[0].strip() for c in tc)
print("housing loggers:",len(ids_h),"| indoor loggers:",len(ids_i),"| matched:",len(ids_h&ids_i))
print("indoor-only:",sorted(ids_i-ids_h),"| housing-only:",sorted(ids_h-ids_i))
aws=pd.read_csv(f"{D}/delhi_aws.csv", na_values=MISS, low_memory=False); aws.columns=[c.strip() for c in aws.columns]
a=aws['DD/MM/YYYY'].astype(str)+' '+aws['Time'].astype(str)
adt=pd.to_datetime(a,format='%m-%d-%y %I:%M:%S %p',errors='coerce'); mm=adt.isna()
for f in ['%m/%d/%Y %I:%M:%S %p','%m-%d-%Y %I:%M:%S %p','%m/%d/%y %I:%M:%S %p']:
    if mm.any(): adt.loc[mm]=pd.to_datetime(a[mm],format=f,errors='coerce'); mm=adt.isna()
aws['dt']=adt
print("\nAWS unparsed:",int(adt.isna().sum()),"| range:",adt.min(),"->",adt.max(),"| rows",len(aws))
print(aws.groupby('Season')['dt'].agg(['min','max','count']).to_string())
print("AWS steps:",aws['dt'].sort_values().diff().value_counts().head(3).to_dict())
for c in ['Temp Out','Out Hum','Solar Rad.','Wind Speed','Heat Index']:
    x=pd.to_numeric(aws[c],errors='coerce'); print(f"{c}: missing {x.isna().mean()*100:.1f}% | min {x.min()} max {x.max()}")
ind.to_pickle(f"{D}/_ind.pkl"); aws.to_pickle(f"{D}/_aws.pkl"); h.to_pickle(f"{D}/_h.pkl")
