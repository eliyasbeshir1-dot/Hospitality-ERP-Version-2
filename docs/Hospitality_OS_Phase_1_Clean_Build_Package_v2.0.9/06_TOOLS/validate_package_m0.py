#!/usr/bin/env python3
"""Hospitality OS v2.0.9 authoritative Package M0 validator template."""
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, re, stat, subprocess, sys, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PACKAGE_VERSION='2.0.9'
CANON_ZIP_SHA='804dc9e81aaa29826f77961681287d5bd1eaa2ac6ef5ddc3ae598db4e5e0fd32'
VALIDATOR_ZIP_SHA='628ae551120497280a82fdfcf8fd8bd2a69e4c893b400cd94d1914529788cce9'
VALIDATOR_SCRIPT_SHA='ee65b8ec3292db19798f785e23a2d54969eadd91f00e98888520d16051c9f7b0'
WORKBOOK_MODEL_SHA='dd260efcb785f37eb49c7074aba8414b7e2c9b44fa308fdbdf14bc1f354771d7'
EXPECTED_INPUT_PINS=json.loads('{"baseline-zip":"e65fa9af0603c13a76c08961dbac44ee5da34192b3e0433c42590c7599830ba7","canonical-source-zip":"804dc9e81aaa29826f77961681287d5bd1eaa2ac6ef5ddc3ae598db4e5e0fd32","detection-module":"7bb11538491b844cbe8149efd1c9adf20e99756605d41712335b5f842b11456d","governed-fields":"7e524c6190dad135b197eecfff59954fd19c3bf8bcad2b47fa8bfb227f6528a2","mechanism-suite":"31c5c47d9c2fea22a1f31835288ff43c37b1acb7904da4611796f7fac819c144","occurrence-registry":"d4dae27e4a97bfd710b50412f488a994232c6573441f3a3778d346fdbbf9dcb2","occurrence-schema":"b501312988ce9db85151f7826c863f1de2edea379966d1bbe923b27161ac7d59","occurrence-validator":"ee65b8ec3292db19798f785e23a2d54969eadd91f00e98888520d16051c9f7b0","validator-freeze-zip":"628ae551120497280a82fdfcf8fd8bd2a69e4c893b400cd94d1914529788cce9"}')
ACTIVE_NEXT_GATE='Independent Codex review of pinned Package M0 v2.0.9. M0R remains blocked until approval.'
ACTIVE_LIFECYCLE_STATE='v2.0.9 focused repair candidate prepared for independent Package M0 review.'
CANONICAL_NEXT_GATE_V208='Independent Codex review of pinned Package M0 v2.0.8. M0R remains blocked until approval.'
CANONICAL_LIFECYCLE_STATE_V208='v2.0.8 focused repair candidate prepared for independent Package M0 review.'

class V:
 def __init__(self):self.f=[]
 def ck(self,condition,code,detail):
  if not condition:self.f.append({'code':code,'detail':str(detail)})

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for chunk in iter(lambda:stream.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()

def is_reparse(path):
 try:
  attrs=getattr(Path(path).lstat(),'st_file_attributes',0)
  return Path(path).is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(path)) or bool(attrs&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))
 except OSError:return False

def assert_plain_tree(root):
 root=Path(root)
 for path in [root,*root.parents,*root.rglob('*')]:
  if path.exists() and is_reparse(path):raise ValueError(f'reparse point prohibited: {path}')

def relative_to(path,parent):
 try:Path(path).relative_to(parent);return True
 except ValueError:return False

def validated_temp_root():
 roots=[]
 for name in ('TEMP','TMP'):
  raw=os.environ.get(name)
  if raw is None or not raw.strip() or '..' in Path(raw).parts or not Path(raw).is_absolute():raise ValueError(f'{name} must be a nonempty absolute traversal-free path')
  path=Path(os.path.abspath(raw));assert_plain_tree(path);path=path.resolve(strict=True)
  if not path.is_dir() or len(path.parts)<3:raise ValueError(f'{name} is not a safe directory')
  roots.append(path)
 if os.path.normcase(str(roots[0]))!=os.path.normcase(str(roots[1])):raise ValueError('TEMP and TMP conflict')
 return roots[0]

