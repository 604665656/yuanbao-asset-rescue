# -*- coding: utf-8 -*-
"""把 recover.py 产出的 _index.json 整理成可浏览的素材档案（通用工具）。

流程：
  1. 按桶分组 -> 编号 -> 复制到 元宝缓存/<桶>/
  2. 命中 EXCLUDE 的挪到 其他对话/<桶>/（不删，方便回查）
  3. 生成 清单/图片清单.{csv,json}（含 sha1、完整性、归属）
  4. 生成 总览/总览_<桶>.png 分组总览大图
  5. 生成 index.html 图廊（根目录，配合 .nojekyll 直接当静态站）

用法：
    python build_archive.py --title "我的素材档案" --stage _yb_stage
"""
import argparse
import json
import os
import re
import shutil

from PIL import Image, ImageDraw, ImageFile, ImageFont

ImageFile.LOAD_TRUNCATED_IMAGES = True

THUMB_MAX = 420

BUCKETS = [
    ('绿幕与白模', '绿幕/拼板', '纯绿背景上的生成结果与白模拼板，可直接做去背输入'),
    ('生成稿_1328x1776', '1328x1776 生成稿', '元宝默认画布 1328×1776 的整张生成稿'),
    ('大幅', '大幅(>=1000x600)', '尺寸 ≥1000×600 的其他大图，含拼板与成图'),
    ('其他', '其他', '缩略图、小图、界面截图等'),
]

# ---------- 人工通读剔除清单（每次用前按实际目视结果填）----------
# 元宝缓存是整个 App 共用的，别的对话的图也在这里。把不属于本项目的
# 编号写进这里；脚本只挪位不改号，清单里标「其他对话」，可回查。
# 编号 = 该桶内重新编号后的序号（见 001_ 前缀）。
EXCLUDE = {
    '绿幕与白模': [],
    '生成稿_1328x1776': [],
    '大幅': [],
    '其他': [],
}


def font(size):
    for f in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
             'C:/Windows/Fonts/arialbd.ttf'):
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def integrity(p):
    if os.path.splitext(p)[1].lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
        return '非图片'
    try:
        Image.open(p).load()
        return '完整'
    except Exception as e:
        m = re.search(r'truncated \((\d+) bytes', str(e))
        return '截断(缺%s字节)' % m.group(1) if m else '损坏'


