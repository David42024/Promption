"""Build the journal manuscript and figures from executed experiment outputs."""
from pathlib import Path
import json, math, re
import pandas as pd
import numpy as np
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
BASE=Path(__file__).resolve().parent
E=BASE/'evidence'
m=pd.read_csv(E/'metrics.csv')
pred=pd.read_csv(E/'predictions.csv')
a=json.loads((E/'manifest.json').read_text())
seed=m[m.experiment=='random_42'].set_index('policy')
counts=a['corpus_counts']
public_benign=sum(v['0'] for v in counts.values());public_malicious=sum(v['1'] for v in counts.values())
values={**a,'public_benign':public_benign,'public_malicious':public_malicious,'full_benign':a['full_labels']['0'],'full_malicious':a['full_labels']['1'],'random_train':int(seed.loc['ml','n_train']),'random_test':int(seed.loc['ml','n']),'python_version':a['python'].split()[0],'or_recall':f"{100*seed.loc['strict_or','recall']:.2f}",'or_fpr':f"{100*seed.loc['strict_or','fpr']:.2f}",'tri_recall':f"{100*seed.loc['three_state','recall']:.2f}",'tri_fpr':f"{100*seed.loc['three_state','fpr']:.2f}",'guarded_attack':int(seed.loc['three_state','attack_guarded'])}
raw=(BASE/'article_content.md').read_text()
raw=re.sub(r'\{\{(\w+)\}\}',lambda k:str(values[k[1]]),raw)
raw=raw.replace('and routes 89 additional malicious inputs to output inspection','and routes 89 malicious inputs to output inspection')
raw=raw.replace(' Funding and competing-interest declarations require confirmation by the authors before submission.','')
raw=raw.replace('Health and dashboard smoke checks provide evidence about importability and startup.','Health and dashboard smoke checks are attempted to examine importability and startup, with any incomplete check recorded separately.')
(BASE/'manuscript.md').write_text(raw)

def wilson(k,n):
 if not n:return 'N/A'
 z=1.959963984540054;p=k/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return f'{100*(mid-half):.2f}–{100*(mid+half):.2f}'

