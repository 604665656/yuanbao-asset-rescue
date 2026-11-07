# -*- coding: utf-8 -*-
"""增量轮次合并：把新一轮 recover.py 捞到的图并进已有档案，不重建、不覆盖。

典型场景：元宝缓存被新对话挤掉/换批后，重新跑 recover.py 得到一批新图，
其中大部分和上一轮重复。本脚本只并入 sha1 差集里的真新增。

用法：
  # 1) 重新提取（输出到新目录，别覆盖上一轮）
  python recover.py --out ./stage_round2

  # 2) 先出带「编号 + 缓存ID + 尺寸」的核对图，目视分拣
  python triage.py --stage ./stage_round2

  # 3) 增量合并（自动做 sha1 差集；--ui-list 把界面截图单独分组）
  python merge_round.py --archive ./我的档案 --fresh ./stage_round2 \
      --round "第2轮·八向新文件" --ui-list 2,3,8,10,11 --dry-run
  python merge_round.py --archive ./我的档案 --fresh ./stage_round2 \
      --round "第2轮·八向新文件" --ui-list 2,3,8,10,11

设计要点：
  - 每条清单记录都带 路径，图廊由 gallery.py 从清单生成，不再硬编码目录规则
  - 旧记录自动补 轮次/路径，新记录带 轮次
  - 任何一条重复 sha1 都跳过而不是硬失败（通用工具要能反复跑）
"""
import argparse
import csv
import json
import os
import re
import shutil

from PIL import Image, ImageDraw, ImageFile, ImageFont

import gallery

ImageFile.LOAD_TRUNCATED_IMAGES = True

DEFAULT_FIELDS = ['组', '文件', '原缓存ID', '宽', '高', '模式', '字节', '绿占比',
                  'sha1', '完整性', '来源', '归属', '轮次', '路径']
THUMB_MAX = 420


def font(size):
    for f in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
              '/System/Library/Fonts/PingFang.ttc'):
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
        im = Image.open(p)
        im.load()
        return '完整'
    except Exception as e:
        m = re.search(r'truncated \((\d+) bytes', str(e))
        return '截断(缺%s字节)' % m.group(1) if m else '损坏'


def make_thumb(src, name, thumb_dir):
    os.makedirs(thumb_dir, exist_ok=True)
    try:
        im = Image.open(src)
        im = im.convert('RGBA') if im.mode in ('RGBA', 'P', 'LA') else im.convert('RGB')
        if im.mode == 'RGBA':
            bg = Image.new('RGB', im.size, (238, 238, 238))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
        im.save(os.path.join(thumb_dir, os.path.splitext(name)[0] + '.jpg'), 'JPEG', quality=84)
        return True
    except Exception as e:
        print('  缩略失败', name, e)
        return False


