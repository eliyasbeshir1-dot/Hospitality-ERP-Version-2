#!/usr/bin/env python3
"""Hospitality OS v2.0.9 parameterized generator successor.

Provenance: derived from generate_m0_text.py at SHA-256
bd224db6a031d4d1d994e8294adba55e466a7854f285734b1542a3b577b4f215.
The pinned v2.0.8 generator is never modified.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, stat, subprocess, sys, tempfile, textwrap, zipfile
from pathlib import Path
from collections import Counter, defaultdict

GENERATOR_ID='hospitality-os-v209-final-candidate-remediation-successor'
PACKAGE_VERSION_REQUIRED='2.0.9'
ACTIVE_NEXT_GATE='Independent Codex review of pinned Package M0 v2.0.9. M0R remains blocked until approval.'
ACTIVE_LIFECYCLE_STATE='v2.0.9 focused repair candidate prepared for independent Package M0 review.'
CANONICAL_NEXT_GATE_V208='Independent Codex review of pinned Package M0 v2.0.8. M0R remains blocked until approval.'
CANONICAL_LIFECYCLE_STATE_V208='v2.0.8 focused repair candidate prepared for independent Package M0 review.'
WORKBOOK_MODEL_SHA256='dd260efcb785f37eb49c7074aba8414b7e2c9b44fa308fdbdf14bc1f354771d7'
PACKAGE_VALIDATOR_TEMPLATE_SHA256='afd6104eee0a37b63915ea90bccce8befb35b55e3830fa7b8eddf4bf80672f88'

def _early_sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()

_PROJECTOR_PATH=Path(__file__).resolve().with_name('projection_artifacts.py')
_projector_stat=_PROJECTOR_PATH.lstat()
if stat.S_ISLNK(_projector_stat.st_mode) or bool(getattr(_projector_stat,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
 raise RuntimeError('projection_artifacts.py must not be a symlink or reparse point')
_projector_spec=importlib.util.spec_from_file_location('v209_projection_artifacts',_PROJECTOR_PATH)
if _projector_spec is None or _projector_spec.loader is None:raise RuntimeError('cannot load projection_artifacts.py')
_projector=importlib.util.module_from_spec(_projector_spec);_projector_spec.loader.exec_module(_projector)
write_docx,write_pdf,write_xlsx=_projector.write_docx,_projector.write_pdf,_projector.write_xlsx
_MODEL_PATH=Path(__file__).resolve().with_name('workbook_projection_model.py')
_model_stat=_MODEL_PATH.lstat()
if stat.S_ISLNK(_model_stat.st_mode) or bool(getattr(_model_stat,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
 raise RuntimeError('workbook_projection_model.py must not be a symlink or reparse point')
if _early_sha(_MODEL_PATH)!=WORKBOOK_MODEL_SHA256:
 raise RuntimeError('workbook_projection_model.py does not match the authoritative Round-2 pin')
_model_spec=importlib.util.spec_from_file_location('v209_workbook_projection_model',_MODEL_PATH)
if _model_spec is None or _model_spec.loader is None:raise RuntimeError('cannot load workbook_projection_model.py')
_workbook_model=importlib.util.module_from_spec(_model_spec);_model_spec.loader.exec_module(_workbook_model)
requirement_workbook_sheets=_workbook_model.requirement_workbook_sheets
decision_workbook_sheets=_workbook_model.decision_workbook_sheets
occurrence_workbook_sheets=_workbook_model.occurrence_workbook_sheets

SOURCE_ZIP_SHA='804dc9e81aaa29826f77961681287d5bd1eaa2ac6ef5ddc3ae598db4e5e0fd32'
SOURCE_ROOT_SHA='cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96'
VALIDATOR_ZIP_SHA='628ae551120497280a82fdfcf8fd8bd2a69e4c893b400cd94d1914529788cce9'
VALIDATOR_SCRIPT_SHA='ee65b8ec3292db19798f785e23a2d54969eadd91f00e98888520d16051c9f7b0'
PRODUCTION_INPUT_PINS={
 'canonical-source-zip':SOURCE_ZIP_SHA,
 'validator-freeze-zip':VALIDATOR_ZIP_SHA,
 'baseline-zip':'e65fa9af0603c13a76c08961dbac44ee5da34192b3e0433c42590c7599830ba7',
 'occurrence-registry':'d4dae27e4a97bfd710b50412f488a994232c6573441f3a3778d346fdbbf9dcb2',
 'governed-fields':'7e524c6190dad135b197eecfff59954fd19c3bf8bcad2b47fa8bfb227f6528a2',
 'occurrence-schema':'b501312988ce9db85151f7826c863f1de2edea379966d1bbe923b27161ac7d59',
 'occurrence-validator':VALIDATOR_SCRIPT_SHA,
 'detection-module':'7bb11538491b844cbe8149efd1c9adf20e99756605d41712335b5f842b11456d',
 'mechanism-suite':'31c5c47d9c2fea22a1f31835288ff43c37b1acb7904da4611796f7fac819c144',
}
INPUT_PINS=dict(PRODUCTION_INPUT_PINS)
EXPECTED_NAMES={
 'canonical-source-zip':'Hospitality_OS_Reconciled_Canonical_Register_v0.1.4.zip',
 'validator-freeze-zip':'Hospitality_OS_Validator_Freeze_v1.0.5.zip',
 'baseline-zip':'Hospitality_OS_Canonical_Baseline_Freeze_v0.1.zip',
 'occurrence-registry':'canonical_occurrence_registry.json',
 'governed-fields':'governed_fields.json',
 'occurrence-schema':'forbidden_occurrence_registry.schema.json',
 'occurrence-validator':'forbidden_occurrence_validator.py',
 'detection-module':'occurrence_mechanism.py',
 'mechanism-suite':'test_occurrence_mechanism.py',
}
EXIT_PATH=3;EXIT_HASH=4;EXIT_ARCHIVE=5;EXIT_OUTPUT=6

def fail(message,code):
    print(f'GENERATOR_ERROR[{code}]: {message}',file=sys.stderr)
    raise SystemExit(code)
def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()
def lexical_path(raw):
    return Path(os.path.abspath(os.fspath(Path(raw).expanduser())))
def is_reparse(path):
    try:
        if path.is_symlink() or (hasattr(os.path,'isjunction') and os.path.isjunction(path)):return True
        attributes=getattr(path.lstat(),'st_file_attributes',0)
        return bool(attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))
    except OSError:return False
def assert_no_reparse(path,label,include_tree=False):
    lexical=lexical_path(path)
    chain=[lexical,*lexical.parents]
    for item in chain:
        if item.exists() and is_reparse(item):fail(f'{label} traverses reparse point: {item}',EXIT_PATH)
    if include_tree and lexical.exists():
        for item in lexical.rglob('*'):
            if is_reparse(item):fail(f'{label} contains reparse point: {item}',EXIT_PATH)
def has_traversal(raw):
    return '..' in Path(raw).parts
def resolved_file(raw,label):
    if not raw or not raw.strip() or has_traversal(raw):fail(f'{label} is empty or contains traversal',EXIT_PATH)
    lexical=lexical_path(raw);assert_no_reparse(lexical,label)
    try:path=lexical.resolve(strict=True)
    except OSError as error:fail(f'{label} is unresolved: {error}',EXIT_PATH)
    if not path.is_file():fail(f'{label} is not a file: {path}',EXIT_PATH)
    if path.name!=EXPECTED_NAMES[label]:fail(f'{label} must retain pinned filename {EXPECTED_NAMES[label]}',EXIT_PATH)
    return path
def broad_anchors():
    values={Path.cwd().resolve(),Path.home().resolve()}
    values.update(Path(p.anchor).resolve() for p in list(values))
    return values
def validated_environment_temp_roots():
    roots={}
    for name in ('TEMP','TMP'):
        raw=os.environ.get(name)
        if raw is None or not raw.strip():fail(f'{name} must be set to a nonempty absolute directory',EXIT_PATH)
        if has_traversal(raw) or not Path(raw).expanduser().is_absolute():fail(f'{name} must not be relative or contain traversal',EXIT_PATH)
        lexical=lexical_path(raw);assert_no_reparse(lexical,name,include_tree=False)
        try:resolved=lexical.resolve(strict=True)
        except OSError as error:fail(f'{name} is unresolved: {error}',EXIT_PATH)
        if not resolved.is_dir() or resolved in broad_anchors() or len(resolved.parts)<3:fail(f'{name} is not a safe temporary root: {resolved}',EXIT_PATH)
        roots[name]=resolved
    if os.path.normcase(str(roots['TEMP']))!=os.path.normcase(str(roots['TMP'])):
        fail(f'TEMP and TMP resolve to conflicting roots: {roots["TEMP"]} != {roots["TMP"]}',EXIT_PATH)
    return roots
def relative_to(path,parent):
    try:path.relative_to(parent);return True
    except ValueError:return False
def overlaps(left,right):
    return left==right or relative_to(left,right) or relative_to(right,left)
def protected_input_directories(input_files):
    return sorted({path.parent.resolve(strict=True) for path in input_files},key=str)
def output_path(raw,label,input_files,work_dir,temp_roots):
    if not raw or not raw.strip() or has_traversal(raw):fail(f'{label} is empty or contains traversal',EXIT_OUTPUT)
    unresolved=lexical_path(raw)
    try:parent=unresolved.parent.resolve(strict=True)
    except OSError as error:fail(f'{label} parent is unresolved: {error}',EXIT_OUTPUT)
    path=(parent/unresolved.name).resolve(strict=False)
    if not unresolved.name or path in broad_anchors() or len(path.parts)<3 or relative_to(Path.cwd().resolve(),path):fail(f'{label} is unsafe or overly broad: {path}',EXIT_OUTPUT)
    assert_no_reparse(unresolved,label,include_tree=unresolved.exists())
    for directory in protected_input_directories(input_files):
        if overlaps(path,directory):fail(f'{label} overlaps input directory {directory}',EXIT_OUTPUT)
    if work_dir is not None and overlaps(path,work_dir):
        fail(f'{label} overlaps work directory {work_dir}',EXIT_OUTPUT)
    for temp_root in temp_roots:
        if path==temp_root or relative_to(temp_root,path):
            fail(f'{label} is a temporary root or its ancestor: {path}',EXIT_OUTPUT)
    return path
def inspect_zip(path,label):
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:fail(f'{label} is corrupt',EXIT_ARCHIVE)
            for name in archive.namelist():
                parts=Path(name).parts
                if name.startswith(('/',chr(92))) or '..' in parts:
                    fail(f'{label} contains unsafe member {name}',EXIT_ARCHIVE)
                mode=(archive.getinfo(name).external_attr>>16)&0o170000
                if mode==0o120000:fail(f'{label} contains symlink member {name}',EXIT_ARCHIVE)
                if '__pycache__' in parts or Path(name).suffix.lower() in {'.pyc','.pyo'}:
                    fail(f'{label} contains compiled cache {name}',EXIT_ARCHIVE)
            return sorted(archive.namelist())
    except (OSError,zipfile.BadZipFile) as error:fail(f'{label} is unreadable: {error}',EXIT_ARCHIVE)
def safe_extract(path,target,expected_root):
    with zipfile.ZipFile(path) as archive:archive.extractall(target)
    roots=sorted(p for p in target.iterdir() if p.is_dir())
    loose=[p for p in target.iterdir() if not p.is_dir()]
    if len(roots)!=1 or loose or roots[0].name!=expected_root:
        fail(f'{path.name} did not reproduce root {expected_root}',EXIT_ARCHIVE)
    verify_package_sums(roots[0])
    return roots[0]
def verify_package_sums(root):
    sums=root/'SHA256SUMS.txt'
    if not sums.is_file():fail(f'extracted package lacks SHA256SUMS.txt: {root}',EXIT_ARCHIVE)
    for line in sums.read_text(encoding='utf-8').splitlines():
        match=re.match(r'^([a-f0-9]{64})  \./(.+)$',line)
        if not match:fail(f'malformed extracted checksum row: {line}',EXIT_ARCHIVE)
        target=root/match.group(2)
        if not target.is_file() or file_sha(target)!=match.group(1):
            fail(f'extracted checksum mismatch: {match.group(2)}',EXIT_ARCHIVE)
def emit_deterministic_archive(root,archive_out,root_name):
    with zipfile.ZipFile(archive_out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(p for p in root.rglob('*') if p.is_file()):
            info=zipfile.ZipInfo(f'{root_name}/{path.relative_to(root).as_posix()}',(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100644&0xFFFF)<<16
            archive.writestr(info,path.read_bytes())
def assert_safe_destination(path):
    destination=lexical_path(path)
    destination.parent.mkdir(parents=True,exist_ok=True)
    assert_no_reparse(destination.parent,'output destination parent')
    resolved_parent=destination.parent.resolve(strict=True)
    resolved_root=OUT.resolve(strict=True)
    if not relative_to(resolved_parent,resolved_root):fail(f'destination escapes output root: {destination}',EXIT_OUTPUT)
    return destination
def safe_copy2(source,destination):
    target=assert_safe_destination(destination)
    return shutil.copy2(source,target)

parser=argparse.ArgumentParser(description=__doc__)
for flag in ['canonical-source-zip','validator-freeze-zip','baseline-zip','occurrence-registry','governed-fields','occurrence-schema','occurrence-validator','detection-module','mechanism-suite']:
    parser.add_argument(f'--{flag}',required=True)
parser.add_argument('--out',required=True)
parser.add_argument('--package-version',required=True)
parser.add_argument('--work-dir')
parser.add_argument('--force',action='store_true')
parser.add_argument('--dry-run',action='store_true')
parser.add_argument('--archive-out')
parser.add_argument('--archive-sha256-out')
parser.add_argument('--synthetic-test-mode',action='store_true',help='explicitly mark a non-candidate synthetic execute test')
parser.add_argument('--synthetic-pins',help='test-only JSON pins for deliberately modified synthetic fixtures')
args=parser.parse_args()
if args.package_version!=PACKAGE_VERSION_REQUIRED:fail('package version must be exactly 2.0.9',EXIT_PATH)
if bool(args.synthetic_test_mode)!=bool(args.synthetic_pins):fail('synthetic mode and synthetic pins must be supplied together',EXIT_PATH)
SYNTHETIC_TEST_MODE=args.synthetic_test_mode
pins_path=None
if SYNTHETIC_TEST_MODE:
    if has_traversal(args.synthetic_pins):fail('synthetic pins path contains traversal',EXIT_PATH)
    pins_path=lexical_path(args.synthetic_pins);assert_no_reparse(pins_path,'synthetic-pins')
    try:pins_path=pins_path.resolve(strict=True)
    except OSError as error:fail(f'synthetic pins path is unresolved: {error}',EXIT_PATH)
    if not pins_path.is_file() or pins_path.name!='synthetic-input-pins.json':fail('synthetic pins must be a regular file named synthetic-input-pins.json',EXIT_PATH)
    try:
        raw_pins=json.loads(pins_path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError) as error:fail(f'synthetic pins are unreadable: {error}',EXIT_PATH)
    if set(raw_pins)!=set(PRODUCTION_INPUT_PINS) or any(not re.fullmatch(r'[a-f0-9]{64}',str(value)) for value in raw_pins.values()):
        fail('synthetic pins must contain exactly the production pin keys with SHA-256 values',EXIT_HASH)
    if raw_pins==PRODUCTION_INPUT_PINS:fail('synthetic pins must differ from production pins',EXIT_HASH)
    INPUT_PINS=dict(raw_pins)
PACKAGE_VERSION=args.package_version
PACKAGE_NAME=f'Hospitality_OS_Phase_1_Clean_Build_Package_v{PACKAGE_VERSION}'
raw_inputs={key:getattr(args,key.replace('-','_')) for key in INPUT_PINS}
inputs={key:resolved_file(value,key) for key,value in raw_inputs.items()}
input_guard_files=list(inputs.values())+([pins_path] if pins_path is not None else [])
ENV_TEMP_ROOTS=validated_environment_temp_roots()
ENV_TEMP_ROOT=ENV_TEMP_ROOTS['TEMP']
for temp_name,temp_root in ENV_TEMP_ROOTS.items():
    for directory in protected_input_directories(input_guard_files):
        if temp_root==directory or relative_to(temp_root,directory):
            fail(f'{temp_name} is equal to or inside input directory {directory}',EXIT_PATH)
for key,path in inputs.items():
    actual=file_sha(path)
    if actual!=INPUT_PINS[key]:fail(f'{key} hash mismatch: expected {INPUT_PINS[key]}, got {actual}',EXIT_HASH)
for key in ['canonical-source-zip','validator-freeze-zip','baseline-zip']:inspect_zip(inputs[key],key)
SOURCE_ZIP_SHA=INPUT_PINS['canonical-source-zip'];VALIDATOR_ZIP_SHA=INPUT_PINS['validator-freeze-zip'];VALIDATOR_SCRIPT_SHA=INPUT_PINS['occurrence-validator']
work_base=None
if args.work_dir:
    if has_traversal(args.work_dir):fail('work-dir contains traversal',EXIT_PATH)
    lexical_work=lexical_path(args.work_dir);assert_no_reparse(lexical_work,'work-dir',include_tree=True)
    try:work_base=lexical_work.resolve(strict=True)
    except OSError as error:fail(f'work-dir is unresolved: {error}',EXIT_PATH)
    if not work_base.is_dir() or work_base in broad_anchors() or relative_to(Path.cwd().resolve(),work_base):fail(f'unsafe work-dir: {work_base}',EXIT_PATH)
    for directory in protected_input_directories(input_guard_files):
        if overlaps(work_base,directory):fail(f'work-dir overlaps input directory {directory}',EXIT_PATH)
    for temp_root in ENV_TEMP_ROOTS.values():
        if work_base==temp_root or relative_to(temp_root,work_base):fail(f'work-dir is a temporary root or its ancestor: {work_base}',EXIT_PATH)
OUT=output_path(args.out,'out',input_guard_files,work_base,ENV_TEMP_ROOTS.values())
ARCHIVE_OUT=None;ARCHIVE_SHA_OUT=None
if bool(args.archive_out)!=bool(args.archive_sha256_out):
    fail('--archive-out and --archive-sha256-out must be supplied together',EXIT_OUTPUT)
if args.archive_out:
    ARCHIVE_OUT=output_path(args.archive_out,'archive-out',input_guard_files,work_base,ENV_TEMP_ROOTS.values())
    ARCHIVE_SHA_OUT=output_path(args.archive_sha256_out,'archive-sha256-out',input_guard_files,work_base,ENV_TEMP_ROOTS.values())
    if len({OUT,ARCHIVE_OUT,ARCHIVE_SHA_OUT})!=3:fail('output paths must be distinct',EXIT_OUTPUT)
    if overlaps(ARCHIVE_OUT,OUT) or overlaps(ARCHIVE_SHA_OUT,OUT):fail('archive outputs must not overlap the package tree',EXIT_OUTPUT)
    if ARCHIVE_OUT.exists() or ARCHIVE_SHA_OUT.exists():fail('archive outputs must not already exist',EXIT_OUTPUT)
if OUT.exists() and not OUT.is_dir():fail(f'out exists and is not a directory: {OUT}',EXIT_OUTPUT)
existing_entries=sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob('*')) if OUT.exists() else []
owner_marker=OUT/'.v209-generator-owned.json'
owned=False
if existing_entries and owner_marker.is_file():
    try:owner=json.loads(owner_marker.read_text(encoding='utf-8'));owned=owner=={'generator':GENERATOR_ID,'package_version':PACKAGE_VERSION}
    except (OSError,json.JSONDecodeError):owned=False
if existing_entries and (not args.force or not owned):fail('nonempty output replacement requires --force and an exact generator ownership marker',EXIT_OUTPUT)
plan={
 'generator':GENERATOR_ID,'package_version':PACKAGE_VERSION,'mode':'dry-run' if args.dry_run else 'execute',
 'validated_input_pins':dict(sorted(INPUT_PINS.items())),
 'output_directory':str(OUT),'replace_existing':bool(existing_entries and args.force and owned),'synthetic_test_mode':SYNTHETIC_TEST_MODE,
 'extractions':[
  {'input':'canonical-source-zip','expected_root':'Hospitality_OS_Reconciled_Canonical_Register_v0.1.4','expected_files':20},
  {'input':'validator-freeze-zip','expected_root':'Hospitality_OS_Validator_Freeze_v1.0.5','expected_files':20}],
 'copy_additions':[
  '02_MACHINE_READABLE/forbidden_occurrence_registry.json','02_MACHINE_READABLE/governed_fields.json',
  '07_SCHEMAS/forbidden_occurrence_registry.schema.json','06_TOOLS/frozen_validator/forbidden_occurrence_validator.py',
  '06_TOOLS/frozen_validator/occurrence_mechanism.py','06_TOOLS/test_occurrence_mechanism.py'],
 'copy_removals':['06_TOOLS/frozen_validator/forbidden_scan.py'],
 'executable_changes':[
  'remove forbidden_scan import and scan_requirements code path from copied legacy validator',
  'repoint validate_package_m0.py existence/hash/invocation to forbidden_occurrence_validator.py',
  'set PACKAGE_VERSION from required CLI value and pin VALIDATOR_SCRIPT_SHA to occurrence validator'],
 'historical_references_preserved':[
  '02_MACHINE_READABLE/amendment_register.json','02_MACHINE_READABLE/finding_register.json'],
 'deterministic_outputs':[
  'CANONICAL_CONTENT_ROOT.json','00_PACKAGE_CONTROL/PACKAGE_MANIFEST.json',
  '00_PACKAGE_CONTROL/GENERATION_MANIFEST.json','00_PACKAGE_CONTROL/PACKAGE_INVENTORY.json','SHA256SUMS.txt',
  f'04_WORKBOOKS/Requirements_Traceability_Matrix_v{PACKAGE_VERSION}.xlsx',
  f'04_WORKBOOKS/Decision_Lineage_and_Evidence_Register_v{PACKAGE_VERSION}.xlsx',
  f'04_WORKBOOKS/Canonical_Occurrence_Registry_v{PACKAGE_VERSION}.xlsx',
  f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.docx',
  f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.pdf',
  '00_PACKAGE_CONTROL/OUTER_ARTIFACT_PIN_POLICY.md'],
 'mandatory_final_validation':'06_TOOLS/validate_package_m0.py',
 'archive_output':str(ARCHIVE_OUT) if ARCHIVE_OUT else None,
 'archive_sha256_output':str(ARCHIVE_SHA_OUT) if ARCHIVE_SHA_OUT else None,
}
PACKAGE_VALIDATOR_TEMPLATE=Path(__file__).with_name('validate_package_m0_v209.py').resolve(strict=True)
PROJECTION_MODULE=Path(__file__).with_name('projection_artifacts.py').resolve(strict=True)
WORKBOOK_MODEL=_MODEL_PATH.resolve(strict=True)
assert_no_reparse(PACKAGE_VALIDATOR_TEMPLATE,'package validator template');assert_no_reparse(PROJECTION_MODULE,'projection module');assert_no_reparse(WORKBOOK_MODEL,'workbook projection model')
if file_sha(PACKAGE_VALIDATOR_TEMPLATE)!=PACKAGE_VALIDATOR_TEMPLATE_SHA256:fail('package validator template hash does not match the authoritative Round-2 pin',EXIT_HASH)
if file_sha(WORKBOOK_MODEL)!=WORKBOOK_MODEL_SHA256:fail('workbook projection model hash does not match the authoritative Round-2 pin',EXIT_HASH)
if args.dry_run:
    print(json.dumps(plan,ensure_ascii=False,indent=2,sort_keys=True));raise SystemExit(0)

extract_context=tempfile.TemporaryDirectory(prefix='v209-generator-',dir=str(work_base) if work_base else str(ENV_TEMP_ROOT))
extract_root=Path(extract_context.name)
SOURCE_ZIP=inputs['canonical-source-zip'];VALIDATOR_ZIP=inputs['validator-freeze-zip'];BASELINE_ZIP=inputs['baseline-zip']
OCCURRENCE_REGISTRY=inputs['occurrence-registry'];GOVERNED_FIELDS=inputs['governed-fields'];OCCURRENCE_SCHEMA=inputs['occurrence-schema']
OCCURRENCE_VALIDATOR=inputs['occurrence-validator'];DETECTION_MODULE=inputs['detection-module'];MECHANISM_SUITE=inputs['mechanism-suite']
SOURCE_DIR=safe_extract(SOURCE_ZIP,extract_root/'canonical','Hospitality_OS_Reconciled_Canonical_Register_v0.1.4')
VALIDATOR_DIR=safe_extract(VALIDATOR_ZIP,extract_root/'validator','Hospitality_OS_Validator_Freeze_v1.0.5')
CANONICAL_SOURCE_VERSION='0.1.4'
if OUT.exists() and existing_entries:
    assert_no_reparse(OUT,'owned output before replacement',include_tree=True)
    owner=json.loads((OUT/'.v209-generator-owned.json').read_text(encoding='utf-8'))
    if owner!={'generator':GENERATOR_ID,'package_version':PACKAGE_VERSION}:fail('output ownership changed before replacement',EXIT_OUTPUT)
    shutil.rmtree(OUT)
elif OUT.exists():
    assert_no_reparse(OUT,'empty output before use',include_tree=True)
for directory in [
 '00_PACKAGE_CONTROL','01_CANONICAL_SOURCE','02_MACHINE_READABLE','03_HUMAN_READABLE',
 '04_WORKBOOKS','05_REVIEW_AND_BUILD','06_TOOLS/frozen_validator','06_TOOLS/generator','07_SCHEMAS','08_HISTORY']:
    (OUT/directory).mkdir(parents=True,exist_ok=True)
assert_no_reparse(OUT,'new output',include_tree=True)
(OUT/'.v209-generator-owned.json').write_text(json.dumps({'generator':GENERATOR_ID,'package_version':PACKAGE_VERSION},sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
if SYNTHETIC_TEST_MODE:
    (OUT/'.synthetic-test-fixture').write_text('NOT A RELEASE CANDIDATE\n',encoding='utf-8')

def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,obj):
    p=assert_safe_destination(Path(p))
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')
def write(p,s):
    p=assert_safe_destination(Path(p))
    p.write_text(s.rstrip()+"\n",encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def canon(obj): return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def semhash(obj): return hashlib.sha256(canon(obj)).hexdigest()

def baseline_json(name):
    with zipfile.ZipFile(BASELINE_ZIP) as z:
        full=f'Hospitality_OS_Canonical_Baseline_Freeze_v0.1/canonical/{name}'
        return json.loads(z.read(full))

# Load reconciled authority.
req_pkg=load(SOURCE_DIR/'canonical/reconciled_requirements.json')
dec_pkg=load(SOURCE_DIR/'canonical/reconciled_decisions.json')
jour_pkg=load(SOURCE_DIR/'canonical/reconciled_journeys.json')
lineage=load(SOURCE_DIR/'canonical/original_requirement_lineage.json')
amend=load(SOURCE_DIR/'canonical/amendment_register.json')
findings=load(SOURCE_DIR/'canonical/finding_register.json')
rec_rules=load(SOURCE_DIR/'canonical/reconciliation_rules.json')
rec_log=load(SOURCE_DIR/'canonical/reconciliation_decision_log.json')
residual=load(SOURCE_DIR/'canonical/residual_issues.json')
if residual.get('next_gate')!=CANONICAL_NEXT_GATE_V208 or residual.get('current_lifecycle_state')!=CANONICAL_LIFECYCLE_STATE_V208:
    fail('canonical residual lifecycle source does not match the reviewed v2.0.8 projection precondition',EXIT_HASH)
residual['next_gate']=ACTIVE_NEXT_GATE
residual['current_lifecycle_state']=ACTIVE_LIFECYCLE_STATE
requirements=req_pkg['active_requirements']
decisions=dec_pkg['decisions']
journeys=jour_pkg['mandatory_journey_slices']
req_by={r['id']:r for r in requirements}
jour_by={j['id']:j for j in journeys}
GATES=['M0','M0R','M1','M2','M3','M4','M5a','M5b','M6']
GI={g:i for i,g in enumerate(GATES)}

# Baseline canonical sets retained and versioned.
state_machines=baseline_json('state_machines.json'); state_machines['version']=PACKAGE_VERSION
phase_boundaries=baseline_json('phase_boundaries.json'); phase_boundaries['version']=PACKAGE_VERSION
phase_boundaries['phase_1']['printing_boundary']={
    'M4':'minimum real production printer path for physical customer receipt',
    'M5a':'durable local queue, retry, restart recovery, deduplication, health, outage continuity and reconciliation'
}
phase_boundaries['phase_1']['authority_boundary']={
    'M5a':'focused outlet-node services exist but no local authority claim',
    'M5b':'bidirectional lease, same-QR DNS/TLS, sequence and fencing establish local authority continuity'
}
negative_controls=baseline_json('negative_controls.json'); negative_controls['version']=PACKAGE_VERSION
non_regression=baseline_json('non_regression_rules.json'); non_regression['version']=PACKAGE_VERSION
forbidden_rules=load(VALIDATOR_DIR/'validator/forbidden_surface_rules.json'); forbidden_rules['version']=PACKAGE_VERSION
review_questions=baseline_json('review_questions.json'); review_questions['version']=PACKAGE_VERSION
events=baseline_json('events.json'); events['version']=PACKAGE_VERSION
# Correct obvious event gate ownership to reconciled milestone boundaries.
for e in events['events']:
    n=e['id']
    if n in {'EVT-TABLE-SESSION-TRANSFERRED'}: e['milestone']='M3'
    if n in {'EVT-TABLE-SESSION-CLOSED'}: e['milestone']='M4'

# Dynamic dependency graph and M5 ownership.
dep_graph={
    'version':PACKAGE_VERSION,
    'review_method':'Two independent anti-anchored clause-level reviews reconciled under RR-01 through RR-06.',
    'requirement_count':len(requirements),
    'requirements':[
        {
            'id':r['id'],'introduced_at':r['introduced_at'],'revalidated_at':r['revalidated_at'],
            'prerequisite_requirement_ids':r['prerequisite_requirement_ids'],
            'journey_links':r['journey_links'],'acceptance_test_ids':r['acceptance_test_ids'],
            'gate_local_behavior':r['gate_local_behavior'],'later_behavior':r['later_behavior']
        } for r in requirements
    ]
}
base_m5=baseline_json('m5_ownership.json')
m5_ownership={
    'version':PACKAGE_VERSION,'normative':True,
    'M4_printing_boundary':'Minimum real production receipt printing begins at M4.',
    'M5a':dict(base_m5['M5a']), 'M5b':dict(base_m5['M5b'])
}
m5_ownership['M5a']['name']='Outlet execution, synchronization and resilient printing'
m5_ownership['M5a']['services']=['outlet_api','outlet_postgresql','sync_worker','realtime_gateway','print_agent']
m5_ownership['M5a']['service_count']=5
m5_ownership['M5a']['excluded_services']=['local_backup_agent']
m5_ownership['M5a']['backup_boundary']='Backup scheduling and destructive restore remain M6 obligations.'
m5_ownership['M5a']['requirements']=[r['id'] for r in requirements if r['introduced_at']=='M5a']
m5_ownership['M5b']['requirements']=[r['id'] for r in requirements if r['introduced_at']=='M5b']
m5_ownership['M5a']['allowed_claims']=['focused outlet services','durable local persistence','synchronization','print resilience','restart recovery']
m5_ownership['M5b']['allowed_claims']=['same-QR DNS/TLS','bidirectional authority lease','verified local authority continuity','emergency fenced replacement']

# Updated implementation manifest.
gate_counts=Counter(r['introduced_at'] for r in requirements)
owner_counts=Counter(r['owner'] for r in requirements)
domain_counts=Counter(r['domain'] for r in requirements)
implementation_manifest={
    'package':{'name':PACKAGE_NAME,'version':PACKAGE_VERSION,'status':'Package M0 candidate - independent Codex review required','canonical_content_root_sha256':SOURCE_ROOT_SHA},
    'governance':{
        'current_gate':'Package M0','next_gate':'M0R only after Codex approval or recorded adjudication',
        'm0r_authorized':False,'implementation_authorized':False,
        'blocker_rule':'All P0 and substantive P1 findings block progression. Only bounded publication/projection P1 debt may proceed through recorded founder adjudication.'
    },
    'repository':{
        'M0':'documents and generated artifacts only',
        'M0R':'empty repository containing approved documents, conformance plans and scanner/CI design only',
        'M1':'PostgreSQL database and executable migration 0001 begin only after M0R approval or adjudication',
        'frozen_prototype':'v1.1 is research/architecture evidence only and is not a release branch'
    },
    'product':{
        'phase_1':'Customer service and outlet execution for dine-in hospitality operations',
        'launch_languages':['English','Amharic','Arabic'],
        'live_payment_paths':['cash','external terminal result recording','verified Telebirr proof confirmation','verified CBE Birr proof confirmation'],
        'simulator_only_until_contracted':['direct online provider APIs'],
        'tip_rule':'Tips are separate, optional and never preselected.',
        'continuity_rule':'The same QR may resolve to cloud or the outlet node under supported resolver conditions, with no browser-security bypass.'
    },
    'architecture_constraints':[
        'multi-tenant and outlet-isolated by default','modular monolith with strict domain boundaries',
        'versioned APIs and reliable events','exact money arithmetic','append-only or reversal-based commerce records',
        'node-generated private keys and CSR-only certificate issuance','cloud is never a writable dine-in fallback',
        'Phase 2/3 surfaces are physically absent from Phase 1 artifacts'
    ],
    'milestones':[],
    'active_requirement_ids':[r['id'] for r in requirements],
    'counts':{
        'active_requirements':len(requirements),'decisions':len(decisions),'journey_slices':len(journeys),
        'state_machines':len(state_machines['state_machines']),'events':len(events['events']),
        'negative_controls':len(negative_controls['controls']),'non_regression_rules':len(non_regression['rules']),
        'review_questions':len(review_questions['questions']),'original_requirement_dispositions':500,'original_decision_dispositions':100,
        'amendments':len(amend['amendments']),'findings':len(findings['findings'])
    },
    'gate_counts':dict(gate_counts),
    'authority_defaults':{
        'cloud_authority_before_M5b':True,'local_authority_at_M5b_only':True,
        'lease_proofs_seconds':{'proof':5,'degraded':10,'expiry':20},
        'emergency_replacement':'fence evidence + LAN unreachability + readiness + monotonic sequence'
    }
}
MILESTONE_TEXT={
'M0':('Package M0','Pin product, architecture, requirements, evidence and review package.','Codex independent review of this exact ZIP.'),
'M0R':('Repository Conformance','Create an empty documentation-only repository and CI/scanner plans.','No database, migration, route, worker or UI exists.'),
'M1':('Foundation','Create tenancy, identity, security, configuration, data architecture and migration 0001.','Real PostgreSQL and production-role isolation tests pass.'),
'M2':('Menu, QR and customer session','Create multilingual menu, QR, tables, guest sessions and safety content.','English/Amharic/Arabic customer surfaces and true Arabic RTL pass.'),
'M3':('Ordering and service','Create customer/waiter orders, service requests, KDS and fulfillment.','The three M3 language journeys pass without billing or local authority.'),
'M4':('POS, billing and settlement','Create checks, separate tips, payments, cash shifts, receipts and minimum real printing.','Live pilot payment paths and physical/digital receipts pass.'),
'M5a':('Outlet execution and resilience','Create local node services, durable persistence, synchronization and resilient printing.','Restart, retry, deduplication, reconnect and print recovery pass.'),
'M5b':('Same-QR trust and authority','Create DNS/TLS, bidirectional lease, authority sequence and fencing.','Same QR works under supported resolver conditions without split-brain or browser bypass.'),
'M6':('Production hardening','Create production images, backup/restore, deployment, observability and final evidence.','Destructive restore, production roles, full scans and second-tenant evidence pass.')}
for g in GATES:
    name,purpose,exitc=MILESTONE_TEXT[g]
    implementation_manifest['milestones'].append({
        'gate':g,'name':name,'purpose':purpose,'depends_on':([] if g=='M0' else [GATES[GI[g]-1]]),
        'requirement_count':gate_counts[g],'journeys':[j['id'] for j in journeys if j['milestone']==g],
        'exit_criterion':exitc
    })

# Registry and historical dispositions.
orig_req_disp=baseline_json('original_requirement_dispositions.json')
orig_dec_disp=baseline_json('original_decision_dispositions.json')
canonical_registry={
    'version':PACKAGE_VERSION,
    'authority_order':[
        f'canonical source ZIP v{CANONICAL_SOURCE_VERSION}','requirements.json','decisions.json','journeys.json','state_machines.json',
        'phase_boundaries.json','implementation_manifest.json','m5_ownership.json','negative_controls.json','non_regression_rules.json'
    ],
    'counts':implementation_manifest['counts'],
    'canonical_source':{'filename':SOURCE_ZIP.name,'version':f'v{CANONICAL_SOURCE_VERSION}','sha256':SOURCE_ZIP_SHA,'content_root_sha256':SOURCE_ROOT_SHA},
    'files':[]
}

machine={
    'requirements.json':req_pkg,'decisions.json':dec_pkg,'journeys.json':jour_pkg,
    'state_machines.json':state_machines,'phase_boundaries.json':phase_boundaries,
    'implementation_manifest.json':implementation_manifest,'m5_ownership.json':m5_ownership,
    'dependency_graph.json':dep_graph,'events.json':events,'negative_controls.json':negative_controls,
    'non_regression_rules.json':non_regression,'forbidden_surface_rules.json':forbidden_rules,
    'review_questions.json':review_questions,'original_requirement_lineage.json':lineage,
    'original_requirement_dispositions.json':orig_req_disp,'original_decision_dispositions.json':orig_dec_disp,
    'amendment_register.json':amend,'finding_register.json':findings,'reconciliation_rules.json':rec_rules,
    'reconciliation_decision_log.json':rec_log,'residual_issues.json':residual,
    'validator_semantic_contract.json':load(VALIDATOR_DIR/'validator/semantic_contract.json')
}
for name,obj in machine.items():
    dump(OUT/'02_MACHINE_READABLE'/name,obj)
    canonical_registry['files'].append({'file':name,'semantic_sha256':semhash(obj)})
dump(OUT/'02_MACHINE_READABLE/canonical_registry.json',canonical_registry)

# Copy pinned source and validator evidence.
safe_copy2(SOURCE_ZIP,OUT/'01_CANONICAL_SOURCE'/SOURCE_ZIP.name)
write(OUT/'01_CANONICAL_SOURCE'/f'{SOURCE_ZIP.name}.sha256',f'{SOURCE_ZIP_SHA}  {SOURCE_ZIP.name}')
safe_copy2(VALIDATOR_ZIP,OUT/'01_CANONICAL_SOURCE'/VALIDATOR_ZIP.name)
write(OUT/'01_CANONICAL_SOURCE'/f'{VALIDATOR_ZIP.name}.sha256',f'{VALIDATOR_ZIP_SHA}  {VALIDATOR_ZIP.name}')
safe_copy2(BASELINE_ZIP,OUT/'01_CANONICAL_SOURCE'/BASELINE_ZIP.name)
write(OUT/'01_CANONICAL_SOURCE'/f'{BASELINE_ZIP.name}.sha256',f'{INPUT_PINS["baseline-zip"]}  {BASELINE_ZIP.name}')
legacy_validator=(VALIDATOR_DIR/'validator/validate_hospitality_os.py').read_text(encoding='utf-8')
legacy_block=""" from forbidden_scan import scan_requirements
 rule_errors,semantic_findings=scan_requirements(rs,rules)
 for code,detail in rule_errors:v.ck(False,code,detail)
 for finding in semantic_findings:v.ck(False,'FORBIDDEN_SURFACE_RULE',f"{finding['requirement_id']}:{finding['domain']}:{finding['term']}:{finding['clause']}")