def load(root,rel,v):
 try:return json.loads((root/rel).read_text(encoding='utf-8'))
 except Exception as error:v.ck(False,'JSON_READ',f'{rel}:{error}');return {}

def iter_extracted(target,temp_root):
 with tempfile.TemporaryDirectory(prefix='v209-validator-',dir=str(temp_root)) as td:
  staging=Path(td)
  with zipfile.ZipFile(target) as archive:
   if archive.testzip():raise ValueError('corrupt zip')
   for info in archive.infolist():
    name=info.filename;mode=(info.external_attr>>16)&0o170000
    if name.startswith(('/',chr(92))) or '..' in Path(name).parts or mode==0o120000:raise ValueError(f'unsafe zip member: {name}')
    if '__pycache__' in Path(name).parts or Path(name).suffix.lower() in {'.pyc','.pyo'}:raise ValueError(f'compiled cache: {name}')
   archive.extractall(staging)
  roots=[path for path in staging.iterdir() if path.is_dir()]
  if len(roots)!=1 or any(not path.is_dir() for path in staging.iterdir()):raise ValueError('archive must contain one root')
  assert_plain_tree(roots[0]);yield roots[0]

def checksums(root,v):
 path=root/'SHA256SUMS.txt';v.ck(path.is_file(),'CHECKSUMS_MISSING',path)
 if not path.is_file():return
 listed={}
 for line in path.read_text(encoding='utf-8').splitlines():
  match=re.match(r'^([a-f0-9]{64})  \./(.+)$',line);v.ck(bool(match),'CHECKSUM_ROW',line)
  if match:listed[match.group(2)]=match.group(1)
 physical={item.relative_to(root).as_posix() for item in root.rglob('*') if item.is_file() and item.name!='SHA256SUMS.txt'}
 v.ck(set(listed)==physical,'CHECKSUM_SET',f'{len(listed)}/{len(physical)}')
 for rel,digest in listed.items():v.ck((root/rel).is_file() and sha(root/rel)==digest,'CHECKSUM_MISMATCH',rel)

def column_index(name):
 value=0
 for char in name:value=value*26+ord(char)-64
 return value-1

def column_name(index):
 value='';number=index+1
 while number:number,remainder=divmod(number-1,26);value=chr(65+remainder)+value
 return value

def parse_xlsx(path):
 unsafe=[];result={}
 with zipfile.ZipFile(path) as archive:
  if archive.testzip():raise ValueError(f'corrupt workbook: {path}')
  ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
  shared=[]
  if 'xl/sharedStrings.xml' in archive.namelist():
   tree=ET.fromstring(archive.read('xl/sharedStrings.xml'));shared=[''.join(node.text or '' for node in item.findall('.//m:t',ns)) for item in tree.findall('m:si',ns)]
  workbook=ET.fromstring(archive.read('xl/workbook.xml'));relationships=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'));targets={item.attrib['Id']:item.attrib['Target'] for item in relationships}
  for sheet in workbook.find('m:sheets',ns):
   name=sheet.attrib['name'];target=targets[sheet.attrib['{'+ns['r']+'}id']]
   if target.startswith('/'):target=target[1:]
   elif not target.startswith('xl/'):target='xl/'+target
   tree=ET.fromstring(archive.read(target));rows=[]
   for row in tree.findall('.//m:sheetData/m:row',ns):
    cells={}
    for cell in row.findall('m:c',ns):
     ref=cell.attrib.get('r','');match=re.match(r'[A-Z]+',ref)
     if not match:continue
     typ=cell.attrib.get('t');formula=cell.find('m:f',ns)
     if formula is not None or typ=='e':unsafe.append(f'{name}!{ref}')
     if typ=='inlineStr':value=''.join(node.text or '' for node in cell.findall('.//m:t',ns))
     else:
      node=cell.find('m:v',ns);raw='' if node is None else (node.text or '');value=shared[int(raw)] if typ=='s' and raw else raw
     cells[match.group(0)]=value
    rows.append(cells)
   width=max((column_index(key) for row in rows for key in row),default=-1)+1
   result[name]=[[row.get(column_name(index),'') for index in range(width)] for row in rows]
 return result,unsafe