def overview(rows, title, out, thumb_dir):
    """把本轮新增拼成一张带文件名的总览图，方便回查。"""
    if not rows:
        return
    cols, cell, pad = 6, 210, 22
    W = cols * cell + pad * 2
    H = ((len(rows) + cols - 1) // cols) * (cell + 18) + pad * 2 + 54
    im = Image.new('RGB', (W, H), (24, 26, 30))
    d = ImageDraw.Draw(im)
    d.text((pad, pad), '%s · %d 张' % (title, len(rows)), fill=(120, 210, 255), font=font(20))
    for i, m in enumerate(rows):
        r, c = divmod(i, cols)
        x, y = pad + c * cell, pad + 54 + r * (cell + 18)
        th = os.path.join(thumb_dir, os.path.splitext(m['文件'])[0] + '.jpg')
        if os.path.exists(th):
            t = Image.open(th)
            t.thumbnail((cell - 10, cell - 10), Image.LANCZOS)
            im.paste(t, (x + (cell - t.width) // 2, y + (cell - t.height) // 2))
        d.rectangle([x, y, x + cell - 4, y + cell - 4], outline=(60, 64, 72))
        d.text((x + 4, y + cell - 2), m['文件'][:28], fill=(170, 180, 190), font=font(12))
    im.save(out, optimize=True)
    print('  总览图:', os.path.basename(out))


def read_fresh(stage):
    for name in ('_fresh.json', '_index.json'):
        p = os.path.join(stage, name)
        if os.path.isfile(p):
            return json.load(open(p, encoding='utf-8')), name
    raise SystemExit('找不到 _fresh.json / _index.json：' + stage)


def next_tag(rows):
    n = 1
    for m in rows:
        hit = re.match(r'^R(\d+)_', m.get('文件', ''))
        if hit:
            n = max(n, int(hit.group(1)))
    return 'R%d' % (n + 1)


def csv_header(archive):
    p = os.path.join(archive, '清单', '图片清单.csv')
    if not os.path.isfile(p):
        return DEFAULT_FIELDS
    with open(p, encoding='utf-8-sig', newline='') as f:
        first = next(csv.reader(f), None)
    return first or DEFAULT_FIELDS


def write_manifest(archive, rows, fields):
    d = os.path.join(archive, '清单')
    os.makedirs(d, exist_ok=True)
    json.dump(rows, open(os.path.join(d, '图片清单.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with open(os.path.join(d, '图片清单.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(fields)
        for m in rows:
            w.writerow([m.get(k, '') for k in fields])
    print('  清单:', len(rows), '条')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', required=True, help='已有档案仓库根目录（含 清单/图片清单.json）')
    ap.add_argument('--fresh', required=True, help='recover.py 本轮输出目录')
    ap.add_argument('--round', default='第2轮', help='写入清单的轮次名')
    ap.add_argument('--group', default='本轮新增/01_素材')
    ap.add_argument('--ui-list', default='', help='界面/过程截图的 1-based 编号，逗号分隔')
    ap.add_argument('--ui-group', default='本轮新增/02_界面与过程记录')
    ap.add_argument('--title', default='素材档案')
    ap.add_argument('--sections', help='gallery.py 用的分区顺序 JSON')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    archive = os.path.abspath(a.archive)
    stage = os.path.abspath(a.fresh)
    mjson = os.path.join(archive, '清单', '图片清单.json')
    old = json.load(open(mjson, encoding='utf-8'))
    have = {m['sha1'] for m in old}
    fresh, src_name = read_fresh(stage)
    ui = {int(x) for x in a.ui_list.split(',') if x.strip().isdigit()}

    # 编号按 fresh 原始顺序（与 triage.py 的核对图一致）
    dup, todo = [], []
    for i, r in enumerate(fresh, 1):
        (dup if r['sha1'] in have else todo).append((i, r))
    print('本轮 %s：%d 条；与档案重复 %d，真新增 %d / %.1f MB'
          % (src_name, len(fresh), len(dup), len(todo),
             sum(r['size'] for _, r in todo) / 1048576))
    if not todo:
        print('没有新增，结束。')
        return
    if a.dry_run:
        for i, r in todo[:5]:
            print('  %d %s %sx%s -> %s' % (i, r['file'], r['w'], r['h'],
                                           a.ui_group if i in ui else a.group))
        print('  ... dry-run，未落盘')
        return

    for m in old:
        m.setdefault('轮次', '第1轮')
        m.setdefault('路径', gallery.path_of(m))

    fields = csv_header(archive)
    for k in ('轮次', '路径'):
        if k not in fields:
            fields.append(k)

    tag = next_tag(old)
    thumb_dir = os.path.join(archive, '总览', 'thumb')
    added = []
    for i, r in todo:
        src = os.path.join(stage, r['file'])
        if not os.path.isfile(src):
            print('  跳过（缺原图）:', src)
            continue
        grp = a.ui_group if i in ui else a.group
        name = '%s_%03d_%s.%s' % (tag, i, r['file'], r['ext'])
        rel = grp.rstrip('/') + '/' + name
        dst = os.path.join(archive, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        make_thumb(dst, name, thumb_dir)
        added.append({
            '组': grp, '文件': name, '原缓存ID': r['file'],
            '宽': r['w'], '高': r['h'], '模式': r['mode'], '字节': r['size'],
            '绿占比': r.get('green', ''), 'sha1': r['sha1'],
            '完整性': integrity(dst), '来源': '元宝 App 缓存（本轮）',
            '归属': '本项目', '轮次': a.round, '路径': rel,
        })

    groups = {}
    for m in added:
        groups.setdefault(m['组'], []).append(m)
    for g, rows in groups.items():
        fn = '总览_%s.png' % g.replace('/', '_')
        overview(rows, g, os.path.join(archive, '总览', fn), thumb_dir)

    rows = old + added
    write_manifest(archive, rows, fields)
    gallery.build(archive, a.title, gallery.load_sections(a.sections))
    print('\n新增 %d 张 / %.1f MB；档案合计 %d 张 / %.1f MB'
          % (len(added), sum(m['字节'] for m in added) / 1048576,
             len(rows), sum(m['字节'] for m in rows) / 1048576))


if __name__ == '__main__':
    main()
