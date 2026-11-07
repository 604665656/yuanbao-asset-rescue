# -*- coding: utf-8 -*-
"""给 yuanbao-asset-rescue 建一个路线图看板（幂等）。

- ProjectV2「yuanbao-asset-rescue · 路线图」，public
- 优先级单选字段 P0/P1/P2
- 几条关于工具迭代 / 经验沉淀的议题，关联本仓库并写入优先级
"""
import json
import os
import urllib.request
import urllib.error

TOKEN = os.environ['GH_TOKEN']
OWNER = '604665656'
REPO = 'yuanbao-asset-rescue'
API = 'https://api.github.com'
GQL = 'https://api.github.com/graphql'


def gql(query, variables=None):
    req = urllib.request.Request(GQL,
        data=json.dumps({'query': query, 'variables': variables or {}}).encode(),
        method='POST')
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            return json.loads(f.read().decode())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_body': e.read().decode()[:300]}


def rest(method, path, data=None):
    req = urllib.request.Request(API + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            return json.loads(f.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_body': e.read().decode()[:300]}


def owner_id():
    d = gql('{user(login:"%s"){id}}' % OWNER)['data']['user']['id']
    return d


def repo_id():
    d = gql('{repository(owner:"%s",name:"%s"){id}}' % (OWNER, REPO))['data']['repository']['id']
    return d


def ensure_issues():
    # 先查已存在的，按标题复用；不存在才建
    existing = rest('GET', '/repos/%s/%s/issues?state=open&per_page=100' % (OWNER, REPO))
    have = {i['title']: i['number'] for i in existing if 'title' in i}
    specs = [
        ('P1', '跨平台缓存路径自动探测',
         'macOS（~/Library/...）和 Linux 的元宝/WebView 缓存位置自动探测；支持非默认 Edge 用户数据目录。'),
        ('P1', '视觉去重（pHash 二次去重）',
         '同一张图可能以不同尺寸/质量多次缓存，sha1 去重会漏。加感知哈希（pHash）二次去重。'),
        ('P2', '噪声自动预筛',
         '用轻量特征（纯色背景占比、文字密度）在 triage 前预筛「界面截图/logo/图表」，减少人工逐张挑的量。'),
        ('P2', '图廊筛选',
         '图廊支持按宽高、绿占比、桶筛选，便于在几百张里快速定位某类图。'),
        ('P1', 'push.py 断点续传',
         '代理断了能从失败的批继续，而不是从头推；加 --dry-run。'),
        ('P1', 'EXCLUDE 外置为 exclude.json',
         '剔除清单现在硬编码在 build_archive.py 里，换个项目就得改脚本。挪成独立的 '
         'exclude.json（按桶 + 编号），triage 后直接编辑，脚本读文件；同时支持 --exclude 指定路径。'),
        ('P2', '导出被去重的重复图清单',
         'recover.py 现在把 sha1 重复项只标「重复」不落盘，无法审计。补一份 '
         'duplicates.csv（原缓存ID → 保留的那张 / 重复张数），用于核对去重有没有误杀。'),
        ('P2', '补一份本次哈士喵案例文档',
         '把 526 原始 → 304 唯一 → 246 本项目 + 68 其他对话 的完整数字链、逐格分拣标准、'
         '以及 7 个坑的现场证据写成 CASE.md，作为「以后怎么复用」的样例，而不只是抽象说明。'),
        ('P1', 'merge_round.py 幂等与回退',
         '第 2 轮实测：缓存从 526 条换成 254 条，重新提取 173 张唯一图里 131 张与首轮重复、'
         '42 张真新增。现在靠 sha1 差集 + next_tag 自动编号保证不重复入库，但还缺：'
         '① --undo-round 按轮次整批撤销（删文件 + 回滚清单 + 重建图廊）；'
         '② 一组最小测试档案做回归，验证重复跑两次结果完全一致（清单条数、图廊 card 数、sha 不变）；'
         '③ triage 核对图把「编号 + 缓存ID + 尺寸」画在同一格，避免两套顺序对不上导致误剔。'),
    ]
    created = []
    for pri, title, body in specs:
        if title in have:
            created.append((pri, have[title], title))
            print('  议题已存在 #%d %s' % (have[title], title))
            continue
        r = rest('POST', '/repos/%s/%s/issues' % (OWNER, REPO),
                 {'title': title, 'body': body})
        created.append((pri, r['number'], title))
        print('  建议题 #%d %s' % (r['number'], title))
    return created


def ensure_project():
    # 按标题复用
    d = gql('{user(login:"%s"){projectsV2(first:30){nodes{number title id public}}}}' % OWNER)
    nodes = d['data']['user']['projectsV2']['nodes']
    for p in nodes:
        if p['title'] == 'yuanbao-asset-rescue · 路线图':
            print('  看板已存在 #%d' % p['number'])
            return p['id'], p['number']
    pid = owner_id()
    r = gql('mutation($o:ID!,$t:String!){createProjectV2(input:'
            '{ownerId:$o,title:$t}){projectV2{id,number}}}',
            {'o': pid, 't': 'yuanbao-asset-rescue · 路线图'})
    pr = r['data']['createProjectV2']['projectV2']
    # 设为 public + 写简短说明（updateProjectV2 才接受 shortDescription）
    gql('mutation($p:ID!,$d:String!){updateProjectV2(input:{projectId:$p,public:true,'
        'shortDescription:$d}){projectV2{id}}}',
        {'p': pr['id'], 'd': '从元宝缓存抢救图片的工具迭代与经验沉淀路线图'})
    print('  建看板 #%d' % pr['number'])
    return pr['id'], pr['number']


def add_priority_field(pid):
    # 先查是否已有「优先级」字段，有就复用（幂等）
    d = gql('{node(id:"%s"){... on ProjectV2{fields(first:30){nodes{'
            '... on ProjectV2SingleSelectField{id name options{id name}}}}}}}' % pid)
    for f in d['data']['node']['fields']['nodes']:
        if f.get('name') == '优先级':
            opts = {o['name']: o['id'] for o in f['options']}
            print('  优先级字段已存在:', f['id'])
            return f['id'], opts
    r = gql('mutation($p:ID!,$n:String!,$o:[ProjectV2SingleSelectFieldOptionInput!]!){'
            'createProjectV2Field(input:{projectId:$p,name:$n,dataType:SINGLE_SELECT,'
            'singleSelectOptions:$o}){projectV2Field{... on ProjectV2SingleSelectField{'
            'id options{id name}}}}}',
            {'p': pid, 'n': '优先级',
             'o': [{'name': 'P0 现在就做', 'color': 'RED', 'description': '现在就做'},
                   {'name': 'P1 下一批', 'color': 'YELLOW', 'description': '下一批'},
                   {'name': 'P2 有空再说', 'color': 'GREEN', 'description': '有空再说'}]})
    f = r['data']['createProjectV2Field']['projectV2Field']
    opts = {o['name']: o['id'] for o in f['options']}
    print('  优先级字段:', f['id'])
    return f['id'], opts


def link_repo(pid):
    rid = repo_id()
    gql('mutation($p:ID!,$r:ID!){linkProjectV2ToRepository(input:'
        '{projectId:$p,repositoryId:$r}){repository{id}}}', {'p': pid, 'r': rid})
    print('  已关联仓库', REPO)


def add_items(pid, fid, opts, issues):
    # 已有条目按 issue 编号索引，避免重复添加
    d = gql('{node(id:"%s"){... on ProjectV2{items(first:50){nodes{'
            'id content{... on Issue{number}}}}}}}' % pid)
    have = {}
    for it in d['data']['node']['items']['nodes']:
        num = (it.get('content') or {}).get('number')
        if num is not None:
            have[num] = it['id']
    for pri, num, title in issues:
        if num in have:
            iid = have[num]
        else:
            nid = gql('{repository(owner:"%s",name:"%s"){issue(number:%d){id}}}'
                      % (OWNER, REPO, num))['data']['repository']['issue']['id']
            r = gql('mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:'
                    '{projectId:$p,contentId:$c}){item{id}}}', {'p': pid, 'c': nid})
            iid = r['data']['addProjectV2ItemById']['item']['id']
        vopt = {'P0': 'P0 现在就做', 'P1': 'P1 下一批', 'P2': 'P2 有空再说'}[pri]
        # 内联 singleSelectOptionId：变量类型 ProjectV2ItemFieldValueInput 在某些 schema 下不可用
        q = ('mutation{updateProjectV2ItemFieldValue(input:{projectId:"%s",itemId:"%s",'
             'fieldId:"%s",value:{singleSelectOptionId:"%s"}}){projectV2Item{id}}}'
             % (pid, iid, fid, opts[vopt]))
        gql(q)
        print('  入板 #%d (%s)' % (num, pri))


def main():
    print('== 议题 ==')
    issues = ensure_issues()
    print('== 看板 ==')
    pid, num = ensure_project()
    print('== 优先级字段 ==')
    fid, opts = add_priority_field(pid)
    print('== 关联仓库 ==')
    link_repo(pid)
    print('== 入板 + 优先级 ==')
    add_items(pid, fid, opts, issues)
    print('\n完成。看板: https://github.com/users/%s/projects/%d' % (OWNER, num))


if __name__ == '__main__':
    main()