def build(stage, root, title):
    idx = os.path.join(stage, '_index.json')
    rows = json.load(open(idx, encoding='utf-8'))
    uniq = [r for r in rows if r.get('bucket') != '重复']

    # 清空旧的产出（保留 .nojekyll / .gitignore / 脚本本身）
    for name, _, _ in BUCKETS:
        d = os.path.join(root, '元宝缓存', name)
        if os.path.isdir(d):
            shutil.rmtree(d)
    for d in ('桌面散件', '总览', '其他对话'):
        p = os.path.join(root, d)
        if os.path.isdir(p):
            shutil.rmtree(p)
    os.makedirs(os.path.join(root, '总览', 'thumb'), exist_ok=True)

    manifest = []
    for dirname, key, note in BUCKETS:
        items = [r for r in uniq if r.get('bucket') == dirname]
        items.sort(key=lambda r: (-(r.get('green') or 0), -r['size']))
        out = os.path.join(root, '元宝缓存', dirname)
        others = os.path.join(root, '其他对话', dirname)
        os.makedirs(out, exist_ok=True)
        os.makedirs(others, exist_ok=True)
        skip = set(EXCLUDE.get(dirname, []))
        for i, r in enumerate(items, 1):
            src = os.path.join(stage, r['file'])
            base = os.path.splitext(r['file'])[0]
            newname = '%03d_%s.%s' % (i, base, r['ext'])
            keep = i not in skip
            dst = os.path.join(out if keep else others, newname)
            shutil.copy2(src, dst)
            _thumb(root, dst, newname)
            manifest.append({
                '组': dirname, '文件': newname, '原缓存ID': base,
                '宽': r.get('w'), '高': r.get('h'), '模式': r.get('mode'),
                '字节': r['size'], '绿占比': r.get('green'),
                'sha1': r['sha1'], '来源': '元宝 App 缓存',
                '完整性': integrity(dst),
                '归属': '本项目' if keep else '其他对话',
            })

    os.makedirs(os.path.join(root, '清单'), exist_ok=True)
    json.dump(manifest, open(os.path.join(root, '清单', '图片清单.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with open(os.path.join(root, '清单', '图片清单.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        f.write('组,文件,原缓存ID,宽,高,模式,字节,绿占比,sha1,完整性,来源,归属\n')
        for m in manifest:
            f.write(','.join(str(m.get(k, '')) for k in
                             ('组', '文件', '原缓存ID', '宽', '高', '模式', '字节', '绿占比',
                              'sha1', '完整性', '来源', '归属')) + '\n')

    for dirname, key, note in BUCKETS:
        _overview(root, manifest, dirname)
    _gallery(root, manifest, title)

    mine = [m for m in manifest if m['归属'] == '本项目']
    other = [m for m in manifest if m['归属'] != '本项目']
    print('\n本项目 %d 个 / %.1f MB   其他对话 %d 个 / %.1f MB   合计 %.1f MB'
          % (len(mine), sum(m['字节'] for m in mine) / 1048576,
             len(other), sum(m['字节'] for m in other) / 1048576,
             sum(m['字节'] for m in manifest) / 1048576))
    for dirname, _, _ in BUCKETS:
        print('  %-20s %3d' % (dirname, len([m for m in mine if m['组'] == dirname])))


def _thumb(root, dst, newname):
    try:
        im = Image.open(dst)
        im = im.convert('RGBA') if im.mode in ('RGBA', 'P', 'LA') else im.convert('RGB')
        if im.mode == 'RGBA':
            bg = Image.new('RGB', im.size, (238, 238, 238))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
        im.save(os.path.join(root, '总览', 'thumb', newname.rsplit('.', 1)[0] + '.jpg'),
                'JPEG', quality=84)
    except Exception as e:
        print('  缩略失败', newname, e)


def _overview(root, manifest, dirname):
    items = [m for m in manifest if m['组'] == dirname and m['归属'] == '本项目']
    if not items:
        return
    cols, cell, pad = 8, 210, 22
    rowsn = (len(items) + cols - 1) // cols
    W = cols * cell + pad * 2
    H = rowsn * (cell + 18) + pad * 2 + 54
    sheet = Image.new('RGB', (W, H), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    d.text((pad, pad), '%s · %d 张' % (dirname, len(items)), fill=(120, 210, 255), font=font(20))
    fl = font(12)
    for i, m in enumerate(items):
        r, c = divmod(i, cols)
        x = pad + c * cell
        y = pad + 54 + r * (cell + 18)
        th = os.path.join(root, '总览', 'thumb', os.path.splitext(m['文件'])[0] + '.jpg')
        if os.path.exists(th):
            im = Image.open(th)
            im.thumbnail((cell - 10, cell - 10), Image.LANCZOS)
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.rectangle([x, y, x + cell - 4, y + cell - 4], outline=(60, 64, 72))
        d.text((x + 4, y + cell - 2), m['文件'][:30], fill=(170, 180, 190), font=fl)
    out = os.path.join(root, '总览', '总览_%s.png' % dirname)
    sheet.save(out, optimize=True)
    print('  总览图:', os.path.basename(out), '%dx%d' % (W, H))


def _gallery(root, manifest, title):
    groups = [(n, note) for n, _, note in BUCKETS]

    parts = ['''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
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
.card img{width:100%%;height:150px;object-fit:contain;background:#1d2128;display:block}
.meta{padding:5px 7px;font-size:10.5px;color:#8b95a5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
footer{padding:26px;color:#6b7482;font-size:12px;border-top:1px solid #23272f}
</style></head><body>
<header><h1>%s</h1>
<div class="sub">从元宝 App 本地缓存恢复本项目 <b>%d</b> 张，点图看原图。另有 <b>%d</b> 张混进来的其他对话图片，已挪到页尾单独存档。</div></header>
<nav>''' % (title, title,
           len([m for m in manifest if m['归属'] == '本项目']),
           len([m for m in manifest if m['归属'] != '本项目']))]
    for dirname, _ in groups:
        n = len([m for m in manifest if m['组'] == dirname and m['归属'] == '本项目'])
        if n:
            parts.append('<a href="#%s">%s（%d）</a>' % (dirname, dirname, n))
    parts.append('</nav><main>')
    for dirname, note in groups:
        items = [m for m in manifest if m['组'] == dirname and m['归属'] == '本项目']
        if not items:
            continue
        parts.append('<section id="%s"><h2>%s</h2><div class="hint">%s</div><div class="grid">'
                     % (dirname, dirname, note))
        for m in items:
            rel = '元宝缓存/' + dirname + '/' + m['文件']
            thumb = '总览/thumb/' + os.path.splitext(m['文件'])[0] + '.jpg'
            dims = ('%s×%s' % (m['宽'], m['高'])) if m['宽'] else ''
            parts.append('<div class="card"><a href="%s" target="_blank"><img loading="lazy" src="%s" alt="%s">'
                         '<div class="meta">%s %s %s</div></a></div>'
                         % (rel, thumb, m['文件'], m['文件'][:14], dims, '%.0fKB' % (m['字节'] / 1024)))
        parts.append('</div></section>')
    oth = [m for m in manifest if m['归属'] != '本项目']
    if oth:
        parts.append('<section id="其他对话"><h2>其他对话（已排除）</h2>'
                     '<div class="hint">同一个元宝账号下别的对话的图片，混在缓存里被一起捞出来的。'
                     '不算本项目素材，但保留存档不删。共 %d 张。</div>'
                     '<details><summary style="cursor:pointer;color:#8b95a5;font-size:12.5px;margin-bottom:10px">展开</summary>'
                     '<div class="grid">' % len(oth))
        for m in oth:
            rel = '其他对话/' + m['组'] + '/' + m['文件']
            thumb = '总览/thumb/' + os.path.splitext(m['文件'])[0] + '.jpg'
            parts.append('<div class="card"><a href="%s" target="_blank"><img loading="lazy" src="%s" alt="%s">'
                         '<div class="meta">%s %s</div></a></div>'
                         % (rel, thumb, m['文件'], m['文件'][:14], '%.0fKB' % (m['字节'] / 1024)))
        parts.append('</div></details></section>')
    parts.append('''</main>
<footer>缩略图在本页，点开是原图。完整字段见 <a href="清单/图片清单.csv" style="color:#5cc8ff">清单/图片清单.csv</a>。
<br>来源：元宝 App（WebView2 缓存）导出。对话正文未缓存，无法恢复。</footer>
</body></html>''')
    open(os.path.join(root, 'index.html'), 'w', encoding='utf-8').write(''.join(parts))
    print('  画廊:', os.path.join(root, 'index.html'))


def main():
    ap = argparse.ArgumentParser(description='把 _index.json 整理成素材档案')
    ap.add_argument('--stage', default='_yb_stage', help='recover.py 的输出目录')
    ap.add_argument('--root', default='.', help='档案输出根目录（默认当前目录）')
    ap.add_argument('--title', default='元宝素材档案', help='图廊标题')
    args = ap.parse_args()
    build(args.stage, os.path.abspath(args.root), args.title)


if __name__ == '__main__':
    main()
