#!/usr/bin/env python3
"""Local intake and explicitly reviewed release export; Python standard library only."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
KERNELS = {
    '35': ('3.5内核 by Sun', '3.5', 'Sun'),
    '41': ('4.1内核 by qiqi', '4.1', 'qiqi'),
    '41cam': ('4.1内核保留剑桥版 by qiqi', '4.1-cambridge', 'qiqi'),
    'epc50': ('5.0内核 by epc', '5.0', 'epc'),
    'ecp50': ('5.0内核 by epc', '5.0', 'epc'),
    'fc42': ('非常4.2内核 by 41824984', '4.2', '41824984'),
}
PAGE_SIZE = 25
APP_MODELS = {'nc1020', 'nc1020tw', 'nc2000', 'nc2600', 'nc3000', 'pc1000'}
CATALOG_MODELS = APP_MODELS | {'nc2000tw', 'pc2000', 'pc2300', 'tc1000'}
FIRMWARE = {'.rom', '.nor', '.nand', '.nand0'}
PROGRAMS = {'.bin': 'bin', '.bas': 'basic', '.lav': 'lava'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def model_hint(text):
    match = re.search(r'(?<![a-z0-9])(nc1020tw|nc2000tw|nc1020|nc2000|nc2600|nc3000|pc1000|pc2000|pc2300|tc1000)(?![0-9])', text.lower())
    return match.group(1) if match else None


def collection_classification(rel):
    # Directory evidence only. Names of executables do not establish a device target.
    dirs = rel.parts[:-1]
    hint = model_hint('/'.join(dirs))
    if hint:
        return hint, hint, 'directory-model'
    lower = [d.lower() for d in dirs]
    if rel.suffix.lower() == '.bas' and 'gvbasic' in lower:
        return None, 'gvbasic', 'directory-runtime'
    if rel.suffix.lower() == '.lav' and 'lava' in lower:
        return None, 'lava', 'directory-runtime'
    return None


def write_tree(base, prefix, records):
    """Every resource is a file; every leaf index contains at most 25 references.

    All paths are relative to base, regardless of the referring index location.
    """
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for record in sorted(records, key=lambda r: r['id']):
        category = record.get('category', record.get('type'))
        group = record.get('classification', '-'.join(record.get('models', [])) or 'unknown')
        for segment in [category, group, record['id']]:
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', segment):
                raise ValueError('目录路径字段不合法')
        path = f"{prefix}/{category}/{group}/entries/{record['id']}.json"
        write(base / path, record)
        grouped[category][group].append({'id': record['id'], 'path': path})
    categories = []
    for category, groups in sorted(grouped.items()):
        group_refs = []
        for group, refs in sorted(groups.items()):
            pages = []
            for start in range(0, len(refs), PAGE_SIZE):
                path = f'{prefix}/{category}/{group}/pages/{start // PAGE_SIZE + 1:04d}.json'
                write(base / path, {'schemaVersion': 2, 'resources': refs[start:start + PAGE_SIZE]})
                pages.append({'path': path, 'count': len(refs[start:start + PAGE_SIZE])})
            path = f'{prefix}/{category}/{group}/index.json'
            # Hash/page fan-out remains bounded as the catalog grows.
            if len(pages) > PAGE_SIZE:
                raise ValueError('单分类超过625项，请按子分类拆分后导入')
            write(base / path, {'schemaVersion': 2, 'pages': pages})
            group_refs.append({'id': group, 'count': len(refs), 'path': path})
        path = f'{prefix}/{category}/index.json'
        write(base / path, {'schemaVersion': 2, 'groups': group_refs})
        categories.append({'id': category, 'path': path})
    return {'schemaVersion': 2, 'categories': categories}


def iter_records(base, index):
    doc = read(index)
    for key in ['categories', 'groups', 'pages']:
        if key in doc:
            for ref in doc[key]:
                path = (base / ref['path']).resolve()
                if not path.is_relative_to(base.resolve()):
                    raise ValueError('索引路径越界')
                yield from iter_records(base, path)
            return
    for ref in doc.get('resources', []):
        path = (base / ref['path']).resolve()
        if not path.is_relative_to(base.resolve()):
            raise ValueError('资源路径越界')
        yield read(path)


def intake(args):
    sources = [('firmware', Path(args.roms).resolve()), ('collection', Path(args.collection).resolve())]
    for _, base in sources:
        if not base.is_dir():
            raise ValueError(f'来源不存在: {base}')
    candidates, skipped, object_sizes = [], [], {}
    groups = {}
    for source_kind, base in sources:
        for f in sorted(base.rglob('*')):
            if not f.is_file():
                continue
            rel = f.relative_to(base)
            reason = None
            if f.is_symlink() or not f.resolve().is_relative_to(base):
                reason = 'symlink-or-outside-source'
            elif f.name.startswith('.'):
                reason = 'hidden-file'
            elif source_kind == 'firmware':
                if f.suffix.lower() == '.nand0':
                    reason = 'temporary-nand0'
                elif f.suffix.lower() not in FIRMWARE:
                    reason = 'state-or-unrecognized-format'
            elif any(part.lower() in {'pc端', '6502simulator'} for part in rel.parts):
                reason = 'host-tools-not-device-resources'
            elif f.suffix.lower() not in PROGRAMS:
                reason = 'archive-document-source-or-unrecognized-format'
            elif any(word in str(rel).lower() for word in ['注册机', '破解', 'keygen', 'crack']):
                reason = 'requires-special-rights-review'
            if not reason and source_kind == 'collection' and not collection_classification(rel):
                reason = 'unidentified-directory-target'
            if not reason and source_kind == 'firmware' and not (f.stem.lower() in KERNELS or model_hint(f.stem)):
                reason = 'unidentified-firmware-model'
            if reason:
                skipped.append({'source': source_kind, 'path': str(rel), 'reason': reason})
                continue
            sha = digest(f)
            obj = LOCAL / 'objects' / sha[:2] / sha
            obj.parent.mkdir(parents=True, exist_ok=True)
            if not obj.exists():
                shutil.copyfile(f, obj)
            if digest(obj) != sha:
                raise ValueError(f'副本校验失败: {rel}')
            object_sizes[sha] = f.stat().st_size
            directory_class = collection_classification(rel) if source_kind == 'collection' else None
            hint = directory_class[0] if directory_class else model_hint(f.stem)
            kernel = KERNELS.get(f.stem.lower()) if source_kind == 'firmware' else None
            classification = 'nc2000-nc2600-kernels' if kernel else (directory_class[1] if directory_class else hint)
            category = 'firmware' if source_kind == 'firmware' else PROGRAMS[f.suffix.lower()]
            # Firmware filename prefix is a hint, not proof of model/version/pristine state.
            group = f'{source_kind}/{category}/{hint or "unknown"}/{f.stem}' if category == 'firmware' else f'{source_kind}/{rel}'
            key = hashlib.sha256(group.encode()).hexdigest()[:16]
            item = groups.get(key)
            if item is None:
                item = {'id': 'candidate-' + key, 'title': f.stem, 'category': category,
                        'modelHint': hint, 'compatibility': 'unverified', 'rights': 'unknown',
                        'releaseEligible': False, 'classification': classification,
                        'classificationEvidence': 'maintainer-confirmed' if kernel else (directory_class[2] if directory_class else 'filename-model'),
                        'files': []}
                if kernel:
                    item.update(title=kernel[0], version=kernel[1], author=kernel[2],
                                modelHint=None, modelHints=['nc2000', 'nc2600'])
                groups[key] = item
                candidates.append(item)
            item['files'].append({'source': str(base), 'relativePath': str(rel),
                                  'name': f.name, 'role': f.suffix.lower()[1:],
                                  'bytes': f.stat().st_size, 'sha256': sha,
                                  'object': str(obj.relative_to(ROOT))})
    # Prepare a fresh generation so removed/unrecognized entries cannot remain active.
    next_dir = LOCAL / 'next-inventory'
    if next_dir.exists():
        shutil.rmtree(next_dir)
    next_dir.mkdir(parents=True)
    result = write_tree(next_dir, 'inventory', candidates)
    old_dir = LOCAL / 'inventory'
    if old_dir.exists():
        shutil.rmtree(old_dir)
    shutil.move(str(next_dir / 'inventory'), str(old_dir))
    next_dir.rmdir()
    write(LOCAL / 'inventory.json', result)
    # Omitted-file logs are partitioned by source and capped at 25 entries per page.
    skip_root = LOCAL / 'skipped'
    if skip_root.exists():
        shutil.rmtree(skip_root)
    skipped_refs = []
    for source in ['firmware', 'collection']:
        rows = [r for r in skipped if r['source'] == source]
        for start in range(0, len(rows), PAGE_SIZE):
            path = f'skipped/{source}/{start // PAGE_SIZE + 1:04d}.json'
            write(LOCAL / path, rows[start:start + PAGE_SIZE])
            skipped_refs.append({'path': path, 'count': len(rows[start:start + PAGE_SIZE])})
    # Only two source indexes in the root; pages live under their source.
    sources_index = []
    for source in ['firmware', 'collection']:
        path = f'skipped/{source}/index.json'
        write(LOCAL / path, {'pages': [r for r in skipped_refs if r['path'].startswith(f'skipped/{source}/')]})
        sources_index.append({'id': source, 'path': path})
    write(LOCAL / 'skipped.json', {'schemaVersion': 2, 'sources': sources_index})
    summary = {'resources': len(candidates), 'files': sum(len(c['files']) for c in candidates),
               'uniqueObjects': len(object_sizes), 'uniqueBytes': sum(object_sizes.values()),
               'categories': dict(collections.Counter(c['category'] for c in candidates)),
               'modelHints': dict(collections.Counter(c['modelHint'] or 'unknown' for c in candidates)),
               'skippedFiles': len(skipped), 'skippedReasons': dict(collections.Counter(s['reason'] for s in skipped))}
    write(LOCAL / 'summary.json', summary)
    lines = ['# 待审核资源分类索引', '', '明细按类型、目标机型或运行环境分层保存，每个资源独立文件。', '']
    for ref in result['categories']:
        lines.append(f"- [{ref['id']}]({ref['path']})")
    lines += ['', '统计见 summary.json；跳过记录见 skipped.json。',
              'gvbasic/lava 表示识别到运行环境，不表示兼容全部机型。']
    (LOCAL / 'REVIEW.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def relative_path(value):
    if not isinstance(value, str) or not value or len(value) > 1024 or value.startswith('/'):
        raise ValueError('路径必须相对于资源仓库根目录')
    if any((ord(c) < 32 or 127 <= ord(c) <= 159) or c in '\\:%?#' for c in value) or any(p in {'', '.', '..'} for p in value.split('/')):
        raise ValueError('资源相对路径无效')
    return value


def public_evidence(value):
    path = ROOT / value
    if not value.startswith('licenses/evidence/') or not path.resolve().is_relative_to((ROOT / 'licenses/evidence').resolve()) or not path.is_file():
        raise ValueError('授权证据必须是 licenses/evidence/ 下的公开文件')
    return value


def build(args):
    approvals = [read(p) for p in sorted((ROOT / 'review/entries').rglob('*.json'))]
    inventory_path = LOCAL / 'inventory.json'
    inventory = {r['id']: r for r in iter_records(LOCAL, inventory_path)} if inventory_path.exists() else {}
    resources, exports, ids = [], {}, set()
    for approval in approvals:
        unverified = approval.get('status') == 'maintainer-published-unverified'
        if approval.get('status') != 'approved' and not unverified:
            continue
        for field in ['id', 'candidateId', 'title', 'version', 'author', 'license', 'evidence',
                      'models', 'compatibilityNotes', 'usage', 'files']:
            if field == 'models' and unverified and approval.get('models') == []:
                continue
            if not approval.get(field):
                raise ValueError(f'审批缺少字段: {field}')
        resource_id = approval['id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,79}', resource_id) or resource_id in ids:
            raise ValueError('资源 ID 格式错误或重复')
        ids.add(resource_id)
        if unverified and (approval.get('rightsStatus') != 'unverified' or not approval.get('publicationDecision')):
            raise ValueError('授权未确认发布必须明确标注权利状态与维护者决定')
        if not unverified and approval['license'].strip().lower() in {'unknown', 'pending', '待确认', '待审核'}:
            raise ValueError('许可证尚未确认')
        if not isinstance(approval['models'], list) or not set(approval['models']).issubset(CATALOG_MODELS):
            raise ValueError('机型必须使用已知目录机型；未知机型不得臆测')
        if unverified:
            if approval['evidence'] != 'docs/DISCLAIMER.md' or not (ROOT / approval['evidence']).is_file():
                raise ValueError('未授权发布必须引用免责声明，不得伪造授权证据')
        else:
            public_evidence(approval['evidence'])
        candidate = inventory[approval['candidateId']]
        known = {f['sha256']: f for f in candidate['files']}
        files = []
        for selection in approval['files']:
            src = known[selection['sha256']]
            obj = ROOT / src['object']
            if not obj.resolve().is_relative_to((LOCAL / 'objects').resolve()) or digest(obj) != src['sha256']:
                raise ValueError('本地文件校验失败')
            path = relative_path(selection['path'])
            if not (path.startswith('assets/') or path.startswith('releases/download/')):
                raise ValueError('附件路径必须位于 assets/ 或 releases/download/')
            # Stable paths and versions may be replaced; SHA-256 remains authoritative.
            files.append({'name': src['name'], 'role': src['role'], 'bytes': src['bytes'],
                          'sha256': src['sha256'], 'path': path})
            if path in exports and exports[path] != obj:
                raise ValueError('不同附件不能使用同一个发布路径')
            exports[path] = obj
        logo = approval.get('logo')
        if logo:
            relative_path(logo)
        screenshots = approval.get('screenshots', [])
        if not isinstance(screenshots, list) or len(screenshots) > 8:
            raise ValueError('截图最多8张')
        for screenshot in screenshots:
            relative_path(screenshot)
        description = approval.get('description', '')
        if not isinstance(description, str) or len(description) > 12000:
            raise ValueError('简介过长')
        resources.append({k: approval[k] for k in ['id', 'title', 'version', 'author', 'license',
                                                   'evidence', 'models', 'compatibilityNotes', 'usage']}
                         | {'type': candidate['category'], 'description': description,
                            'logo': logo or '', 'screenshots': screenshots, 'files': files,
                            'classification': candidate['classification'],
                            'rightsStatus': 'unverified' if unverified else 'authorized'})
    if args.export and (ROOT / 'dist').exists():
        raise ValueError('dist 已存在；先手动核对并移走旧导出，避免混入撤回资源')
    # Build the complete tree in private staging before replacing any public file.
    staging = LOCAL / 'generated-catalog'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    catalog = write_tree(staging, 'catalog', resources)
    # Validate every record before generating any publication artifact.
    if args.export:
        dist = ROOT / 'dist'
        dist.mkdir()
        for path, obj in exports.items():
            target = dist / 'payloads' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(obj, target)
        if (staging / 'catalog').exists():
            shutil.copytree(staging / 'catalog', dist / 'catalog')
        write(dist / 'catalog.json', catalog)
    # Replace only generated catalog shards after all approvals have been validated.
    generated = ROOT / 'catalog'
    if generated.exists():
        shutil.rmtree(generated)
    if (staging / 'catalog').exists():
        shutil.move(str(staging / 'catalog'), str(generated))
    write(ROOT / 'catalog.json', catalog)
    shutil.rmtree(staging)
    print(f'已生成目录: {len(resources)} 个维护者确认发布的资源；未联网、未上传。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('intake', help='只读扫描来源，复制可识别文件到忽略的 .local')
    scan.add_argument('--roms', required=True)
    scan.add_argument('--collection', required=True)
    publish = commands.add_parser('build', help='校验显式审批记录并生成公开目录')
    publish.add_argument('--export', action='store_true', help='额外复制审批通过的附件到 dist（不上传）')
    args = parser.parse_args()
    try:
        intake(args) if args.command == 'intake' else build(args)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f'错误: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