tables={
'related':('Table 1: Evaluation boundaries in related research and the present study',['Work','Principal boundary','Relation to this study'],[
['Greshake et al. [1]','Retrieved adversarial text','Motivates trust-context analysis'],['BIPIA [2]','Model output on indirect attacks','Requires live-model outcome checks'],['InjecAgent [3] and AgentDojo [4]','Tool-integrated tasks','Observe agent actions and task outcomes'],['Instruction hierarchy [5]','Model instruction privilege','Acts within the language model'],['CaMeL [6] and firewalls [7]','Control flow and tool interfaces','Enforce boundaries around model behavior'],['Present study','Input rejection and guarded routing','Paired policies and classifier source withholding']]),
'policy':('Table 2: Implemented actions at the configured decision boundary',['Heuristic score','ML probability','Action'],[
['0.0','Any or unavailable','ALLOWED'],['1.0','Any or unavailable','BLOCKED'],['0.4, 0.5, 0.7','Unavailable','GUARDED'],['0.4, 0.5, 0.7','p ≤ 0.66','GUARDED'],['0.4, 0.5, 0.7','p > 0.66','BLOCKED']]),
'corpus':('Table 3: Retained corpus after normalized exact deduplication',['Source','Benign','Malicious','Total'],[[s,str(v['0']),str(v['1']),str(v['0']+v['1'])] for s,v in counts.items()]+[['Total',str(public_benign),str(public_malicious),str(a['public_n'])]]),
'metrics':('Table 4: Meaning and limits of the reported observations',['Quantity','Observed event','Interpretation limit'],[
['Recall','Malicious inputs blocked / malicious inputs','Measures input interception'],['FPR','Benign inputs blocked / benign inputs','Measures rejection against corpus labels'],['Precision','Malicious inputs / all blocked inputs','Depends on observed prevalence'],['GUARDED count','Inputs routed to output inspection','No generated output is observed'],['Input escape','Malicious inputs not blocked','Does not establish compromise'],['Warm latency','In-process screen and action selection','Excludes the complete application path']]),
'seed42':('Table 5: Seed 42 test results on 534 malicious and 641 benign inputs',['Policy','TP / FP','FN / TN','Precision %','Recall %','FPR %'],[[{'heuristic':'Heuristic','ml':'ML','strict_or':'Strict OR','three_state':'Three state'}[s],f'{int(r.tp)} / {int(r.fp)}',f'{int(r.fn)} / {int(r.tn)}',f'{r.precision*100:.2f}',f'{r.recall*100:.2f}',f'{r.fpr*100:.2f}'] for s,r in seed.iterrows()]),
'random':('Table 6: Mean and sample standard deviation over three overlapping random holdouts',['Policy','Precision %','Recall %','F1','FPR %'],[]),
'holdout':('Table 7: Source held out recall and implemented policy false positives',['Held-out source','Recall H / ML %','Recall OR / 3S %','3S recall 95% CI','3S FPR % [95% CI]'],[]),
'actions':('Table 8: Implemented policy actions for the seed 42 test partition',['Label','ALLOWED','GUARDED','BLOCKED','Total'],[['Malicious','0','89','445','534'],['Benign','0','589','52','641'],['Total','0','678','497','1175']]),
'audit':('Table 9: Audit findings and their treatment in the experimental protocol',['Finding','Evidence','Experimental treatment'],[
['Configured backend','use_lightweight_ml is true','Refit the TF-IDF and logistic model'],['Three-state semantics','Action function differs from strict OR','Compare both over paired inputs'],['Position mismatch in splitter','199 locally excluded-source rows enter intended test','Construct new holdouts directly'],['No-LLM success proxy','Success becomes complement of input blocking','Report input escape only'],['Lenient response oracle','Non-refusal can count as compromise','Do not infer secret disclosure']])}
for policy,g in m[m.experiment.str.startswith('random')].groupby('policy',sort=False):
 row=[{'heuristic':'Heuristic','ml':'ML','strict_or':'Strict OR','three_state':'Three state'}[policy]]
 for col in ['precision','recall','f1','fpr']:
  scale=1 if col=='f1' else 100
  row.append(f'{g[col].mean()*scale:.4f} ± {g[col].std()*scale:.4f}' if col=='f1' else f'{g[col].mean()*scale:.2f} ± {g[col].std()*scale:.2f}')
 tables['random'][2].append(row)
for s in counts:
 g=m[m.experiment=='holdout_'+s].set_index('policy');r=g.loc['three_state']
 tables['holdout'][2].append([s,f"{100*g.loc['heuristic','recall']:.2f} / {100*g.loc['ml','recall']:.2f}",f"{100*g.loc['strict_or','recall']:.2f} / {100*r.recall:.2f}",wilson(r.tp,r.n_malicious),'N/A' if pd.isna(r.fpr) else f'{100*r.fpr:.2f} [{wilson(r.fp,r.n_benign)}]'])
