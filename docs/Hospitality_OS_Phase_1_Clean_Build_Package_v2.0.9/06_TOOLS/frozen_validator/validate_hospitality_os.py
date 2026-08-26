#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, sys, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
GATES=['M0','M0R','M1','M2','M3','M4','M5a','M5b','M6']; GI={g:i for i,g in enumerate(GATES)}
TEST_RE=re.compile(r'^TST-(M0R|M0|M1|M2|M3|M4|M5a|M5b|M6)-(.+)$')
REQ_RE=re.compile(r'^FR-[A-Z0-9]+-[0-9]{3}[A-Z]?$')
class V:
 def __init__(self): self.f=[]
 def ck(self,c,code,d):
  if not c:self.f.append({'code':code,'detail':str(d)})

def cb(o):return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sh(o):return hashlib.sha256(cb(o)).hexdigest()
def sf(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def safe(target,tmp):
 p=Path(target)
 if p.is_dir():return p
 with zipfile.ZipFile(p) as z:
  if z.testzip():raise ValueError('corrupt zip')
  if any(n.startswith('/') or '..' in Path(n).parts for n in z.namelist()):raise ValueError('unsafe zip')
  z.extractall(tmp)
 roots=[x for x in Path(tmp).iterdir() if x.is_dir()]
 return roots[0] if len(roots)==1 else Path(tmp)
def load(root,rel,v):
 try:return json.loads((root/rel).read_text(encoding='utf-8'))
 except Exception as e:v.ck(False,'JSON_READ',f'{rel}:{e}');return {}
def checksums(root,v):
 p=root/'SHA256SUMS.txt';v.ck(p.exists(),'CHECKSUM_MANIFEST','missing')
 if not p.exists():return
 listed={}
 for line in p.read_text().splitlines():
  if not line:continue
  m=re.match(r'^([a-f0-9]{64})  \./(.+)$',line);v.ck(bool(m),'CHECKSUM_ROW',line)
  if m:listed[m.group(2)]=m.group(1)
 physical={str(x.relative_to(root)).replace('\\','/') for x in root.rglob('*') if x.is_file() and x.name!='SHA256SUMS.txt'}
 v.ck(set(listed)==physical,'CHECKSUM_SET',f'{len(listed)} vs {len(physical)}')
 for rel,d in listed.items():v.ck((root/rel).exists() and sf(root/rel)==d,'CHECKSUM_MISMATCH',rel)
def xlsx(path,v):
 try:
  with zipfile.ZipFile(path) as z:
   ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
   shared=[]
   if 'xl/sharedStrings.xml' in z.namelist():
    rt=ET.fromstring(z.read('xl/sharedStrings.xml'))
    for si in rt.findall('m:si',ns):shared.append(''.join(t.text or '' for t in si.findall('.//m:t',ns)))
   wb=ET.fromstring(z.read('xl/workbook.xml'));rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
   rmap={x.attrib['Id']:x.attrib['Target'] for x in rels};out={}
   for s in wb.find('m:sheets',ns):
    name=s.attrib['name'];rid=s.attrib['{'+ns['r']+'}id'];target=rmap[rid]
    if target.startswith('/'):target=target[1:]
    elif not target.startswith('xl/'):target='xl/'+target
    xml=ET.fromstring(z.read(target));rows=[]
    for row in xml.findall('.//m:sheetData/m:row',ns):
     cells={}
     for c in row.findall('m:c',ns):
      ref=c.attrib.get('r','');col=re.match(r'[A-Z]+',ref).group(0);typ=c.attrib.get('t');val=''
      if typ=='inlineStr':val=''.join(x.text or '' for x in c.findall('.//m:t',ns))
      else:
       ve=c.find('m:v',ns);raw='' if ve is None else (ve.text or '')
       val=shared[int(raw)] if typ=='s' and raw else ('TRUE' if typ=='b' and raw=='1' else ('FALSE' if typ=='b' else raw))
      cells[col]=val
     rows.append(cells)
    out[name]=rows
   return out
 except Exception as e:v.ck(False,'XLSX_PARSE',e);return {}
def ci(c):
 n=0
 for x in c:n=n*26+ord(x)-64
 return n-1
def col(i):
 s='';n=i+1
 while n:n,r=divmod(n-1,26);s=chr(65+r)+s
 return s
def dicts(sheets,name,v):
 v.ck(name in sheets,'SHEET_MISSING',name)
 if name not in sheets:return []
 rows=sheets[name];mx=max((ci(k) for r in rows for k in r),default=-1);mat=[[r.get(col(i),'') for i in range(mx+1)] for r in rows]
 if not mat:return []
 h=mat[0];return [{h[i]:row[i] if i<len(row) else '' for i in range(len(h)) if h[i]} for row in mat[1:] if any(str(x).strip() for x in row)]
def validate(root,v):
 req=load(root,'canonical/reconciled_requirements.json',v);dec=load(root,'canonical/reconciled_decisions.json',v);lin=load(root,'canonical/original_requirement_lineage.json',v);am=load(root,'canonical/amendment_register.json',v);fi=load(root,'canonical/finding_register.json',v);res=load(root,'canonical/residual_issues.json',v);man=load(root,'PACKAGE_MANIFEST.json',v);rd=load(root,'CANONICAL_CONTENT_ROOT.json',v)
 if v.f:return
 for e in rd.get('semantic_entries',[]):v.ck(sh(load(root,e['file'],v))==e['semantic_sha256'],'SEMANTIC_HASH',e['file'])
 v.ck(sh({'version':rd.get('version'),'semantic_entries':rd.get('semantic_entries',[])})==rd.get('canonical_content_root_sha256'),'CONTENT_ROOT','root')
 v.ck(man.get('canonical_content_root_sha256')==rd.get('canonical_content_root_sha256'),'MANIFEST_ROOT','root')
 rs=req.get('active_requirements',[]);v.ck(len(rs)==336,'REQ_COUNT',len(rs));by={r.get('id'):r for r in rs};v.ck(len(by)==336,'REQ_DUP','ids')
 clause_count=0
 required=['clause_id','exact_clause_text','introduced_at','revalidated_at','prerequisite_components','prerequisite_requirement_ids','artifacts_available_at_introduction','gate_local_behavior','later_behavior','journey_links','engineering_test_links','deferred_domain_risk','deferred_domain_notes','reviewer_rationale','reviewer_confidence','disagreement_category','review_status']
 for rid,r in by.items():
  v.ck(bool(REQ_RE.match(rid)),'REQ_ID',rid);clauses=r.get('clauses',[]);v.ck(bool(clauses),'CLAUSE_EMPTY',rid);clause_count+=len(clauses);union=[]
  for c in clauses:
   for f in required:v.ck(f in c,'CLAUSE_FIELD',f'{rid}:{c.get("clause_id")}:{f}')
   v.ck('source_clause_text' not in c and 'required_behavior' not in c,'CLAUSE_SUBSTITUTE_FIELD',rid)
   v.ck(bool(str(c.get('exact_clause_text','')).strip()),'CLAUSE_TEXT_EMPTY',rid)
   gates=[c.get('introduced_at')]+list(c.get('revalidated_at',[]));tests=c.get('engineering_test_links',[])
   v.ck(len(tests)==len(gates),'CLAUSE_TEST_COUNT',c.get('clause_id'))
   for t,g in zip(tests,gates):
    m=TEST_RE.match(t);v.ck(bool(m),'TEST_PATTERN',t)
    if m:v.ck(m.group(1)==g,'TEST_GATE',f'{t}:{g}');v.ck(m.group(2).startswith(rid),'TEST_ID_PREFIX',f'{rid}:{t}')
   for t in tests:
    if t not in union:union.append(t)
  v.ck(r.get('engineering_test_links')==union,'TOP_ENGINEERING_TEST_UNION',rid)
  v.ck(r.get('acceptance_test_ids')==union,'TOP_ACCEPTANCE_TEST_UNION',rid)
 v.ck(clause_count==337,'CLAUSE_COUNT',clause_count)
 v.ck(len(lin.get('lineage',[]))==294,'LINEAGE_COUNT',len(lin.get('lineage',[])));v.ck(len(lin.get('split_register',[]))==32,'SPLIT_COUNT',len(lin.get('split_register',[])))
 for s in lin.get('split_register',[]):v.ck(bool(s.get('split_reason')),'SPLIT_REASON_EMPTY',s.get('original_id'))
 dm={d['id']:d for d in dec.get('decisions',[])};v.ck(len(dm)==120,'DEC_COUNT',len(dm))
 v.ck('AMD-V208-002' in dm['D-100'].get('source',''),'D100_PROVENANCE',dm['D-100'].get('source'))
 v.ck('JSON and workbook projections' in dm['D-100'].get('decision','') and 'YAML' not in dm['D-100'].get('decision',''),'D100_JSON_WORDING',dm['D-100'].get('decision'));v.ck('exact pinned package' in dm['D-102'].get('decision','').lower(),'D102_STALE_REUSE',dm['D-102'].get('decision'))
 # Executable normative forbidden-surface vocabulary.
 rule_path=Path(__file__).with_name('forbidden_surface_rules.json')
 rules=json.loads(rule_path.read_text(encoding='utf-8'))
 positive_verbs={x.lower() for x in rules.get('positive_obligation_verbs',[])}
 v.ck({'enable','provide','capture','record','expose'}.issubset(positive_verbs),'POSITIVE_VERB_COVERAGE',sorted(positive_verbs))
 # Every declared forbidden domain and every recorded sense must be populated.
 v.ck(len(rules.get('forbidden_positive_obligations',{}))>=11,'FORBIDDEN_DOMAIN_COUNT',len(rules.get('forbidden_positive_obligations',{})))
 for domain,terms in rules.get('forbidden_positive_obligations',{}).items(): v.ck(bool(terms),'FORBIDDEN_DOMAIN_EMPTY',domain)
 # M5a exact service-boundary requirement.
 edg=by.get('FR-EDG-002A',{}).get('required_behavior','').lower()
 v.ck('exactly the five named services' in edg,'M5A_FIVE_SERVICE_REQUIREMENT','FR-EDG-002A')
 v.ck('backup agent' not in edg,'M5A_BACKUP_AGENT_LEAK','FR-EDG-002A')

 v.ck(len(am.get('amendments',[]))==20,'AMEND_COUNT',len(am.get('amendments',[])));v.ck(len(fi.get('findings',[]))==22,'FIND_COUNT',len(fi.get('findings',[])))
 for a in am.get('amendments',[]):
  for f in ['amendment_id','title','source','affected_ids','old_value','new_value','change','reason','semantic_behavior_change','verification','residual_risk']:v.ck(f in a,'AMEND_FIELD',f'{a.get("amendment_id")}:{f}')
 for f in fi.get('findings',[]):
  for x in ['finding_id','severity','title','finding','disposition','affected_canonical_ids','affected_files','verification','residual_risk']:v.ck(x in f,'FIND_FIELD',f'{f.get("finding_id")}:{x}')
  v.ck(f.get('disposition') not in {'deferred_to_next_controlled_step','resolved_for_next_generation','resolved_for_reconciliation'},'STALE_FINDING_STATE',f.get('finding_id'))
 v.ck('Blind Mutation Round 2' in res.get('completed_controls',[]),'STALE_LIFECYCLE','blind round 2');v.ck('v2.0.8' in res.get('current_lifecycle_state',''),'STALE_LIFECYCLE','current state')
 wbpath=root/man.get('primary_files',{}).get('workbook','');v.ck(wbpath.exists(),'WORKBOOK_MISSING',wbpath)
 if wbpath.exists():
  shs=xlsx(wbpath,v);ar=dicts(shs,'Active Requirements',v);cm=dicts(shs,'Clause Register',v);dr=dicts(shs,'Decision Register',v);sr=dicts(shs,'Requirement Splits',v);aa=dicts(shs,'Amendments',v);ff=dicts(shs,'Findings',v)
  v.ck(len(ar)==336,'XLSX_REQ_COUNT',len(ar));v.ck(len(cm)==337,'XLSX_CLAUSE_COUNT',len(cm));v.ck(len(dr)==120,'XLSX_DEC_COUNT',len(dr));v.ck(len(sr)==32,'XLSX_SPLIT_COUNT',len(sr));v.ck(len(aa)==20,'XLSX_AMEND_COUNT',len(aa));v.ck(len(ff)==22,'XLSX_FIND_COUNT',len(ff))
  amap={x.get('ID'):x for x in ar};cmap={(x.get('Requirement ID'),x.get('Clause ID')):x for x in cm};dmap={x.get('ID'):x for x in dr}
  for rid,r in by.items():
   row=amap.get(rid);v.ck(row is not None,'XLSX_REQ_MISSING',rid)
   if row:
    for c,e in [('Title',r['title']),('Acceptance Test IDs',', '.join(r['acceptance_test_ids'])),('Classification',r['classification']),('Component Path',r['component_path'])]:v.ck(row.get(c,'')==e,'XLSX_REQ_PARITY',f'{rid}:{c}')
   for c in r['clauses']:
    row=cmap.get((rid,c['clause_id']));v.ck(row is not None,'XLSX_CLAUSE_MISSING',f'{rid}:{c["clause_id"]}')
    if row:v.ck(row.get('Exact Clause Text','')==c['exact_clause_text'],'XLSX_CLAUSE_TEXT',f'{rid}:{c["clause_id"]}')
  for did,d in dm.items():
   row=dmap.get(did);v.ck(row is not None,'XLSX_DEC_MISSING',did)
   if row:v.ck(row.get('Decision','')==d['decision'],'XLSX_DEC_PARITY',did)
 checksums(root,v)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('target',nargs='?',default='.');ap.add_argument('--json-report');a=ap.parse_args();v=V()
 try:
  with tempfile.TemporaryDirectory() as td:validate(safe(a.target,td),v)
 except Exception as e:v.ck(False,'RUNTIME',e)
 rep={'validator_version':'1.0.5','passed':not v.f,'failure_count':len(v.f),'failures':v.f}
 if a.json_report:Path(a.json_report).write_text(json.dumps(rep,indent=2)+'\n')
 if v.f:
  for f in v.f:print(f"FAIL {f['code']}: {f['detail']}",file=sys.stderr)
  return 1
 print('PASS HOSPITALITY_OS_FROZEN_VALIDATOR');print(json.dumps(rep,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
