# -*- coding: utf-8 -*-
"""清单驱动的静态图廊生成器（通用版）。

只读档案仓库里的 清单/图片清单.json：
  - 路径  -> 原图相对位置
  - 归属  -> 进主区还是页尾「其他对话」区
  - 组    -> 分区，按清单出现顺序（或用 --sections 指定顺序与说明）

好处：图廊不再依赖提取阶段的中间目录，增量合并 / 手工改清单后重跑即可。

用法：
  python gallery.py --archive /path/to/archive --title "我的素材档案"
  python gallery.py --archive . --sections sections.json
"""
import argparse
import json
import os

DEFAULT_TITLE = '素材档案'


def path_of(m):
    """兼容没有「路径」字段的旧清单。"""
    if m.get('路径'):
        return m['路径']
    g = m.get('组', '')
    if m.get('归属') != '本项目':
        return '其他对话/' + g + '/' + m['文件']
    if g == '桌面散件':
        return '桌面散件/' + m['文件']
    if g.startswith('本轮新增/') or g.startswith('/'):
        return g.lstrip('/') + '/' + m['文件']
    return '元宝缓存/' + g + '/' + m['文件']


def load_sections(p):
    """可选：JSON 数组 [["组名","说明"], ...]，指定分区顺序与提示文案。"""
    if not p:
        return []
    return [tuple(x) for x in json.load(open(p, encoding='utf-8'))]


def build(archive, title=DEFAULT_TITLE, sections=None, subtitle=''):
    root = os.path.abspath(archive)
    mpath = os.path.join(root, '清单', '图片清单.json')
    manifest = json.load(open(mpath, encoding='utf-8'))
    mine = [m for m in manifest if m.get('归属') == '本项目']
    other = [m for m in manifest if m.get('归属') != '本项目']

    missing = []
    for m in manifest:
        rel = path_of(m)
        if not os.path.isfile(os.path.join(root, rel.replace('/', os.sep))):
            missing.append(rel)
    if missing:
        print('  警告：%d 条清单记录找不到原图，前 5 条：' % len(missing))
        for p in missing[:5]:
            print('   ', p)

    order = []
    for m in mine:
        if m.get('组') not in order:
            order.append(m.get('组'))
    if sections:
        given = [g for g, _ in sections]
        order = [g for g in given if g in order] + [g for g in order if g not in given]
    notes = dict(sections or [])

    html = ['''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + title + '''</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0f1115;color:#e6e9ee;font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{padding:22px 26px;border-bottom:1px solid #23272f}
h1{font-size:19px;font-weight:600}
.sub{color:#98a2b3;font-size:12.5px;margin-top:6px}
.sub b{color:#5cc8ff;font-weight:600}
nav{position:sticky;top:0;z-index:5;display:flex;gap:6px;flex-wrap:wrap;
 padding:10px 26px;background:#14171c;border-bottom:1px solid #23272f}
nav a{color:#c9d3e0;text-decoration:none;font-size:12.5px;padding:5px 11px;
 border:1px solid #2c3340;border-radius:999px}
nav a:hover{border-color:#5cc8ff;color:#5cc8ff}
main{padding:8px 26px 60px}
section{margin-top:26px}
h2{font-size:15px;font-weight:600;color:#8fd4ff;margin-bottom:3px}
.hint{color:#8b95a5;font-size:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.card{background:#171a20;border:1px solid #242a33;border-radius:9px;overflow:hidden}
.card:hover{border-color:#5cc8ff}
.card a{display:block;text-decoration:none}
.card img{width:100%;height:150px;object-fit:contain;background:#1d2128;display:block}
.meta{padding:5px 7px;font-size:10.5px;color:#8b95a5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
footer{padding:26px;color:#6b7482;font-size:12px;border-top:1px solid #23272f}
</style></head><body>
<header><h1>''' + title + '''</h1>
<div class="sub">本项目 <b>''' + str(len(mine)) + '''</b> 张，点图看原图。''' + subtitle +
        '''另有 <b>''' + str(len(other)) + '''</b> 张其他来源图片，页尾单独存档。</div></header>
<nav>''']

    nav = ['<a href="#%s">%s（%d）</a>' % (g, g.split('/')[-1], len([m for m in mine if m.get('组') == g]))
           for g in order]
    if other:
        nav.append('<a href="#其他对话">其他对话（%d）</a>' % len(other))
    html.append(''.join(nav) + '</nav><main>')

    def cards(items, with_dims):
        out = []
        for m in items:
            rel = path_of(m)
            thumb = '总览/thumb/' + os.path.splitext(m['文件'])[0] + '.jpg'
            dims = ('%s×%s' % (m['宽'], m['高'])) if with_dims and m.get('宽') else ''
            kb = '%.0fKB' % (m['字节'] / 1024)
            out.append('<div class="card"><a href="%s" target="_blank"><img loading="lazy" src="%s" alt="%s">'
                       '<div class="meta">%s %s %s</div></a></div>'
                       % (rel, thumb, m['文件'], m['文件'][:16], dims, kb))
        return ''.join(out)

    for g in order:
        items = [m for m in mine if m.get('组') == g]
        note = notes.get(g, '自动归组')
        html.append('<section id="%s"><h2>%s</h2><div class="hint">%s · 共 %d 张</div><div class="grid">'
                    % (g, g, note, len(items)))
        html.append(cards(items, True))
        html.append('</div></section>')

    if other:
        html.append('<section id="其他对话"><h2>其他对话 · 单独存档</h2>'
                    '<div class="hint">同一个账号下别的对话的图，混在缓存里被一起捞出来的。'
                    '不算本项目素材，但完整保留不删，默认展开供查。共 %d 张。</div><div class="grid">'
                    % len(other))
        html.append(cards(other, False))
        html.append('</div></section>')

    html.append('''</main>
<footer>缩略图在本页，点开是原图。完整字段见 <a href="清单/图片清单.csv" style="color:#5cc8ff">清单/图片清单.csv</a>。
<br>由 yuanbao-asset-rescue / gallery.py 生成。对话正文未缓存，无法恢复。</footer>
</body></html>''')

    out = os.path.join(root, 'index.html')
    open(out, 'w', encoding='utf-8').write(''.join(html))
    print('  画廊:', out, os.path.getsize(out), '字节')
    print('  主区 %d 张 / 其他 %d 张 / 分区 %d 个 / 缺图 %d'
          % (len(mine), len(other), len(order), len(missing)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', default='.', help='档案仓库根目录')
    ap.add_argument('--title', default=DEFAULT_TITLE)
    ap.add_argument('--subtitle', default='')
    ap.add_argument('--sections', help='JSON 文件，[["组名","说明"], ...]')
    a = ap.parse_args()
    build(a.archive, a.title, load_sections(a.sections), a.subtitle)


if __name__ == '__main__':
    main()
