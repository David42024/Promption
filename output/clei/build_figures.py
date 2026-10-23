from pathlib import Path
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
BASE=Path(__file__).resolve().parent
m=pd.read_csv(BASE/'evidence/metrics.csv')
a=json.loads((BASE/'evidence/manifest.json').read_text())
counts=a['corpus_counts']
seed=m[m.experiment=='random_42'].set_index('policy')
plt.rcParams.update({'font.family':'DejaVu Serif','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':180,'savefig.dpi':200})
fig,ax=plt.subplots(figsize=(7.0,3.15));ax.set_xlim(0,10);ax.set_ylim(0,5);ax.axis('off')
def box(x,y,w,h,t):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.05',facecolor='#f5f5f5',edgecolor='#444',linewidth=.8));ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=9)
def arrow(x,y,x2,y2):ax.annotate('',xy=(x2,y2),xytext=(x,y),arrowprops={'arrowstyle':'->','color':'#444','lw':1})
box(.05,3.2,1.7,1.0,'Input text');box(2.25,3.65,2.15,.8,'Regex heuristic');box(2.25,2.6,2.15,.8,'TF-IDF + logistic\nregression');box(4.95,3.05,1.65,1.15,'Three-state\npolicy');box(7.2,4.0,2.15,.7,'BLOCKED\nStop input');box(7.2,2.95,2.15,.7,'GUARDED\nInspect output');box(7.2,1.9,2.15,.7,'ALLOWED\nForward input')
arrow(1.8,3.7,2.2,4.0);arrow(1.8,3.4,2.2,3.0);arrow(4.45,4,4.95,3.75);arrow(4.45,3,4.95,3.4)
for y in [4.35,3.3,2.25]:arrow(6.65,3.6,7.15,y)
ax.plot([0,9.6],[1.45,1.45],color='#777',lw=.7,linestyle='--');ax.text(4.8,1.6,'Measured input-screening boundary',ha='center',fontsize=9)
ax.text(4.8,.7,'Downstream model generation, output inspection, tool authorization\nand protected-property outcomes are outside these classifier experiments',ha='center',va='center',fontsize=9)
fig.tight_layout();fig.savefig(BASE/'architecture.png',bbox_inches='tight');plt.close(fig)
sources=list(counts)
h=m[(m.policy=='three_state')&m.experiment.str.startswith('holdout')].set_index('experiment').loc[['holdout_'+s for s in sources]]
fig,ax=plt.subplots(figsize=(7,3.05));xx=np.arange(5);ax.bar(xx-.18,h.recall*100,.35,label='Malicious inputs blocked',color='#3f526c');ax.bar(xx+.18,h.fpr*100,.35,label='Benign inputs blocked',color='#a7afb8');ax.set_ylim(0,110);ax.set_ylabel('Percentage of class');ax.set_xticks(xx,sources,fontsize=9);ax.legend(loc='lower left',bbox_to_anchor=(0,1.02),ncol=2,frameon=False,fontsize=8.5);ax.grid(axis='y',color='#ddd',lw=.5);ax.set_axisbelow(True)
for i,r in enumerate(h.itertuples()):
 ax.text(i-.18,r.recall*100+2,f'{r.recall*100:.1f}',ha='center',fontsize=8)
 if not pd.isna(r.fpr):ax.text(i+.18,r.fpr*100+2,f'{r.fpr*100:.1f}',ha='center',fontsize=8)
 else:ax.text(i+.18,3,'N/A',ha='center',fontsize=8)
fig.tight_layout();fig.savefig(BASE/'shift.png',bbox_inches='tight');plt.close(fig)
fig,ax=plt.subplots(figsize=(7,2.35));r=seed.loc['three_state'];vals=np.array([[r.attack_blocked,r.attack_guarded],[r.benign_blocked,r.benign_guarded]],float);per=vals/vals.sum(1)[:,None]*100;left=np.zeros(2)
for j,(label,col) in enumerate([('BLOCKED','#3f526c'),('GUARDED','#b6bec7')]):
 ax.barh([1,0],per[:,j],left=left,color=col,label=label,height=.5)
 for i,y in enumerate([1,0]):ax.text(left[i]+per[i,j]/2,y,(f'{int(vals[i,j])}' if per[i,j]<15 else f'{int(vals[i,j])} ({per[i,j]:.1f}%)'),ha='center',va='center',fontsize=9,color='white' if j==0 else 'black')
 left+=per[:,j]
ax.set_yticks([1,0],['Malicious','Benign']);ax.set_xlim(0,100);ax.set_xlabel('Percentage within each label');ax.legend(loc='upper center',bbox_to_anchor=(.5,1.35),ncol=2,frameon=False,fontsize=9);fig.tight_layout();fig.savefig(BASE/'routing.png',bbox_inches='tight');plt.close(fig)
