#!/usr/bin/env python3
"""Upload validated exports; credentials are read from environment or Git, never logged."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'xtulnx/wqx-resources'
TAG = 'resources-current'
API = 'https://api.github.com/repos/' + REPO


def token():
    value = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if value:
        return value
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    return values.get('password')


def main():
    credentials = token()
    if not credentials:
        print('缺少 GitHub 写入凭据。请配置 Git HTTPS 凭据或在本机设置 GH_TOKEN/GITHUB_TOKEN；不要把令牌发到聊天或写入仓库。', file=sys.stderr)
        return 2

    def request(url, method='GET', body=None, binary=False):
        headers = {'Authorization': 'Bearer ' + credentials, 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'wqx-resources-publisher',
                   'Content-Type': 'application/octet-stream' if binary else 'application/json'}
        data = body if binary else (json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=180) as response:
            return json.load(response)

    payloads = ROOT / 'dist/payloads/releases/download' / TAG
    files = sorted(payloads.glob('*'))
    if not files:
        raise ValueError('请先执行 resources.py build --export')
    for file in files:
        if not file.is_file() or not file.stem.isalnum() or len(file.stem) != 64:
            raise ValueError('导出文件名称异常')
        digest = hashlib.file_digest(file.open('rb'), 'sha256').hexdigest()
        if digest != file.stem:
            raise ValueError('导出文件摘要不一致，停止上传')
    # Source is committed and pushed first, avoiding manifests referring to an absent branch.
    try:
        release = request(API + '/releases/tags/' + TAG)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        releases = request(API + '/releases?per_page=100')
        release = next((r for r in releases if r['tag_name'] == TAG), None)
        if release is None:
            release = request(API + '/releases', 'POST', {
                'tag_name': TAG, 'target_commitish': 'main', 'name': '文曲星资源下载', 'draft': True,
                'body': '历史资源，授权未确认。请阅读仓库 docs/DISCLAIMER.md；如有侵权请通过版权投诉入口请求暂停或移除。'})
    existing = {}
    for page in range(1, 100):
        batch = request(API + f"/releases/{release['id']}/assets?per_page=100&page={page}")
        existing.update({a['name']: a for a in batch})
        if len(batch) < 100:
            break
    upload_url = release['upload_url'].split('{')[0]

    def upload(file):
        asset = existing.get(file.name)
        if asset:
            if asset['size'] != file.stat().st_size:
                raise ValueError('现有同名附件大小不一致，请先人工核实')
            return
        request(upload_url + '?name=' + urllib.parse.quote(file.name), 'POST', file.read_bytes(), binary=True)
        print('已上传 ' + file.name, flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(upload, files))
    if release.get('draft'):
        request(API + '/releases/' + str(release['id']), 'PATCH', {'draft': False})
    print('附件发布完成：https://github.com/' + REPO + '/releases/tag/' + TAG)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        # Avoid dumping request objects or headers that may include credentials.
        print('发布未完成：' + type(error).__name__ + '；请检查权限、网络和已上传附件后重试。', file=sys.stderr)
        sys.exit(1)