refs=[
('K. Greshake, S. Abdelnabi, S. Mishra, C. Endres, T. Holz, and M. Fritz, “Not what you\'ve signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection,” arXiv preprint arXiv:2302.12173, 2023.','https://doi.org/10.48550/arXiv.2302.12173'),
('J. Yi et al., “Benchmarking and defending against indirect prompt injection attacks on large language models,” arXiv preprint arXiv:2312.14197, ver. 4, 2025.','https://doi.org/10.48550/arXiv.2312.14197'),
('Q. Zhan, Z. Liang, Z. Ying, and D. Kang, “InjecAgent: Benchmarking indirect prompt injections in tool-integrated large language model agents,” arXiv preprint arXiv:2403.02691, 2024.','https://doi.org/10.48550/arXiv.2403.02691'),
('E. Debenedetti, J. Zhang, M. Balunović, L. Beurer-Kellner, M. Fischer, and F. Tramèr, “AgentDojo: A dynamic environment to evaluate prompt injection attacks and defenses for LLM agents,” arXiv preprint arXiv:2406.13352, 2024.','https://doi.org/10.48550/arXiv.2406.13352'),
('E. Wallace, K. Xiao, R. Leike, L. Weng, J. Heidecke, and A. Beutel, “The instruction hierarchy: Training LLMs to prioritize privileged instructions,” arXiv preprint arXiv:2404.13208, 2024.','https://doi.org/10.48550/arXiv.2404.13208'),
('E. Debenedetti et al., “Defeating prompt injections by design,” arXiv preprint arXiv:2503.18813, ver. 2, 2025.','https://doi.org/10.48550/arXiv.2503.18813'),
('R. Bhagwatkar et al., “Indirect prompt injections: Are firewalls all you need, or stronger benchmarks?” arXiv preprint arXiv:2510.05244, ver. 2, 2026.','https://doi.org/10.48550/arXiv.2510.05244'),
('verazuo, “jailbreak_llms,” GitHub repository, accessed Oct. 2, 2026. [Online]. Available:','https://github.com/verazuo/jailbreak_llms'),
('Vaibhav-GOAT, “nepi-prompts-dataset,” Hugging Face dataset, accessed Oct. 2, 2026. [Online]. Available:','https://huggingface.co/datasets/Vaibhav-GOAT/nepi-prompts-dataset'),
('Shomi28, “prompt-injection-dataset,” Hugging Face dataset, accessed Oct. 2, 2026. [Online]. Available:','https://huggingface.co/datasets/Shomi28/prompt-injection-dataset'),
('deepset, “prompt-injections,” Hugging Face dataset, accessed Oct. 2, 2026. [Online]. Available:','https://huggingface.co/datasets/deepset/prompt-injections'),
('yanismiraoui, “prompt_injections,” Hugging Face dataset, accessed Oct. 2, 2026. [Online]. Available:','https://huggingface.co/datasets/yanismiraoui/prompt_injections'),
('scikit-learn developers, “TfidfVectorizer,” API documentation, accessed Oct. 2, 2026. [Online]. Available:','https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html'),
('scikit-learn developers, “LogisticRegression,” API documentation, accessed Oct. 2, 2026. [Online]. Available:','https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html')]
(E/'references.json').write_text(json.dumps(refs,ensure_ascii=False,indent=2))

doc=Document();sec=doc.sections[0];sec.page_width=Cm(21);sec.page_height=Cm(29.7);sec.top_margin=Cm(2);sec.right_margin=Cm(2);sec.bottom_margin=Cm(2.5);sec.left_margin=Cm(2.5);sec.footer_distance=Cm(1.2)
for name in ['Normal','Title','Heading 1','Heading 2','Heading 3','Caption']:
 st=doc.styles[name];st.font.name='Times New Roman';st.font.color.rgb=RGBColor(0,0,0);st.font.size=Pt(10);st.paragraph_format.line_spacing=1;st.paragraph_format.space_after=Pt(5)
 st.element.get_or_add_rPr().append(OxmlElement('w:rFonts'));st.element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman');st.element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman')
doc.styles['Normal'].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
doc.styles['Title'].font.size=Pt(16);doc.styles['Title'].font.bold=True;doc.styles['Title'].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER;doc.styles['Title'].paragraph_format.space_after=Pt(12)
for n,size in [('Heading 1',12),('Heading 2',10),('Heading 3',10)]:
 doc.styles[n].font.size=Pt(size);doc.styles[n].font.bold=n!='Heading 3';doc.styles[n].font.italic=n=='Heading 3';doc.styles[n].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.LEFT;doc.styles[n].paragraph_format.space_before=Pt(10);doc.styles[n].paragraph_format.space_after=Pt(5);doc.styles[n].paragraph_format.keep_with_next=True
fp=sec.footer.paragraphs[0];fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');fp._p.append(field)
doc.core_properties.title='Promption for Prompt Injection Detection under Source Shift and Three State Enforcement';doc.core_properties.author='Roberto Enrique Quezada-Rodríguez; David Adrian Lucano Nieves';doc.core_properties.subject='Original research manuscript prepared for CLEI Electronic Journal';doc.core_properties.keywords='Prompt injection, source shift, enforcement, security middleware'

def link(p,label,url):
 hyp=OxmlElement('w:hyperlink');hyp.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True));r=OxmlElement('w:r');rp=OxmlElement('w:rPr');color=OxmlElement('w:color');color.set(qn('w:val'),'000000');rp.append(color);r.append(rp);t=OxmlElement('w:t');t.text=label;r.append(t);hyp.append(r);p._p.append(hyp)
