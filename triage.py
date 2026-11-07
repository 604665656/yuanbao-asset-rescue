# -*- coding: utf-8 -*-
"""出逐格审查图：6 列 × 6 行，每格带大编号（= build_archive 里的重新编号）。

用途：recover + build_archive 跑一遍后，缓存里混进来的「别的对话的图」需要人工
挑出来。本脚本把每个桶的图铺成带编号的审查图，逐张目视，把不属于本项目的
编号记下来，填进 build_archive.py 的 EXCLUDE，再重跑 build_archive 即可。

用法：
    python build_archive.py            # 先生成 清单/ 和 总览/thumb/
    python triage.py                   # 读清单，出审查图到 _triage/
"""
import json
import os

from PIL import Image, ImageDraw, ImageFile, ImageFont

ImageFile.LOAD_TRUNCATED_IMAGES = True

COLS, ROWS, CELL = 6, 6, 262
PER = COLS * ROWS


def font(size):
    for f in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/arialbd.ttf'):
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()


def sheet(items, title, dst):
    rows = (len(items) + COLS - 1) // COLS
    W, H = COLS * CELL + 16, rows * (CELL + 16) + 50
    im = Image.new('RGB', (W, H), (18, 19, 22))
    d = ImageDraw.Draw(im)
    d.text((10, 12), title, fill=(120, 210, 255), font=font(20))
    for i, (num, path) in enumerate(items):
        r, c = divmod(i, COLS)
        x, y = 8 + c * CELL, 44 + r * (CELL + 16)
        try:
            t = Image.open(path).convert('RGB')
            t.thumbnail((CELL - 6, CELL - 6), Image.LANCZOS)
            im.paste(t, (x + (CELL - t.width) // 2, y + (CELL - t.height) // 2))
        except Exception:
            pass
        d.rectangle([x, y, x + CELL, y + CELL], outline=(58, 62, 70))
        d.rectangle([x, y, x + 30, y + 18], fill=(0, 0, 0))
        d.text((x + 4, y + 1), str(num), fill=(255, 220, 60), font=font(15))
    im.save(dst, optimize=True)
    print(' ', os.path.basename(dst), '%dx%d' % (W, H), len(items), '格')


def main():
    root = os.path.abspath('.')
    m = json.load(open(os.path.join(root, '清单', '图片清单.json'), encoding='utf-8'))
    out = os.path.join(root, '_triage')
    os.makedirs(out, exist_ok=True)
    for grp in ('绿幕与白模', '生成稿_1328x1776', '大幅', '其他'):
        items = [x for x in m if x['组'] == grp and x['归属'] == '本项目']
        for page in range(0, len(items), PER):
            chunk = items[page:page + PER]
            lst = []
            for x in chunk:
                n = int(x['文件'].split('_')[0])
                p = os.path.join(root, '总览', 'thumb', os.path.splitext(x['文件'])[0] + '.jpg')
                if not os.path.exists(p):
                    p = os.path.join(root, '元宝缓存', grp, x['文件'])
                lst.append((n, p))
            sheet(lst, '%s 第 %d 页' % (grp, page // PER + 1),
                  os.path.join(out, '%s_%d.png' % (grp[:2], page // PER + 1)))


if __name__ == '__main__':
    main()
