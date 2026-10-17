import sys
sys.path.insert(0, sys.argv[1])
import pandas as pd
df=pd.read_excel(sys.argv[2], header=None).iloc[7:]
cols=['tab','st','dist','teh','town','area','tru','total','thatch','plastic','hand_tiles','mach_tiles','burnt_brick','stone_slate','gi_metal_asbestos','concrete','other']
df.columns=cols
for c in cols[7:]: df[c]=pd.to_numeric(df[c],errors='coerce')
sel=df[(df.teh=='00000')&(df.tru=='Total')]
pct=sel[['area','total']].copy()
for c in cols[8:]: pct[c]=(sel[c]/sel['total']*100).round(1)
pd.set_option('display.width',250)
print(pct.to_string(index=False))
u=df[(df.dist=='000')&(df.tru=='Urban')]
print("\nDelhi URBAN:", {c: round(float(u[c].iloc[0]/u['total'].iloc[0]*100),1) for c in cols[8:]})
