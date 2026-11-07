# -*- coding: utf-8 -*-
"""把大仓库分批提交 + 推送。代理长连接不稳时，单次 18MB 左右最稳，每批推完比对 sha。

用法：
    set GH_TOKEN=ghp_xxx
    python push.py --owner 你的名 --repo 仓库名
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

BATCH = 18 * 1024 * 1024


def sh(args, cwd, check=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit('命令失败: %s' % ' '.join(args))
    return r


def head(cwd):
    return sh(['git', 'rev-parse', 'HEAD'], cwd).stdout.strip()


def remote_head(cwd):
    for _ in range(6):
        r = sh(['git', 'ls-remote', 'origin', 'refs/heads/main'], cwd)
        s = (r.stdout or '').strip().split('\t')[0]
        if s:
            return s
    return ''


def push_until_ok(cwd):
    for i in range(1, 7):
        r = sh(['git', '-c', 'http.version=HTTP/1.1', '-c', 'pack.threads=1',
                'push', 'origin', 'HEAD:main'], cwd)
        if r.returncode == 0 and remote_head(cwd) == head(cwd):
            return True
        msg = (r.stderr or '').strip().splitlines()[-1][:80] if r.stderr else ''
        print('   重试 %d（%s）' % (i, msg))
    return remote_head(cwd) == head(cwd)


def ensure_repo(owner, repo, token, desc):
    req = urllib.request.Request('https://api.github.com/repos/%s/%s' % (owner, repo))
    req.add_header('Authorization', 'Bearer ' + token)
    try:
        urllib.request.urlopen(req, timeout=30)
        print('仓库已存在')
    except Exception:
        body = json.dumps({'name': repo, 'description': desc, 'private': False,
                           'auto_init': False, 'has_wiki': False,
                           'has_projects': True}).encode()
        r = urllib.request.Request('https://api.github.com/user/repos', data=body, method='POST')
        r.add_header('Authorization', 'Bearer ' + token)
        r.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(r, timeout=60)
        print('已创建仓库 %s/%s' % (owner, repo))


def main():
    ap = argparse.ArgumentParser(description='大仓库分批推送')
    ap.add_argument('--owner', required=True)
    ap.add_argument('--repo', required=True)
    ap.add_argument('--desc', default='')
    args = ap.parse_args()
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise SystemExit('需要环境变量 GH_TOKEN')

    root = os.path.abspath('.')
    ensure_repo(args.owner, args.repo, token, args.desc)

    if not os.path.isdir(os.path.join(root, '.git')):
        sh(['git', 'init', '-q', '-b', 'main'], root, check=True)
        sh(['git', 'remote', 'add', 'origin',
             'https://github.com/%s/%s.git' % (args.owner, args.repo)], root, check=True)
        print('git 已初始化')

    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ('.git', '__pycache__', '_yb_stage', '_triage')]
        for f in fn:
            p = os.path.join(dp, f)
            files.append((os.path.relpath(p, root).replace('\\', '/'), os.path.getsize(p)))
    files.sort()
    todo = [(p, s) for p, s in files
            if sh(['git', 'status', '--porcelain', '--', p], root).stdout.strip()]
    print('待提交 %d 个文件 / %.1f MB' % (len(todo), sum(s for _, s in todo) / 1048576))

    batches, cur, cursz = [], [], 0
    for p, s in todo:
        if cur and cursz + s > BATCH:
            batches.append(cur)
            cur, cursz = [], 0
        cur.append(p)
        cursz += s
    if cur:
        batches.append(cur)

    for i, b in enumerate(batches, 1):
        sh(['git', 'add', '--'] + b, root, check=True)
        r = sh(['git', '-c', 'user.name=' + args.owner,
                '-c', 'user.email=' + args.owner + '@users.noreply.github.com',
                'commit', '-q', '-m',
                'assets: 第 %d/%d 批（%d 个文件）' % (i, len(batches), len(b))], root)
        if r.returncode:
            print('  提交失败:', r.stderr[:200])
            continue
        ok = push_until_ok(root)
        print('  第 %d/%d 批  %-2d 文件  %s' % (i, len(batches), len(b), 'ok' if ok else '失败'))
        if not ok:
            print('  推送失败，停在第 %d 批' % i)
            sys.exit(1)

    print('\n完成。local=%s remote=%s' % (head(root), remote_head(root)))


if __name__ == '__main__':
    main()
