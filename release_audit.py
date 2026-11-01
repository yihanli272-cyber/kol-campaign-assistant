"""Read-only release allowlist/privacy/import checks. Never stages or publishes files."""
import ast
import csv
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
MANIFEST='release_whitelist.txt'
EMAIL=re.compile(r'[A-Za-z0-9._%+-]{1,254}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}')
TOKEN=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
PASSWORD=re.compile(r'''(?im)(?:api[_-]?key|password|passwd|secret[_-]?key|access[_-]?token)\s*[:=]\s*["'][^"'\n]{6,}["']''')
FORBIDDEN_DIRS={'.venv','venv','env','__pycache__','human_reviews','backup','backups','local_backups','private','local_private','reports','sprint_research'}
FORBIDDEN_SUFFIXES={'.xlsx','.xls','.xlsm','.pdf','.bak','.tmp','.orig','.pem','.key','.p12','.pfx','.log','.pyc'}


def forbidden_path(name):
    p=PurePosixPath(name)
    return (bool(set(p.parts)&FORBIDDEN_DIRS) or p.suffix.lower() in FORBIDDEN_SUFFIXES
            or p.name.startswith('.env') or p.name.lower() in {'secrets.toml','secrets.json'} or p.name.startswith('~$'))


def manifest_files(root=ROOT):
    root=Path(root)
    names=[line.strip() for line in (root/MANIFEST).read_text(encoding='utf-8').splitlines()
           if line.strip() and not line.lstrip().startswith('#')]
    if len(names)!=len(set(names)):
        raise ValueError('发布白名单有重复路径。')
    for name in names:
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or any(c in name for c in '*?[]'):
            raise ValueError('发布白名单只允许项目内的精确相对文件路径。')
    return names


def audit_release(root=ROOT, check_git=True):
    root=Path(root).resolve()
    errors=[]
    try:
        names=manifest_files(root)
    except (OSError,ValueError) as exc:
        return {'files':[],'errors':[str(exc)]}
    included=set(names)
    for name in names:
        path=root/name
        if forbidden_path(name):errors.append('禁止发布路径：'+name)
        if not path.is_file():
            errors.append('白名单文件不存在：'+name);continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            errors.append('白名单不允许符号链接或越界：'+name);continue
        try:
            text=path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            errors.append('非文本发布文件需人工审核：'+name);continue
        for kind,pattern in [('邮箱',EMAIL),('凭据',TOKEN),('口令赋值',PASSWORD)]:
            if pattern.search(text):errors.append(f'发现{kind}候选，请人工核验（不输出原值）：'+name)
        if path.suffix=='.csv':
            rows=list(csv.DictReader(text.splitlines()))
            for row in rows:
                for field,value in row.items():
                    if field and (field.lower() in {'email','phone','mobile','telephone','whatsapp','private_address'} or field.endswith('_checked_by') or field=='checked_by') and str(value or '').strip():
                        errors.append('不应公开的非空联系/审核人员字段：'+name+' / '+field)
        if path.suffix=='.py':
            try:tree=ast.parse(text)
            except SyntaxError:
                errors.append('Python语法错误：'+name);continue
            imports=set()
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):imports.update(a.name.split('.')[0] for a in node.names)
                elif isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module.split('.')[0])
            for module in imports-sys.stdlib_module_names-{'pandas','streamlit'}:
                candidates=[module+'.py','tests/'+module+'.py']
                if not any(p in included for p in candidates):errors.append('发布导入依赖未列入白名单：'+name+' -> '+module)
    try:
        if json.loads((root/'deployment_config.json').read_text(encoding='utf-8')).get('mode')!='public_demo':
            errors.append('发布配置必须为public_demo。')
        campaign=json.loads((root/'campaign_config.json').read_text(encoding='utf-8'))
        directory=campaign.get('creator_registry_directory','data/creator_registry')
        for filename in ['accounts.csv','reviews.csv','content_evidence.csv','campaign_assumptions.csv','hicreator_supplement.csv']:
            if (PurePosixPath(directory)/filename).as_posix() not in included:errors.append('缺少运行数据：'+filename)
    except (OSError,ValueError,AttributeError):errors.append('部署或Campaign配置无效。')
    if check_git:
        try:
            raw=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root)
            for name in raw.decode('utf-8').split('\0'):
                if name and name not in included:errors.append('Git可见文件不在发布白名单：'+name)
            ignored=subprocess.run(['git','check-ignore','--stdin','-z'],cwd=root,
                input=('\0'.join(names)+'\0').encode('utf-8'),capture_output=True)
            if ignored.returncode not in (0,1):errors.append('无法检查Git忽略规则。')
            for name in ignored.stdout.decode('utf-8').split('\0'):
                if name:errors.append('必要发布文件被忽略：'+name)
        except (OSError,subprocess.CalledProcessError):errors.append('无法完成只读Git白名单核验。')
    return {'files':names,'count':len(names),'errors':sorted(set(errors))}


if __name__=='__main__':
    result=audit_release()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(bool(result['errors']))