def normalized(rows):return [['' if value is None else '1' if value is True else '0' if value is False else str(value) for value in row] for row in rows]

def workbook_parity(path,expected,v,label):
 v.ck(path.is_file(),'WORKBOOK_MISSING',path)
 if not path.is_file():return
 try:actual,unsafe=parse_xlsx(path)
 except Exception as error:v.ck(False,'WORKBOOK_READ',f'{label}:{error}');return
 expected_names=[item[0] for item in expected];v.ck(list(actual)==expected_names,'WORKBOOK_SHEET_SET',f'{label}:{list(actual)} != {expected_names}');v.ck(not unsafe,'WORKBOOK_FORMULA_OR_ERROR',f'{label}:{unsafe}')
 for name,rows,*_ in expected:v.ck(actual.get(name)==normalized(rows),'WORKBOOK_PARITY',f'{label}:{name}')

def canon(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def semhash(obj):return hashlib.sha256(canon(obj)).hexdigest()

def projected_residual(value):
 value=json.loads(json.dumps(value))
 if value.get('next_gate')!=CANONICAL_NEXT_GATE_V208 or value.get('current_lifecycle_state')!=CANONICAL_LIFECYCLE_STATE_V208:raise ValueError('canonical residual lifecycle projection precondition changed')
 value['next_gate']=ACTIVE_NEXT_GATE;value['current_lifecycle_state']=ACTIVE_LIFECYCLE_STATE
 return value

def load_model(root,v):
 path=root/'06_TOOLS/workbook_projection_model.py';valid=path.is_file() and not is_reparse(path) and sha(path)==WORKBOOK_MODEL_SHA
 v.ck(valid,'WORKBOOK_MODEL_PIN',path)
 if not valid:return None
 spec=importlib.util.spec_from_file_location('v209_pinned_workbook_model',path)
 if spec is None or spec.loader is None:v.ck(False,'WORKBOOK_MODEL_LOAD','no loader');return None
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def validate(root,v,temp_root):
 root=Path(root).resolve(strict=True);assert_plain_tree(root)
 if temp_root==root or relative_to(temp_root,root):raise ValueError('temporary root is equal to or inside target package')
 compiled=[item.relative_to(root).as_posix() for item in root.rglob('*') if item.is_file() and ('__pycache__' in item.parts or item.suffix.lower() in {'.pyc','.pyo'})]
 v.ck(not compiled,'COMPILED_CACHE',compiled);v.ck(not list(root.rglob('forbidden_scan.py')),'OBSOLETE_SCANNER','forbidden_scan.py')
 content=load(root,'CANONICAL_CONTENT_ROOT.json',v);manifest=load(root,'00_PACKAGE_CONTROL/PACKAGE_MANIFEST.json',v);generation=load(root,'00_PACKAGE_CONTROL/GENERATION_MANIFEST.json',v);inventory=load(root,'00_PACKAGE_CONTROL/PACKAGE_INVENTORY.json',v)
 semantic_entries=[]
 for path in sorted((root/'02_MACHINE_READABLE').glob('*.json')):semantic_entries.append({'path':path.relative_to(root).as_posix(),'semantic_sha256':semhash(load(root,path.relative_to(root).as_posix(),v))})
 calculated_root=hashlib.sha256(canon({'version':PACKAGE_VERSION,'semantic_entries':semantic_entries})).hexdigest()
 v.ck(content=={'version':PACKAGE_VERSION,'canonical_content_root_sha256':calculated_root,'semantic_entries':semantic_entries},'CONTENT_ROOT_PARITY',calculated_root)
 v.ck(manifest.get('package_version')==PACKAGE_VERSION and manifest.get('package_name')==f'Hospitality_OS_Phase_1_Clean_Build_Package_v{PACKAGE_VERSION}','PACKAGE_MANIFEST_VERSION',manifest.get('package_version'))
 v.ck(manifest.get('canonical_content_root_sha256')==calculated_root,'PACKAGE_MANIFEST_ROOT',manifest.get('canonical_content_root_sha256'))
 v.ck(manifest.get('canonical_source',{}).get('sha256')==CANON_ZIP_SHA,'PACKAGE_MANIFEST_CANON_PIN',manifest.get('canonical_source'))
 v.ck(manifest.get('validator',{}).get('sha256')==VALIDATOR_SCRIPT_SHA,'PACKAGE_MANIFEST_VALIDATOR_PIN',manifest.get('validator'))
 v.ck(generation.get('package_version')==PACKAGE_VERSION and generation.get('canonical_content_root_sha256')==calculated_root,'GENERATION_CONTROL','version/root')
 v.ck(generation.get('input_pins')==EXPECTED_INPUT_PINS,'GENERATION_INPUT_PINS',generation.get('input_pins'))
 v.ck(generation.get('workbook_projection_model_sha256')==WORKBOOK_MODEL_SHA,'WORKBOOK_MODEL_MANIFEST_PIN',generation.get('workbook_projection_model_sha256'))
 validator_path=root/'06_TOOLS/validate_package_m0.py';validator_digest=sha(validator_path) if validator_path.is_file() else ''
 v.ck(generation.get('package_validator_sha256')==validator_digest,'PACKAGE_VALIDATOR_PARITY','generation manifest')
 v.ck(manifest.get('package_validator')=={'path':'06_TOOLS/validate_package_m0.py','sha256':validator_digest},'PACKAGE_VALIDATOR_PARITY','package manifest')
 expected_profile={'package_version':PACKAGE_VERSION,'validator_path':'06_TOOLS/validate_package_m0.py','validator_sha256':validator_digest}
 v.ck(generation.get('p208_validator_profile')==expected_profile,'P208_VALIDATOR_PROFILE','generation manifest')
 v.ck(manifest.get('p208_validator_profile')==expected_profile,'P208_VALIDATOR_PROFILE','package manifest')
 physical=generation.get('physical_input_artifacts',{})
 expected_paths={
  'canonical-source-zip':'01_CANONICAL_SOURCE/Hospitality_OS_Reconciled_Canonical_Register_v0.1.4.zip',
  'validator-freeze-zip':'01_CANONICAL_SOURCE/Hospitality_OS_Validator_Freeze_v1.0.5.zip',
  'baseline-zip':'01_CANONICAL_SOURCE/Hospitality_OS_Canonical_Baseline_Freeze_v0.1.zip',
  'occurrence-registry':'08_HISTORY/INPUTS/canonical_occurrence_registry.json','governed-fields':'02_MACHINE_READABLE/governed_fields.json',
  'occurrence-schema':'07_SCHEMAS/forbidden_occurrence_registry.schema.json','occurrence-validator':'06_TOOLS/frozen_validator/forbidden_occurrence_validator.py',
  'detection-module':'06_TOOLS/frozen_validator/occurrence_mechanism.py','mechanism-suite':'06_TOOLS/test_occurrence_mechanism.py'}
 v.ck(set(physical)==set(expected_paths),'PHYSICAL_INPUT_SET',set(physical))
 for key,path in expected_paths.items():
  item=root/path;actual=sha(item) if item.is_file() and not is_reparse(item) else ''
  v.ck(actual==EXPECTED_INPUT_PINS[key] and physical.get(key)=={'path':path,'sha256':EXPECTED_INPUT_PINS[key]},'PHYSICAL_INPUT_PIN',key)
 for field in ('text_projections','binary_projections'):
  for rel,digest in generation.get(field,{}).items():v.ck((root/rel).is_file() and sha(root/rel)==digest,'GENERATION_PROJECTION_HASH',f'{field}:{rel}')
 v.ck(inventory.get('package_version')==PACKAGE_VERSION,'INVENTORY_VERSION',inventory.get('package_version'))
 canonical_zip=root/expected_paths['canonical-source-zip'];occurrence_validator=root/expected_paths['occurrence-validator']
 child_dir=tempfile.TemporaryDirectory(prefix='v209-occurrence-',dir=str(temp_root))
 try:
  child_temp=Path(child_dir.name);child_env={key:os.environ[key] for key in ('SystemRoot','WINDIR') if key in os.environ}
  child_env.update({'TEMP':str(child_temp),'TMP':str(child_temp),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','PYTHONNOUSERSITE':'1'})
  process=subprocess.run([str(Path(sys.executable).resolve(strict=True)),str(occurrence_validator.resolve(strict=True)),str(root)],capture_output=True,text=True,cwd=str(root),env=child_env)
  v.ck(process.returncode==0,'OCCURRENCE_VALIDATOR',(process.stdout+process.stderr)[-2000:])
 finally:child_dir.cleanup()
 registry=load(root,'02_MACHINE_READABLE/canonical_registry.json',v);v.ck(registry.get('authority_order',[None])[0]=='canonical source ZIP v0.1.4','CANONICAL_AUTHORITY',registry.get('authority_order'))
 rules=load(root,'02_MACHINE_READABLE/forbidden_surface_rules.json',v);frozen_rules=load(root,'06_TOOLS/frozen_validator/forbidden_surface_rules.json',v);v.ck(rules==frozen_rules,'RULES_PARITY','machine/frozen')
 with tempfile.TemporaryDirectory(prefix='v209-canonical-',dir=str(temp_root)) as td:
  with zipfile.ZipFile(canonical_zip) as archive:archive.extractall(td)
  canonical_root=next(Path(td).iterdir())
  mapping=[('requirements.json','canonical/reconciled_requirements.json'),('decisions.json','canonical/reconciled_decisions.json'),('original_requirement_lineage.json','canonical/original_requirement_lineage.json'),('amendment_register.json','canonical/amendment_register.json'),('finding_register.json','canonical/finding_register.json'),('journeys.json','canonical/reconciled_journeys.json'),('reconciliation_rules.json','canonical/reconciliation_rules.json'),('reconciliation_decision_log.json','canonical/reconciliation_decision_log.json')]
  for package_file,canonical_file in mapping:v.ck(load(root,'02_MACHINE_READABLE/'+package_file,v)==load(canonical_root,canonical_file,v),'CANONICAL_PROJECTION',package_file)
  residual=load(root,'02_MACHINE_READABLE/residual_issues.json',v)
  try:expected_residual=projected_residual(load(canonical_root,'canonical/residual_issues.json',v))
  except Exception as error:v.ck(False,'LIFECYCLE_PROJECTION',error);expected_residual=None
  v.ck(residual==expected_residual,'CANONICAL_PROJECTION','residual_issues.json')
  v.ck(residual.get('next_gate')==ACTIVE_NEXT_GATE and residual.get('current_lifecycle_state')==ACTIVE_LIFECYCLE_STATE,'ACTIVE_LIFECYCLE_VERSION',{'next_gate':residual.get('next_gate'),'current_lifecycle_state':residual.get('current_lifecycle_state')})
 req=load(root,'02_MACHINE_READABLE/requirements.json',v);dec=load(root,'02_MACHINE_READABLE/decisions.json',v);amendments=load(root,'02_MACHINE_READABLE/amendment_register.json',v);findings=load(root,'02_MACHINE_READABLE/finding_register.json',v);non_regression=load(root,'02_MACHINE_READABLE/non_regression_rules.json',v)
 v.ck(len(req.get('active_requirements',[]))==336,'REQ_COUNT',len(req.get('active_requirements',[])));v.ck(len(dec.get('decisions',[]))==120,'DEC_COUNT',len(dec.get('decisions',[])));v.ck(len(amendments.get('amendments',[]))==20,'AMEND_COUNT',len(amendments.get('amendments',[])));v.ck(len(findings.get('findings',[]))==22,'FIND_COUNT',len(findings.get('findings',[])))
 decision_map={item['id']:item for item in dec.get('decisions',[])};v.ck('JSON and workbook projections' in decision_map.get('D-100',{}).get('decision','') and 'YAML' not in decision_map.get('D-100',{}).get('decision',''),'D100_JSON',decision_map.get('D-100'))
 model=load_model(root,v)
 if model:
  bundle={'version':PACKAGE_VERSION,'requirements':req,'decisions':dec,'journeys':load(root,'02_MACHINE_READABLE/journeys.json',v),'lineage':load(root,'02_MACHINE_READABLE/original_requirement_lineage.json',v),'residual':load(root,'02_MACHINE_READABLE/residual_issues.json',v),'implementation':load(root,'02_MACHINE_READABLE/implementation_manifest.json',v),'amendments':amendments,'findings':findings,'non_regression':non_regression,'original_decisions':load(root,'02_MACHINE_READABLE/original_decision_dispositions.json',v),'occurrence_registry':load(root,'02_MACHINE_READABLE/forbidden_occurrence_registry.json',v)}
  workbook_parity(root/f'04_WORKBOOKS/Requirements_Traceability_Matrix_v{PACKAGE_VERSION}.xlsx',model.requirement_workbook_sheets(bundle),v,'requirements')
  workbook_parity(root/f'04_WORKBOOKS/Decision_Lineage_and_Evidence_Register_v{PACKAGE_VERSION}.xlsx',model.decision_workbook_sheets(bundle),v,'decisions')
  workbook_parity(root/f'04_WORKBOOKS/Canonical_Occurrence_Registry_v{PACKAGE_VERSION}.xlsx',model.occurrence_workbook_sheets(bundle),v,'occurrences')
 amendment_md=(root/'03_HUMAN_READABLE/13_AMENDMENTS_AND_FINDINGS.md').read_text(encoding='utf-8');decision_md=(root/'03_HUMAN_READABLE/06_DECISION_CATALOG.md').read_text(encoding='utf-8');master=(root/f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.md').read_text(encoding='utf-8');rule_md=(root/'03_HUMAN_READABLE/15_NON_REGRESSION_RULES.md').read_text(encoding='utf-8')
 for item in amendments.get('amendments',[]):v.ck(item['amendment_id'] in amendment_md and item['title'] in amendment_md,'MD_AMEND',item['amendment_id'])
 for item in findings.get('findings',[]):v.ck(item['finding_id'] in amendment_md and item['title'] in amendment_md,'MD_FIND',item['finding_id'])
 v.ck(decision_map['D-100']['decision'] in decision_md and decision_map['D-100']['decision'] in master,'D100_PUBLICATION','D100')
 for item in non_regression.get('rules',[]):v.ck(item['id'] in rule_md and item['id'] in master,'NR_PUBLICATION',item['id'])
 docx=root/f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.docx';pdf=root/f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.pdf'
 v.ck(docx.is_file() and docx.stat().st_size>50000,'DOCX','file');v.ck(pdf.is_file() and pdf.stat().st_size>400000,'PDF','file')
 policy=(root/'00_PACKAGE_CONTROL/OUTER_ARTIFACT_PIN_POLICY.md').read_text(encoding='utf-8');v.ck('.zip.sha256' in policy and 'separate artifacts' in policy,'SIDECAR_POLICY','policy')
 files=inventory.get('files',[]);physical_files={item.relative_to(root).as_posix() for item in root.rglob('*') if item.is_file() and item.relative_to(root).as_posix() not in {'00_PACKAGE_CONTROL/PACKAGE_INVENTORY.json','SHA256SUMS.txt'}}
 v.ck(inventory.get('file_count')==len(files) and {item['path'] for item in files}==physical_files,'INVENTORY_SET',f'{len(files)}/{len(physical_files)}')
 for item in files:
  path=root/item['path'];v.ck(path.is_file() and path.stat().st_size==item['size_bytes'] and sha(path)==item['sha256'],'INVENTORY_HASH',item['path'])
 checksums(root,v)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('target',nargs='?',default='.');parser.add_argument('--json-report');args=parser.parse_args();validator=V()
 try:
  temp_root=validated_temp_root();target=Path(args.target).resolve(strict=True)
  if target.is_dir():validate(target,validator,temp_root)
  else:
   for root in iter_extracted(target,temp_root):validate(root,validator,temp_root)
 except Exception as error:validator.ck(False,'RUNTIME',repr(error))
 report={'validator_version':f'{PACKAGE_VERSION}-package-m0','passed':not validator.f,'failure_count':len(validator.f),'failures':validator.f}
 if args.json_report:Path(args.json_report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 if validator.f:
  for failure in validator.f:print(f"FAIL {failure['code']}: {failure['detail']}",file=sys.stderr)
  return 1
 print('PASS PACKAGE_M0_VALID');print(json.dumps(report,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