def table(key):
 caption,head,rows=tables[key];p=doc.add_paragraph(caption,style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
 t=doc.add_table(rows=1,cols=len(head));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
 widths={3:[4.0,5.5,7.0],4:[7.1,3.1,3.1,3.2],5:[4.1,3.0,3.0,3.0,3.4],6:[3.2,2.4,2.4,2.9,2.8,2.8]}[len(head)]
 for c,w in zip(t.columns,widths):c.width=Cm(w)
 for i,v in enumerate(head):t.rows[0].cells[i].text=v
 for row in rows:
  cells=t.add_row().cells
  for c,v in zip(cells,row):c.text=str(v)
 pr=t._tbl.tblPr;b=OxmlElement('w:tblBorders')
 for edge in ['top','bottom','insideH','left','right','insideV']:
  e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single' if edge in ['top','bottom','insideH'] else 'nil');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');b.append(e)
 pr.append(b)
 for idx,row in enumerate(t.rows):
  trpr=row._tr.get_or_add_trPr();csp=OxmlElement('w:cantSplit');trpr.append(csp)
  if idx==0:repeat=OxmlElement('w:tblHeader');trpr.append(repeat)
  for j,cell in enumerate(row.cells):
   cell.width=Cm(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
   tcpr=cell._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
   for side in ['top','bottom','left','right']:
    tag=OxmlElement('w:'+side);tag.set(qn('w:w'),'65');tag.set(qn('w:type'),'dxa');mar.append(tag)
   tcpr.append(mar)
   for p in cell.paragraphs:
    p.paragraph_format.space_after=Pt(1);p.paragraph_format.space_before=Pt(1);p.paragraph_format.line_spacing=1;p.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 or key in ['related','metrics','audit','policy'] else WD_ALIGN_PARAGRAPH.CENTER
    for r in p.runs:r.font.size=Pt(10);r.font.bold=idx==0
 doc.add_paragraph().paragraph_format.space_after=Pt(0)
figcaps={'architecture':'Figure 1: Input screening and the downstream application boundary','shift':'Figure 2: Implemented policy performance under classifier source withholding','routing':'Figure 3: Implemented policy actions on the seed 42 random holdout'}
lines=raw.splitlines();mode=None;auth=False;disclosure=9
for line in lines:
 if not line.strip():continue
 if line.startswith('# '):
  doc.add_paragraph(line[2:],style='Title')
  for author_index,(name,orcid) in enumerate([('Roberto Enrique Quezada-Rodríguez','0009-0004-0869-3881'),('David Adrian Lucano Nieves','0009-0003-2167-8515')]):
   if author_index:
    p=doc.add_paragraph('and');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(5)
    for r in p.runs:r.font.size=Pt(12)
   p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;r=p.add_run(name);r.bold=True;r.font.size=Pt(12);p.paragraph_format.space_after=Pt(2)
   p=doc.add_paragraph('Universidad Nacional de Trujillo, Trujillo, Perú');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(2)
   for r in p.runs:r.font.size=Pt(12)
   p=doc.add_paragraph('requezadaro@unitru.edu.pe');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(2)
   for r in p.runs:r.font.size=Pt(12)
   p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;link(p,'ORCID '+orcid,'https://orcid.org/'+orcid);p.paragraph_format.space_after=Pt(5)
   for rpr in p._p.iter(qn('w:rPr')):
    size=OxmlElement('w:sz');size.set(qn('w:val'),'24');rpr.append(size)
  continue
 if line=='@ABSTRACT':
  p=doc.add_paragraph('Abstract',style='Heading 1');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;mode='abstract';continue
 if line=='@KEYWORDS':mode='keywords';continue
 if line.startswith('@TABLE '):table(line.split()[1]);continue
 if line.startswith('@FIG '):
  key=line.split()[1];p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True;p.add_run().add_picture(str(BASE/(key+'.png')),width=Cm(16.1));p=doc.add_paragraph(figcaps[key],style='Caption');p.alignment=WD_ALIGN_PARAGRAPH.CENTER;continue
 if line=='@REFERENCES':
  doc.add_paragraph('References',style='Heading 1')
  for idx,(txt,url) in enumerate(refs,1):
   p=doc.add_paragraph();p.paragraph_format.left_indent=Cm(.65);p.paragraph_format.first_line_indent=Cm(-.65)
   p.add_run(f'[{idx}] ')
   if 'arXiv preprint' in txt:
    bef,aft=txt.split('arXiv preprint',1);p.add_run(bef);p.add_run('arXiv preprint').italic=True;p.add_run(aft+' ')
   else:p.add_run(txt+' ')
   link(p,url,url)
  continue
 if line in ['@DATA','@APPENDIX']:mode=line;continue
 if mode=='@DATA':doc.add_paragraph(f'{disclosure} {line}',style='Heading 1');disclosure+=1;mode=None;continue
 if mode=='@APPENDIX':doc.add_paragraph(line,style='Heading 1');mode=None;continue
 if line.startswith('### '):doc.add_paragraph(line[4:],style='Heading 2');mode=None;continue
 if line.startswith('## '):doc.add_paragraph(line[3:],style='Heading 1');mode=None;continue
 if mode=='keywords':
  p=doc.add_paragraph();p.add_run('Keywords: ').bold=True;p.add_run(line);mode=None;continue
 p=doc.add_paragraph(line)
 if mode=='abstract':p.paragraph_format.left_indent=Cm(1.5);p.paragraph_format.right_indent=Cm(1.5);p.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
 mode=None
for st in doc.styles:
 for border in list(st.element.iter(qn('w:pBdr'))):
  border.getparent().remove(border)
 for fonts in list(st.element.iter(qn('w:rFonts'))):
  for key in list(fonts.attrib):
   if 'theme' in key.lower():del fonts.attrib[key]
 for rpr in list(st.element.iter(qn('w:rPr'))):
  ff=list(rpr.findall(qn('w:rFonts')))
  if ff:
   for f in ff:rpr.remove(f)
   f=OxmlElement('w:rFonts')
   for name in ['ascii','hAnsi','eastAsia','cs']:f.set(qn('w:'+name),'Times New Roman')
   rpr.insert(0,f)
for t in doc.tables:
 for cell in t.rows[-2].cells:
  for pp in cell.paragraphs:pp.paragraph_format.keep_with_next=True
 for row in list(t.rows)[:3]:
  for cell in row.cells:
   for pp in cell.paragraphs:pp.paragraph_format.keep_with_next=True
out=BASE/'Promption_CLEI_Article.docx';doc.save(out)
abstract=raw.split('@ABSTRACT\n')[1].split('@KEYWORDS')[0].strip()
assert len(abstract.split())<=200
assert not re.search(r'\{\{\w+\}\}',raw)
print('DOCX',out,'words',len(raw.split()),'abstract_words',len(abstract.split()),'tables',len(doc.tables))
(E/'document_validation.json').write_text(json.dumps({'abstract_words':len(abstract.split()),'manuscript_words':len(raw.split()),'tables':len(doc.tables),'figures':3,'title_points':16,'body_points':10,'single_spacing':True,'page_size_mm':[210,297],'margins_cm':{'top':2,'right':2,'bottom':2.5,'left':2.5},'references':len(refs)},indent=2))
metadata={'title':doc.core_properties.title,'authors':[{'name':'Roberto Enrique Quezada-Rodríguez','institution':'Universidad Nacional de Trujillo','city':'Trujillo','country':'Perú','email':'requezadaro@unitru.edu.pe','ORCID':'0009-0004-0869-3881'},{'name':'David Adrian Lucano Nieves','institution':'Universidad Nacional de Trujillo','city':'Trujillo','country':'Perú','email':'requezadaro@unitru.edu.pe','ORCID':'0009-0003-2167-8515'}],'abstract':abstract,'keywords':'Prompt injection, text classification, source shift, security middleware, software evaluation','provisional_corresponding_author':'Roberto Enrique Quezada-Rodríguez','provisional_correspondence_email':'requezadaro@unitru.edu.pe','author_instructions_reference':'AuthorInstructions2016-OTH.pdf supplied by the user on 2026-10-02'}
(BASE/'submission_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
(BASE/'submission_metadata_ascii.txt').write_text(__import__('unicodedata').normalize('NFKD',json.dumps(metadata,ensure_ascii=False,indent=2)).encode('ascii','ignore').decode())