"""
if legacy_block not in legacy_validator: raise RuntimeError('legacy forbidden-scan block not found')
legacy_validator=legacy_validator.replace(legacy_block,'')
if 'forbidden_scan' in legacy_validator: raise RuntimeError('live forbidden-scan reference remains')
write(OUT/'06_TOOLS/frozen_validator/validate_hospitality_os.py',legacy_validator)
safe_copy2(VALIDATOR_DIR/'validator/semantic_contract.json',OUT/'06_TOOLS/frozen_validator/semantic_contract.json')
dump(OUT/'06_TOOLS/frozen_validator/forbidden_surface_rules.json',forbidden_rules)
# forbidden_scan.py is intentionally not copied in v2.0.9.
safe_copy2(OCCURRENCE_VALIDATOR,OUT/'06_TOOLS/frozen_validator/forbidden_occurrence_validator.py')
safe_copy2(DETECTION_MODULE,OUT/'06_TOOLS/frozen_validator/occurrence_mechanism.py')
occurrence_registry=load(OCCURRENCE_REGISTRY)
occurrence_count=occurrence_registry.get('occurrence_count')
if not isinstance(occurrence_count,int) or occurrence_count<=0 or len(occurrence_registry.get('occurrences',[]))!=occurrence_count:
    raise RuntimeError('canonical occurrence registry candidate count is invalid')
occurrence_registry['expected_occurrence_count']=occurrence_count
occurrence_registry['count']=occurrence_count
occurrence_registry['version']=occurrence_registry.get('normalization_version','1.0')
for occurrence in occurrence_registry['occurrences']:
    occurrence.setdefault('term',occurrence.get('detected_term',''))
    occurrence.setdefault('rationale',occurrence.get('classification_rationale',''))
    occurrence.setdefault('introduced_by_amendment','AMD-V208-001')
dump(OUT/'02_MACHINE_READABLE/forbidden_occurrence_registry.json',occurrence_registry)
safe_copy2(OCCURRENCE_REGISTRY,OUT/'08_HISTORY/INPUTS/canonical_occurrence_registry.json')
safe_copy2(GOVERNED_FIELDS,OUT/'02_MACHINE_READABLE/governed_fields.json')
safe_copy2(OCCURRENCE_SCHEMA,OUT/'07_SCHEMAS/forbidden_occurrence_registry.schema.json')
safe_copy2(MECHANISM_SUITE,OUT/'06_TOOLS/test_occurrence_mechanism.py')
validator_template=PACKAGE_VALIDATOR_TEMPLATE.read_text(encoding='utf-8')
validator_replacements={
 '__PACKAGE_VERSION__':PACKAGE_VERSION,
 '__CANONICAL_SOURCE_SHA256__':SOURCE_ZIP_SHA,
 '__VALIDATOR_FREEZE_SHA256__':VALIDATOR_ZIP_SHA,
 '__OCCURRENCE_VALIDATOR_SHA256__':VALIDATOR_SCRIPT_SHA,
 '__WORKBOOK_MODEL_SHA256__':WORKBOOK_MODEL_SHA256,
 '__EXPECTED_INPUT_PINS_JSON__':json.dumps(dict(sorted(INPUT_PINS.items())),ensure_ascii=False,sort_keys=True,separators=(',',':')),
}
for token,value in validator_replacements.items():
    if token not in validator_template:raise RuntimeError(f'validator template token missing: {token}')
    validator_template=validator_template.replace(token,value)
if any(token in validator_template for token in validator_replacements):raise RuntimeError('unresolved validator template token')
write(OUT/'06_TOOLS/validate_package_m0.py',validator_template)
safe_copy2(WORKBOOK_MODEL,OUT/'06_TOOLS/workbook_projection_model.py')
for f in ['BLIND_MUTATION_ROUND1_RESULTS.json','BLIND_MUTATION_ROUND2_RESULTS.json','ROUND2_POST_REPAIR_DIAGNOSTIC.json','VALIDATOR_FREEZE_REPORT.md','KNOWN_VALIDATOR_LIMITS.md']:
    safe_copy2(VALIDATOR_DIR/'reports'/f,OUT/'05_REVIEW_AND_BUILD'/f)
safe_copy2(VALIDATOR_DIR/'reports/Validator_Coverage_and_Mutation_Report_v1.0.5.xlsx',OUT/'04_WORKBOOKS/Validator_Coverage_and_Mutation_Report_v1.0.5.xlsx')
safe_copy2(SOURCE_DIR/'RECONCILIATION_REPORT.md',OUT/'08_HISTORY/RECONCILIATION_REPORT_v0.1.4.md')
safe_copy2(SOURCE_DIR/'Hospitality_OS_Reconciled_Register_v0.1.4.xlsx',OUT/'04_WORKBOOKS/Reconciled_Canonical_Register_v0.1.4.xlsx')

# ---------- Markdown helpers ----------
def front(title,subtitle=None):
    s=f'# {title}\n\n'
    if subtitle: s+=f'**{subtitle}**\n\n'
    s+=(f'- Package: `{PACKAGE_NAME}`\n- Canonical source root: `{SOURCE_ROOT_SHA}`\n'
       f'- Status: **Package M0 candidate - M0R and implementation are not authorized**\n')
    return s

def fmt_list(items): return ', '.join(items) if items else 'None'
def req_anchor(r): return f"## {r['id']} - {r['title']}"
def esc_table(s): return str(s or '').replace('|','\\|').replace('\n',' ')

def source_of_truth():
    s=front('Hospitality OS Phase 1 Source of Truth', 'Normative human-readable projection')
    s+='''\n## Authority\n\nThe canonical authority is the pinned reconciled source ZIP in `01_CANONICAL_SOURCE`. The JSON files in `02_MACHINE_READABLE` and all Markdown, Excel, Word and PDF files are generated projections. When projections conflict, the pinned canonical JSON controls.\n\n'''
    s+='## Package status\n\n- Package M0: candidate for independent Codex review.\n- M0R: prohibited until Codex approves or a recorded founder adjudication satisfies FR-GOV-004.\n- Database, migration `0001`, routes, workers, screens and application code: prohibited before M1.\n\n'
    s+='## Canonical counts\n\n'
    for k,v in implementation_manifest['counts'].items(): s+=f'- {k.replace("_"," ").title()}: **{v}**\n'
    s+='\n## Non-negotiable product rules\n\n'
    rules=[
        'Phase 1 is dine-in customer service and outlet execution only.',
        'English, Amharic and Arabic are the exact customer launch languages; Arabic is true RTL.',
        'Bill, payment and tip are separate records; no tip is preselected.',
        'Cash, external-terminal result recording and verified Telebirr/CBE Birr proof confirmation are live pilot paths.',
        'Direct provider APIs remain simulator-only until contracted; raw card data is prohibited.',
        'Minimum real receipt printing begins at M4; resilient local print queueing begins at M5a.',
        'Local authority continuity begins at M5b, not M5a; the cloud is never a writable dine-in fallback.',
        'The outlet node generates and retains its private key; only a CSR leaves the node.',
        'Phase 2/3 entities, routes, tables, workers, screens and positive tests are physically absent.'
    ]
    for x in rules:s+=f'- {x}\n'
    s+='\n## Milestone sequence\n\n| Gate | Name | Requirements | Exit criterion |\n|---|---|---:|---|\n'
    for m in implementation_manifest['milestones']:
        s+=f"| {m['gate']} | {esc_table(m['name'])} | {m['requirement_count']} | {esc_table(m['exit_criterion'])} |\n"
    return s

def product_definition():
    s=front('Phase 1 Product Definition')
    s+='''\n## Product purpose\n\nHospitality OS is a configurable multi-tenant operating system for restaurants, cafés, bakeries, bars, food courts, hotel outlets and related hospitality operators. Phase 1 covers the complete dine-in customer-service journey from QR discovery through ordering, kitchen execution, billing, payment, tip and receipt, including controlled outlet continuity.\n\n## Personas\n\n- Guest customer\n- Waiter and supervisor\n- Kitchen, bar and expo staff\n- Cashier and manager\n- Tenant, legal-entity and outlet administrator\n- Platform operations and security staff\n\n## Phase 1 capabilities\n\n'''
    for x in phase_boundaries['phase_1']['active']:s+=f'- {x}\n'
    s+='\n## Explicit exclusions\n\n'
    for x in phase_boundaries['phase_1']['excluded']:s+=f'- {x}\n'
    s+='\n## Customer-language contract\n\nEnglish, Amharic and Arabic are complete customer launch languages. Staff applications launch in English on a translation-ready architecture. Browser language is a suggestion; the customer chooses the session language.\n\n'
    s+='## Payment and tip contract\n\nTips are separate from the bill and from bill allocation. No percentage or amount is selected by default. A payer may add a tip independently, and a tip cannot hide an unpaid bill balance.\n\n'
    s+='## Continuity promise and boundary\n\nThe same QR can resolve to the cloud or the outlet node under supported system-resolver conditions. Unsupported strict custom encrypted resolvers receive translated captive-portal/signage/staff guidance. No self-signed certificate, browser bypass or writable cloud fallback is permitted.\n'
    return s

def implementation_sequence():
    s=front('Implementation Sequence and Gate Closures')
    s+='\nA milestone closes only on behavior executable with approved predecessors. Later capabilities may revalidate an earlier mechanism but cannot be used to close an earlier gate.\n\n'
    for m in implementation_manifest['milestones']:
        s+=f"## {m['gate']} - {m['name']}\n\n**Purpose.** {m['purpose']}\n\n**Depends on.** {fmt_list(m['depends_on'])}\n\n**Requirements introduced.** {m['requirement_count']}\n\n**Mandatory journeys.** {fmt_list(m['journeys'])}\n\n**Exit criterion.** {m['exit_criterion']}\n\n"
    return s

def architecture():
    s=front('Architecture, Security and Continuity Constraints')
    for h,items in [
        ('Core architecture',implementation_manifest['architecture_constraints']),
        ('Tenant and outlet isolation',[x['rule'] for x in non_regression['rules'] if x['id'] in {'NR-009','NR-010','NR-011','NR-012','NR-013','NR-014','NR-015','NR-016'}]),
        ('Money and audit',[x['rule'] for x in non_regression['rules'] if x['id'] in {'NR-017','NR-018','NR-019','NR-020','NR-021','NR-022','NR-023','NR-024'}]),
    ]:
        s+=f'\n## {h}\n\n'
        for x in items:s+=f'- {x}\n'
    s+='''\n## M4/M5a printing boundary\n\nM4 owns the minimum real printer path needed to issue a physical customer receipt. M5a adds durable local queueing, bounded retry, restart recovery, deduplication, printer health, outage continuity and reconciliation.\n\n## M5a/M5b authority boundary\n\nM5a provides focused local services but does not claim local authority. M5b adds same-QR DNS/TLS, bidirectional lease, authority sequence and fencing. The cloud remains a control plane/forwarder and is never a writable dine-in fallback.\n\n## Certificate custody\n\nThe outlet node generates and retains the private key, submits only a certificate signing request, receives only the certificate chain, renews through DNS-01 automation and never exports the private key.\n'''
    return s

def requirements_md():
    s=front('Functional Requirements Register', f'{len(requirements)} active requirements')
    s+='\nRequirements are ordered by introducing gate, domain and ID. Each entry states its executable gate-local behavior and later revalidation ownership.\n\n'
    grouped=defaultdict(list)
    for r in requirements:grouped[r['introduced_at']].append(r)
    for g in GATES:
        s+=f'# Gate {g}\n\n'
        domains=defaultdict(list)
        for r in sorted(grouped[g],key=lambda x:(x['domain'],x['id'])):domains[r['domain']].append(r)
        for domain,rs in sorted(domains.items()):
            s+=f'## {domain}\n\n'
            for r in rs:
                s+=f"### {r['id']} - {r['title']}\n\n"
                s+=f"**Priority:** {r['priority']}  \n**Owner:** {r['owner']}  \n**Lineage:** {r['lineage_status']}"
                if r.get('split_from'):s+=f" from `{r['split_from']}`"
                s+='  \n'
                s+=f"**Introduced:** {r['introduced_at']}  \n**Revalidated:** {fmt_list(r['revalidated_at'])}  \n"
                s+=f"**Required behavior:** {r['required_behavior']}\n\n"
                s+=f"**Gate-local behavior:** {r['gate_local_behavior']}\n\n"
                s+=f"**Later behavior:** {r['later_behavior']}\n\n"
                s+=f"**Prerequisites:** {fmt_list(r['prerequisite_requirement_ids'])}  \n"
                s+=f"**Journeys:** {fmt_list(r['journey_links'])}  \n"
                s+=f"**Acceptance tests:** {fmt_list(r['acceptance_test_ids'])}\n\n"
    return s

def decisions_md():
    s=front('Decision Catalog',f'{len(decisions)} canonical decisions')
    s+='\n| ID | Topic | Target | Source | Decision |\n|---|---|---|---|---|\n'
    for d in decisions:
        s+=f"| {d['id']} | {esc_table(d['topic'])} | {esc_table(d['target'])} | {esc_table(d['source'])} | {esc_table(d['decision'])} |\n"
    return s

def journeys_md():
    s=front('Mandatory Golden Journeys',f'{len(journeys)} slices')
    for j in journeys:
        s+=f"\n## {j['id']} - {j['name']}\n\n**Milestone:** {j['milestone']}  \n**Mandatory:** {j['mandatory']}  \n**Predecessors:** {j['predecessors']}  \n**Personas:** {j['personas']}\n\n**Steps:** {j['steps']}\n\n**Pass:** {j['pass']}\n"
    return s

def states_md():
    s=front('State Machines',f"{len(state_machines['state_machines'])} canonical machines")
    for sm in state_machines['state_machines']:
        s+=f"\n## {sm['id']} - {sm['name']}\n\n**Phase:** {sm.get('phase','Phase 1')}\n\n**States:** {fmt_list(sm.get('states',[]))}\n\n**Transitions**\n\n"
        for x in sm.get('transitions',[]):s+=f'- {x}\n'
        s+='\n**Invariants**\n\n'
        for x in sm.get('invariants',[]):s+=f'- {x}\n'
    return s

def boundaries_md():
    s=front('Phase Boundaries and M5 Ownership')
    s+='\n## Phase 1 active scope\n\n'+''.join(f'- {x}\n' for x in phase_boundaries['phase_1']['active'])
    s+='\n## Excluded scope\n\n'+''.join(f'- {x}\n' for x in phase_boundaries['phase_1']['excluded'])
    s+='\n## Repository boundary\n\n'
    for k,v in phase_boundaries['phase_1']['repository_and_migration_boundary'].items():s+=f'- **{k}:** {v}\n'
    s+='\n## M5a ownership\n\n'
    for k in ['requirements','journeys','services','forbidden_claims']:
        s+=f"**{k.replace('_',' ').title()}:** {fmt_list(m5_ownership['M5a'][k])}\n\n"
    s+=f"**Exact service boundary:** exactly five services; `local_backup_agent` is excluded. {m5_ownership['M5a']['backup_boundary']}\n\n"
    s+='## M5b ownership\n\n'
    for k in ['requirements','journeys','services','forbidden_claims']:
        s+=f"**{k.replace('_',' ').title()}:** {fmt_list(m5_ownership['M5b'][k])}\n\n"
    return s

def testing_md():
    r1=load(VALIDATOR_DIR/'reports/BLIND_MUTATION_ROUND1_RESULTS.json')
    r2=load(VALIDATOR_DIR/'reports/BLIND_MUTATION_ROUND2_RESULTS.json')
    diag=load(VALIDATOR_DIR/'reports/ROUND2_POST_REPAIR_DIAGNOSTIC.json')
    internal=load(VALIDATOR_DIR/'reports/INTERNAL_MUTATION_RESULTS.json')
    s=front('Test, Evidence and Validator Strategy')
    s+=f'''\n## Validator status\n\n- Frozen validator script SHA-256: `{VALIDATOR_SCRIPT_SHA}`\n- Validator package SHA-256: `{VALIDATOR_ZIP_SHA}`\n- Internal planted mutations: **{internal.get('detected_count')}/{internal.get('mutation_count')} detected**\n- Blind Round 1: **{r1.get('detected')}/{r1.get('mutations_run')} detected before repair**\n- Blind Round 2: **{r2.get('detected')}/{r2.get('mutations_run')} detected before repair**\n- Disclosed Round 2 misses after repair: **{diag.get('detected')}/{diag.get('mutations_run')} detected diagnostically**\n\nThe post-repair reruns are diagnostic, not fresh independent evidence. The agreed two-round cap is closed; Codex receives the limitation explicitly.\n\n## Negative controls\n\n'''
    for c in negative_controls['controls']:
        s+=f"- **{c['id']} ({c['milestone']}):** {c['property']} - deliberate break: {c['deliberate_break']} - expected: `{c['expected_failure_signature']}`\n"
    s+='\n## Package M0 questions\n\n'
    for q in review_questions['questions']:s+=f"{q['number']}. {q['question']}\n"
    return s

def build_control_md():
    s=front('Build Control Plan')
    s+='''\n## Control principles\n\n1. Build one milestone at a time.\n2. Do not start a later milestone before the current gate is approved or adjudicated under FR-GOV-004.\n3. Every route, table, worker, screen and test maps to an active requirement and gate.\n4. Phase 2/3 surfaces are physically absent.\n5. Reused prototype code is reviewed as third-party code.\n6. Production-role tests, not owner/superuser tests, prove isolation.\n7. Generated projections are rebuilt from canonical sources; manual edits are prohibited.\n\n## Repository start rule\n\nM0R creates an empty repository containing only the approved Package M0 documents, conformance plans and CI/scanner design. No database, schema, executable migration, application route, worker or UI is permitted.\n\n## Migration start rule\n\nPostgreSQL and migration `0001` begin at M1 after M0R approval or adjudication. No v1.1 migration is imported.\n\n## Requirement ownership by gate\n\n'''
    for g in GATES:
        owners=Counter(r['owner'] for r in requirements if r['introduced_at']==g)
        s+=f"- **{g}:** {gate_counts[g]} requirements - "+'; '.join(f'{o}: {n}' for o,n in owners.most_common())+'\n'
    return s

def historical_md():
    s=front('Historical Disposition and Lineage Summary')
    s+='''\nThe historical registers preserve all 500 original v1.1 requirements and 100 original decisions at row level. The active reconciled register preserves all 294 imported Phase 1 requirement IDs through retained rows or explicit split-successor lineage.\n\n'''
    s+=f"- Original imported Phase 1 requirements: {lineage['original_count']}\n- Mapped originals: {lineage['mapped_count']}\n- Split originals: {len(lineage['split_register'])}\n- New audit requirements: {len(lineage['new_requirements'])}\n- Behavior coverage attested: {lineage['all_behavior_coverage_attested']}\n"
    s+='\n## Split register\n\n| Original | Successors | Reason |\n|---|---|---|\n'
    for row in lineage['split_register']:
        s+=f"| {row.get('original_id')} | {esc_table(', '.join(row.get('successor_ids',row.get('successors',[]))))} | {esc_table(row.get('split_reason',row.get('reason','')))} |\n"
    return s

def amendments_md():
    s=front('Amendments and Findings')
    s+='\n## Amendments\n\n'
    for a in amend['amendments']:
        s+=f"### {a.get('amendment_id')} - {a.get('title') or a.get('type') or a.get('amendment_id')}\n\n**Source:** {a.get('source') or 'reconciliation'}  \n**Affected:** {fmt_list(a.get('affected_ids',[]))}\n\n**Old value:** {a.get('old_value') or 'Not separately recorded.'}\n\n**New value:** {a.get('new_value') or a.get('change') or 'See canonical amendment record.'}\n\n**Change:** {a.get('change') or a.get('new_value') or ''}\n\n**Reason:** {a.get('reason')}\n\n**Verification:** {a.get('verification')}\n\n**Residual risk:** {a.get('residual_risk','None.')}\n\n"
    s+='## Findings\n\n'
    for f in findings['findings']:
        s+=f"### {f.get('finding_id')} - {f.get('title') or f.get('finding') or f.get('finding_id')}\n\n**Severity:** {f.get('severity')}  \n**Disposition:** {f.get('disposition')}  \n**Affected:** {fmt_list(f.get('affected_canonical_ids',[]))}\n\n**Finding:** {f.get('finding') or f.get('title') or ''}\n\n**Verification:** {f.get('verification')}\n\n**Residual risk:** {f.get('residual_risk')}\n\n"
    return s


def non_regression_md():
    s=front('Non-Regression Rules',f"{len(non_regression['rules'])} canonical rules")
    s+='\nEvery rule is identified and published. The machine-readable register remains authoritative.\n\n'
    for rule in non_regression['rules']:
        s+=f"## {rule['id']}\n\n{rule['rule']}\n\n"
    return s

def limits_md():
    limits=(VALIDATOR_DIR/'reports/KNOWN_VALIDATOR_LIMITS.md').read_text(encoding='utf-8')
    return front('Known Validator Limits')+'\n'+limits

human_files={
'01_SOURCE_OF_TRUTH.md':source_of_truth(),
'02_PRODUCT_DEFINITION.md':product_definition(),
'03_IMPLEMENTATION_SEQUENCE.md':implementation_sequence(),
'04_ARCHITECTURE_AND_SECURITY.md':architecture(),
'05_FUNCTIONAL_REQUIREMENTS.md':requirements_md(),
'06_DECISION_CATALOG.md':decisions_md(),
'07_GOLDEN_JOURNEYS.md':journeys_md(),
'08_STATE_MACHINES.md':states_md(),
'09_PHASE_BOUNDARIES_AND_M5_OWNERSHIP.md':boundaries_md(),
'10_TEST_AND_VALIDATION_STRATEGY.md':testing_md(),
'11_BUILD_CONTROL_PLAN.md':build_control_md(),
'12_HISTORICAL_DISPOSITION_SUMMARY.md':historical_md(),
'13_AMENDMENTS_AND_FINDINGS.md':amendments_md(),
'14_KNOWN_VALIDATOR_LIMITS.md':limits_md(),
'15_NON_REGRESSION_RULES.md':non_regression_md(),
}
for name,text in human_files.items():write(OUT/'03_HUMAN_READABLE'/name,text)

# Review/build docs.
codex=f'''# Codex Package M0 Independent Review Brief\n\n## Artifact to review\n\n`{PACKAGE_NAME}.zip`\n\nThe reviewer must receive both the ZIP and its `.zip.sha256` sidecar, independently compute the ZIP hash, compare it with the supplied pin, and run:\n\n```bash\npython 06_TOOLS/validate_package_m0.py .\n```\n\nThe package validator must return `PASS PACKAGE_M0_VALID`. The reviewer must also verify the pinned canonical source ZIP and frozen validator hashes.\n\n## Independence\n\nReview the package independently. Do not rely on prior reviewer dispositions as proof. The historical and reconciliation material may be used only after forming an independent view of the current canonical product, architecture, gates and acceptance evidence.\n\n## Required review questions\n\n'''+''.join(f"{q['number']}. {q['question']}\n" for q in review_questions['questions'])+'''\n## Critical semantic areas\n\n- M0R contains no database, executable migration, route, worker, screen or application code.\n- Minimum physical receipt printing begins at M4; M5a adds resilience.\n- M5a does not claim local authority; M5b owns same-QR DNS/TLS, lease and fencing.\n- Bill, payment and tip remain separate; no tip is preselected.\n- Direct payment-provider APIs remain simulator-only until contracted.\n- Node private keys never leave the outlet node.\n- Phase 2/3 surfaces are physically absent.\n- Every requirement is executable at its introduction gate with no later-gate prerequisite.\n\n## Verdict required\n\nReturn exactly one:\n\n- `APPROVE PACKAGE M0 AND AUTHORIZE M0R`\n- `DO NOT AUTHORIZE M0R`\n\nList every P0/P1/P2 finding with affected IDs, evidence, required amendment and gate consequence. A bounded publication/projection P1 may proceed only under FR-GOV-004; substantive P1 findings remain blockers.\n'''
write(OUT/'05_REVIEW_AND_BUILD/CODEX_PACKAGE_M0_REVIEW_BRIEF.md',codex)

build_brief=f'''# Implementation Brief - Locked Until Package M0 Approval\n\n## Current instruction\n\nDo not create a repository, database, migration, application route, worker, screen or UI.\n\n## After Package M0 approval\n\n1. Create M0R as an empty documentation-only repository.\n2. Add the approved package, conformance plans and CI/scanner design.\n3. Prove the forbidden-surface scanner and traceability controls.\n4. Submit M0R for independent approval.\n5. Only after M0R approval, begin M1 with PostgreSQL and migration `0001`.\n\n## Build order\n\n'''+''.join(f"- **{m['gate']} {m['name']}:** {m['purpose']}\n" for m in implementation_manifest['milestones'])
write(OUT/'05_REVIEW_AND_BUILD/BUILD_IMPLEMENTATION_BRIEF.md',build_brief)

m0r=f'''# M0R Repository Conformance Plan\n\n## Purpose\n\nCreate the first clean repository without implementing the product.\n\n## Allowed\n\n- Approved Package M0 documents and machine-readable registers\n- Traceability and ownership plans\n- CI design and forbidden-surface scanner design\n- Code-reuse provenance register\n- Review evidence templates\n\n## Forbidden\n\n- Database or schema\n- Executable migration, including `0001`\n- Application route, worker, screen, UI or runtime service\n- Hidden or feature-flagged Phase 2/3 surface\n- Reused prototype code\n\n## Exit\n\nA scan proves the repository is documentation-only, every planned unit maps to an active requirement and no deferred-domain surface exists.\n'''
write(OUT/'05_REVIEW_AND_BUILD/M0R_REPOSITORY_CONFORMANCE_PLAN.md',m0r)

# Requirement ownership and milestone matrix.
own=f'''# Build-Control Requirement Ownership\n\n| Requirement | Gate | Owner | Domain | Tests |\n|---|---|---|---|---|\n'''
for r in sorted(requirements,key=lambda x:(GI[x['introduced_at']],x['owner'],x['id'])):
    own+=f"| {r['id']} | {r['introduced_at']} | {esc_table(r['owner'])} | {esc_table(r['domain'])} | {esc_table(', '.join(r['acceptance_test_ids']))} |\n"
write(OUT/'05_REVIEW_AND_BUILD/BUILD_CONTROL_REQUIREMENT_OWNERSHIP.md',own)
mat='# Milestone Acceptance Matrix\n\n| Gate | Requirement count | Mandatory journeys | Exit criterion |\n|---|---:|---|---|\n'
for m in implementation_manifest['milestones']:
    mat+=f"| {m['gate']} | {m['requirement_count']} | {esc_table(', '.join(m['journeys']))} | {esc_table(m['exit_criterion'])} |\n"
write(OUT/'05_REVIEW_AND_BUILD/MILESTONE_ACCEPTANCE_MATRIX.md',mat)

# Full master markdown.
master=front(f'Hospitality OS Phase 1 Master Blueprint v{PACKAGE_VERSION}','Generated review edition')
order=list(human_files)
for name in order:
    txt=human_files[name]
    # omit repeated front matter and promote first heading.
    master+='\n\n---\n\n'+txt
write(OUT/'03_HUMAN_READABLE'/f'HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.md',master)

# Deterministic workbook, DOCX, PDF, and external-pin policy projections.
workbook_bundle={
 'version':PACKAGE_VERSION,'requirements':req_pkg,'decisions':dec_pkg,'journeys':jour_pkg,
 'lineage':lineage,'residual':residual,'implementation':implementation_manifest,
 'amendments':amend,'findings':findings,'non_regression':non_regression,
 'original_decisions':orig_dec_disp,'occurrence_registry':occurrence_registry,
}
requirements_sheets=requirement_workbook_sheets(workbook_bundle)
decision_sheets=decision_workbook_sheets(workbook_bundle)
occurrence_sheets=occurrence_workbook_sheets(workbook_bundle)
expected_sheet_sets={
 'requirements':['Dashboard','Active Requirements','Clause Evidence','Golden Journeys','Milestone Matrix'],
 'decisions':['Dashboard','Decision Register','Original Lineage','Split Register','Amendments','Findings','Non-Regression Rules','Original Decisions'],
 'occurrences':['Dashboard','Occurrences'],
}
if [s[0] for s in requirements_sheets]!=expected_sheet_sets['requirements'] or [s[0] for s in decision_sheets]!=expected_sheet_sets['decisions'] or [s[0] for s in occurrence_sheets]!=expected_sheet_sets['occurrences']:
 raise RuntimeError('binary projection sheet-set precondition failed')
if len(requirements_sheets[1][1])!=337 or len(requirements_sheets[2][1])!=338 or len(decision_sheets[1][1])!=121 or len(occurrence_sheets[1][1])!=occurrence_count+1:
 raise RuntimeError('binary projection row-count precondition failed')
requirements_workbook=assert_safe_destination(OUT/'04_WORKBOOKS'/f'Requirements_Traceability_Matrix_v{PACKAGE_VERSION}.xlsx')
decision_workbook=assert_safe_destination(OUT/'04_WORKBOOKS'/f'Decision_Lineage_and_Evidence_Register_v{PACKAGE_VERSION}.xlsx')
occurrence_workbook=assert_safe_destination(OUT/'04_WORKBOOKS'/f'Canonical_Occurrence_Registry_v{PACKAGE_VERSION}.xlsx')
write_xlsx(requirements_workbook,requirements_sheets)
write_xlsx(decision_workbook,decision_sheets)
write_xlsx(occurrence_workbook,occurrence_sheets)
master_docx=assert_safe_destination(OUT/'03_HUMAN_READABLE'/f'HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.docx')
master_pdf=assert_safe_destination(OUT/'03_HUMAN_READABLE'/f'HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.pdf')
write_docx(master_docx,f'Hospitality OS Phase 1 Master Blueprint v{PACKAGE_VERSION}',master)
write_pdf(master_pdf,f'Hospitality OS Phase 1 Master Blueprint v{PACKAGE_VERSION}',master)
if master_docx.stat().st_size<=50000 or master_pdf.stat().st_size<=400000:
    raise RuntimeError(f'binary projection size/completeness precondition failed: docx={master_docx.stat().st_size}, pdf={master_pdf.stat().st_size}')
pin_policy=f'''# Outer Artifact Pin Policy - v{PACKAGE_VERSION}

The Package M0 review delivery is incomplete unless the generated ZIP and its
publisher-supplied `.zip.sha256` sidecar are attached together as two separate artifacts.
The reviewer must independently compute the ZIP SHA-256 before relying on either artifact.
'''
write(OUT/'00_PACKAGE_CONTROL/OUTER_ARTIFACT_PIN_POLICY.md',pin_policy)

# Schemas (pragmatic package schemas).
req_schema={
 '$schema':'https://json-schema.org/draft/2020-12/schema','title':'Hospitality OS reconciled requirements projection',
 'type':'object','required':['active_requirements','counts','gate_counts'],
 'properties':{'active_requirements':{'type':'array','minItems':336,'maxItems':336},'counts':{'type':'object'},'gate_counts':{'type':'object'}}
}
manifest_schema={
 '$schema':'https://json-schema.org/draft/2020-12/schema','title':'Hospitality OS Package M0 manifest',
 'type':'object','required':['package_name','package_version','canonical_source','validator','package_validator','counts','primary_files']
}
dump(OUT/'07_SCHEMAS/requirements_projection.schema.json',req_schema)
dump(OUT/'07_SCHEMAS/package_manifest.schema.json',manifest_schema)
safe_copy2(SOURCE_DIR/'schemas/original_requirement_lineage.schema.json',OUT/'07_SCHEMAS/original_requirement_lineage.schema.json')
safe_copy2(SOURCE_DIR/'schemas/reconciled_canonical_register.schema.json',OUT/'07_SCHEMAS/reconciled_canonical_register.schema.json')

# Control docs before workbook/docx/pdf generation.
lineage_manifest={
 'package_version':PACKAGE_VERSION,
 'current_canonical_source':{'file':SOURCE_ZIP.name,'sha256':SOURCE_ZIP_SHA,'content_root_sha256':SOURCE_ROOT_SHA,'role':'sole canonical content source'},
 'frozen_validator':{'file':VALIDATOR_ZIP.name,'sha256':VALIDATOR_ZIP_SHA,'script_sha256':VALIDATOR_SCRIPT_SHA},
 'historical_sources':[{'version':'v2.0.4','role':'historical parent and baseline registers only'},{'version':'v2.0.3','role':'historical 500/100 row-level dispositions only'}],
 'supersession_rule':'No parallel edits to earlier lineages; all current changes are represented in the pinned reconciled source.'
}
dump(OUT/'00_PACKAGE_CONTROL/LINEAGE_MANIFEST.json',lineage_manifest)

status_label='SYNTHETIC TEST FIXTURE — NOT A RELEASE CANDIDATE' if SYNTHETIC_TEST_MODE else 'Candidate for independent Codex review'
status=f'''# Package M0 Status\n\n**Status:** {status_label}.\n\n**M0R authorized:** No.\n\n**Implementation authorized:** No.\n\nThe exact ZIP, checksum, canonical source root and validator hashes must be pinned in the review verdict.\n'''
write(OUT/'00_PACKAGE_CONTROL/PACKAGE_M0_STATUS.md',status)
readme=f'''# {PACKAGE_NAME}\n\nStatus: **{status_label}**.\n\n## Start here\n\n1. Read `00_PACKAGE_CONTROL/PACKAGE_M0_STATUS.md`.\n2. Run `python 06_TOOLS/validate_package_m0.py .`.\n3. Read `03_HUMAN_READABLE/01_SOURCE_OF_TRUTH.md`.\n4. Use `05_REVIEW_AND_BUILD/CODEX_PACKAGE_M0_REVIEW_BRIEF.md` for the independent verdict.\n\n## Current boundary\n\nDo not create M0R, a database, migration `0001`, application code or runtime services until Package M0 is independently approved.\n'''
write(OUT/'00_PACKAGE_CONTROL/README.md',readme)

# Generation manifest - filled after binary projections.
generation={
 'package_version':PACKAGE_VERSION,'generation_mode':'deterministic-no-timestamp',
 'canonical_source_sha256':SOURCE_ZIP_SHA,'canonical_content_root_sha256':SOURCE_ROOT_SHA,
 'frozen_validator_sha256':VALIDATOR_SCRIPT_SHA,'workbook_projection_model_sha256':WORKBOOK_MODEL_SHA256,
 'text_projections':{},'binary_projections':{}
}
for name in human_files:
    p=OUT/'03_HUMAN_READABLE'/name;generation['text_projections'][str(p.relative_to(OUT))]=sha(p)
for p in [OUT/'03_HUMAN_READABLE'/f'HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.md',OUT/'05_REVIEW_AND_BUILD/CODEX_PACKAGE_M0_REVIEW_BRIEF.md',OUT/'05_REVIEW_AND_BUILD/BUILD_IMPLEMENTATION_BRIEF.md',OUT/'05_REVIEW_AND_BUILD/M0R_REPOSITORY_CONFORMANCE_PLAN.md',OUT/'05_REVIEW_AND_BUILD/BUILD_CONTROL_REQUIREMENT_OWNERSHIP.md',OUT/'05_REVIEW_AND_BUILD/MILESTONE_ACCEPTANCE_MATRIX.md']:
    generation['text_projections'][str(p.relative_to(OUT))]=sha(p)
for p in [requirements_workbook,decision_workbook,occurrence_workbook,master_docx,master_pdf]:
    generation['binary_projections'][str(p.relative_to(OUT))]=sha(p)
generation['synthetic_test_mode']=SYNTHETIC_TEST_MODE
dump(OUT/'00_PACKAGE_CONTROL/GENERATION_MANIFEST.json',generation)

# Copy this generator source for reproducibility.
safe_copy2(Path(__file__),OUT/'06_TOOLS/generator/generate_v209_package.py')
safe_copy2(PROJECTION_MODULE,OUT/'06_TOOLS/generator/projection_artifacts.py')
safe_copy2(WORKBOOK_MODEL,OUT/'06_TOOLS/generator/workbook_projection_model.py')

# Deterministic content root and control manifests.
semantic_entries=[]
for path in sorted((OUT/'02_MACHINE_READABLE').glob('*.json')):
    semantic_entries.append({'path':path.relative_to(OUT).as_posix(),'semantic_sha256':semhash(load(path))})
content_root_payload={'version':PACKAGE_VERSION,'semantic_entries':semantic_entries}
generated_content_root=hashlib.sha256(canon(content_root_payload)).hexdigest()
dump(OUT/'CANONICAL_CONTENT_ROOT.json',{'version':PACKAGE_VERSION,'canonical_content_root_sha256':generated_content_root,'semantic_entries':semantic_entries})
generation=load(OUT/'00_PACKAGE_CONTROL/GENERATION_MANIFEST.json')
generation['canonical_content_root_sha256']=generated_content_root
generation['input_pins']=dict(sorted(INPUT_PINS.items()))
physical_input_paths={
 'canonical-source-zip':f'01_CANONICAL_SOURCE/{SOURCE_ZIP.name}',
 'validator-freeze-zip':f'01_CANONICAL_SOURCE/{VALIDATOR_ZIP.name}',
 'baseline-zip':f'01_CANONICAL_SOURCE/{BASELINE_ZIP.name}',
 'occurrence-registry':'08_HISTORY/INPUTS/canonical_occurrence_registry.json',
 'governed-fields':'02_MACHINE_READABLE/governed_fields.json',
 'occurrence-schema':'07_SCHEMAS/forbidden_occurrence_registry.schema.json',
 'occurrence-validator':'06_TOOLS/frozen_validator/forbidden_occurrence_validator.py',
 'detection-module':'06_TOOLS/frozen_validator/occurrence_mechanism.py',
 'mechanism-suite':'06_TOOLS/test_occurrence_mechanism.py',
}
generation['physical_input_artifacts']={key:{'path':path,'sha256':sha(OUT/path)} for key,path in physical_input_paths.items()}
package_validator_path=OUT/'06_TOOLS/validate_package_m0.py'
package_validator_sha=sha(package_validator_path)
generation['package_validator_sha256']=package_validator_sha
generation['p208_validator_profile']={
 'package_version':PACKAGE_VERSION,
 'validator_path':'06_TOOLS/validate_package_m0.py',
 'validator_sha256':package_validator_sha,
}
dump(OUT/'00_PACKAGE_CONTROL/GENERATION_MANIFEST.json',generation)
package_manifest={
 'package_name':PACKAGE_NAME,'package_version':PACKAGE_VERSION,
 'canonical_source':{'filename':SOURCE_ZIP.name,'sha256':SOURCE_ZIP_SHA},
 'validator':{'filename':'forbidden_occurrence_validator.py','sha256':VALIDATOR_SCRIPT_SHA},
 'package_validator':{'path':'06_TOOLS/validate_package_m0.py','sha256':package_validator_sha},
 'p208_validator_profile':{
  'package_version':PACKAGE_VERSION,
  'validator_path':'06_TOOLS/validate_package_m0.py',
  'validator_sha256':package_validator_sha,
 },
 'workbook_projection_model':{'path':'06_TOOLS/workbook_projection_model.py','sha256':WORKBOOK_MODEL_SHA256},
 'counts':implementation_manifest['counts'],
 'primary_files':{
  'master_markdown':f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.md',
  'master_docx':f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.docx',
  'master_pdf':f'03_HUMAN_READABLE/HOSPITALITY_OS_PHASE_1_MASTER_BLUEPRINT_v{PACKAGE_VERSION}.pdf',
  'requirements_workbook':f'04_WORKBOOKS/Requirements_Traceability_Matrix_v{PACKAGE_VERSION}.xlsx',
  'decision_workbook':f'04_WORKBOOKS/Decision_Lineage_and_Evidence_Register_v{PACKAGE_VERSION}.xlsx',
  'occurrence_workbook':f'04_WORKBOOKS/Canonical_Occurrence_Registry_v{PACKAGE_VERSION}.xlsx'},
 'synthetic_test_mode':SYNTHETIC_TEST_MODE,
 'canonical_content_root_sha256':generated_content_root
}
dump(OUT/'00_PACKAGE_CONTROL/PACKAGE_MANIFEST.json',package_manifest)
def rebuild_inventory_and_checksums():
    excluded={'00_PACKAGE_CONTROL/PACKAGE_INVENTORY.json','SHA256SUMS.txt'}
    paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.relative_to(OUT).as_posix() not in excluded)
    inventory={'package_version':PACKAGE_VERSION,'file_count':len(paths),'files':[
      {'path':p.relative_to(OUT).as_posix(),'size_bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]}
    dump(OUT/'00_PACKAGE_CONTROL/PACKAGE_INVENTORY.json',inventory)
    checksum_paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt')
    write(OUT/'SHA256SUMS.txt','\n'.join(f"{sha(p)}  ./{p.relative_to(OUT).as_posix()}" for p in checksum_paths))
rebuild_inventory_and_checksums()
assert_no_reparse(OUT,'completed output before validation',include_tree=True)
validation_report=extract_root/'generator-final-validation.json'
if validation_report.exists():raise RuntimeError('final validation report path unexpectedly exists')
delivered_validator=(OUT/'06_TOOLS/validate_package_m0.py').resolve(strict=True)
if sha(delivered_validator)!=package_validator_sha or load(OUT/'00_PACKAGE_CONTROL/GENERATION_MANIFEST.json').get('package_validator_sha256')!=package_validator_sha or load(OUT/'00_PACKAGE_CONTROL/PACKAGE_MANIFEST.json').get('package_validator',{}).get('sha256')!=package_validator_sha:
 raise RuntimeError('delivered package validator does not match both recorded execution pins')
validation_temp=extract_root/'validator-temp';validation_temp.mkdir()
validation_command=[str(Path(sys.executable).resolve(strict=True)),str(delivered_validator),str(OUT.resolve(strict=True)),'--json-report',str(validation_report)]
validation_env={key:os.environ[key] for key in ('SystemRoot','WINDIR') if key in os.environ}
validation_env.update({'TEMP':str(validation_temp),'TMP':str(validation_temp)})
validation_env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','PYTHONNOUSERSITE':'1','PYTHONSAFEPATH':'1'})
validation_process=subprocess.run(validation_command,capture_output=True,text=True,check=False,cwd=str(OUT.parent),env=validation_env)
if not validation_report.is_file() or is_reparse(validation_report):raise RuntimeError('generated validator did not create a regular fresh report')
validation=json.loads(validation_report.read_text(encoding='utf-8'))
valid_schema=(isinstance(validation,dict) and validation.get('validator_version')==f'{PACKAGE_VERSION}-package-m0' and isinstance(validation.get('passed'),bool) and isinstance(validation.get('failure_count'),int) and isinstance(validation.get('failures'),list) and validation.get('failure_count')==len(validation.get('failures')))
if not valid_schema or validation_process.returncode!=0 or validation.get('passed') is not True or validation.get('failures')!=[]:
    raise RuntimeError(f'generated package failed mandatory validation: exit={validation_process.returncode} report={validation}')
archive_sha=None
if ARCHIVE_OUT is not None:
    assert_no_reparse(ARCHIVE_OUT.parent,'archive output parent');assert_no_reparse(ARCHIVE_SHA_OUT.parent,'archive sidecar parent')
    if ARCHIVE_OUT.exists() or ARCHIVE_SHA_OUT.exists():fail('archive destination appeared before publication',EXIT_OUTPUT)
    archive_fd,archive_name=tempfile.mkstemp(prefix='.v209-archive-',suffix='.tmp',dir=str(ARCHIVE_OUT.parent));os.close(archive_fd)
    sidecar_fd,sidecar_name=tempfile.mkstemp(prefix='.v209-sidecar-',suffix='.tmp',dir=str(ARCHIVE_SHA_OUT.parent));os.close(sidecar_fd)
    archive_temp=Path(archive_name);sidecar_temp=Path(sidecar_name)
    archive_temp.unlink();sidecar_temp.unlink()
    try:
        emit_deterministic_archive(OUT,archive_temp,PACKAGE_NAME)
        archive_sha=sha(archive_temp)
        sidecar_temp.write_text(f'{archive_sha}  {ARCHIVE_OUT.name}\n',encoding='utf-8')
        os.link(archive_temp,ARCHIVE_OUT)
        try:os.link(sidecar_temp,ARCHIVE_SHA_OUT)
        except Exception:
            ARCHIVE_OUT.unlink(missing_ok=True);raise
    finally:
        archive_temp.unlink(missing_ok=True);sidecar_temp.unlink(missing_ok=True)
print(json.dumps({'package_dir':str(OUT),'requirements':len(requirements),'decisions':len(decisions),'journeys':len(journeys),'state_machines':len(state_machines['state_machines']),'canonical_content_root_sha256':generated_content_root,'mandatory_validation_passed':True,'package_validator_sha256':package_validator_sha,'executed_validator_path':str(delivered_validator),'validator_stdout_sha256':hashlib.sha256(validation_process.stdout.encode()).hexdigest(),'validator_stderr_sha256':hashlib.sha256(validation_process.stderr.encode()).hexdigest(),'archive_sha256':archive_sha,'synthetic_test_mode':SYNTHETIC_TEST_MODE},indent=2))
