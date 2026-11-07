# -*- coding: utf-8 -*-
"""从元宝 App 的 WebView2 缓存里抢救图片（通用工具，不绑定具体项目）。

元宝是 WebView2 套壳，对话里渲染过的图会留在本地缓存：
    %LOCALAPPDATA%\\com.tencent.yuanbao\\EBWebView\\Default\\Cache\\Cache_Data
（Linux/mac 上路径不同；也可用 --cache 直接指定。）

缓存里的文件没有扩展名，靠「magic byte」识别图片类型；同一张图会存
多份，靠 sha1 去重。再按「绿占比 + 尺寸」粗分桶，方便人工分拣。

输出：<out>/_index.json —— 唯一图的清单（含尺寸、绿占比、桶、sha1）。

用法：
    python recover.py
    python recover.py --cache "D:/cache/Cache_Data" --out my_stage
"""
import argparse
import hashlib
import json
import os
import shutil

from PIL import Image

# 缓存里有记录尾部被截断（缺十几到几十字节），画面其实完整，允许读入
Image.MAX_IMAGE_PIXELS = None  # 防止超大图触发 DecompressionBomb 警告
try:
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except Exception:
    pass


def default_cache():
    local = os.environ.get('LOCALAPPDATA')
    if local:
        p = os.path.join(local, 'com.tencent.yuanbao', 'EBWebView',
                         'Default', 'Cache', 'Cache_Data')
        if os.path.isdir(p):
            return p
    return None


def magic_ext(head):
    """前 16 字节判图片类型，返回扩展名或 None。"""
    if head[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if head[:2] == b'\xff\xd8':
        return 'jpg'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    if head[:3] == b'GIF':
        return 'gif'
    return None


def classify(im, size):
    """返回 (宽, 高, 模式, 绿占比, 桶)。"""
    w, h = im.size
    mode = im.mode
    green = 0.0
    bucket = '其他'
    try:
        rgb = im.convert('RGB')
        sm = rgb.resize((64, 64))
        px = list(sm.getdata())
        g = sum(1 for (r, g_, b) in px if g_ > r + 30 and g_ > b + 30)
        green = round(g / len(px), 3)
        if green > 0.35:
            bucket = '绿幕与白模'
        elif (w, h) == (1328, 1776) or (w, h) == (1776, 1328):
            bucket = '生成稿_1328x1776'
        elif w >= 1000 and h >= 600:
            bucket = '大幅'
        else:
            bucket = '其他'
    except Exception:
        pass
    return w, h, mode, green, bucket


def extract(cache_dir, out_dir):
    if not os.path.isdir(cache_dir):
        raise SystemExit('缓存目录不存在: %s' % cache_dir)
    os.makedirs(out_dir, exist_ok=True)
    rows, seen = [], {}
    raw = skipped = 0
    for name in sorted(os.listdir(cache_dir)):
        p = os.path.join(cache_dir, name)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, 'rb') as f:
                head = f.read(16)
        except Exception:
            continue
        ext = magic_ext(head)
        if not ext:
            skipped += 1
            continue
        data = open(p, 'rb').read()
        sha = hashlib.sha1(data).hexdigest()
        raw += 1
        if sha in seen:  # 同一张图缓存多份 -> 去重
            rows.append({'file': name, 'ext': ext, 'size': len(data),
                         'sha1': sha, 'dup_of': seen[sha], 'bucket': '重复'})
            continue
        seen[sha] = name
        rec = {'file': name, 'ext': ext, 'size': len(data), 'sha1': sha}
        # 把唯一图（及首遇的重复图）落到 stage 目录，供 build_archive 读取
        shutil.copy2(p, os.path.join(out_dir, name))
        try:
            im = Image.open(p)
            w, h, mode, green, bucket = classify(im, len(data))
            rec.update({'w': w, 'h': h, 'mode': mode,
                        'green': green, 'bucket': bucket})
        except Exception:
            rec.update({'w': 0, 'h': 0, 'mode': '?',
                        'green': -1, 'bucket': '其他'})
        rows.append(rec)

    uniq = [r for r in rows if r.get('bucket') != '重复']
    dups = len(rows) - len(uniq)
    json.dump(rows, open(os.path.join(out_dir, '_index.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('原始图片条目: %d（非图片跳过 %d）' % (raw, skipped))
    print('去重: 唯一 %d 张，重复 %d 张' % (len(uniq), dups))
    from collections import Counter
    for k, v in Counter(r['bucket'] for r in uniq).most_common():
        print('  桶 %-16s %d' % (k, v))
    print('清单: %s' % os.path.join(out_dir, '_index.json'))
    return uniq


def main():
    ap = argparse.ArgumentParser(description='从元宝缓存抢救图片')
    ap.add_argument('--cache', default=default_cache(),
                    help='Cache_Data 目录（默认自动探测元宝路径）')
    ap.add_argument('--out', default='_yb_stage', help='输出目录（默认 _yb_stage）')
    args = ap.parse_args()
    if not args.cache:
        raise SystemExit('没找到元宝缓存，请用 --cache 指定 Cache_Data 路径')
    extract(args.cache, args.out)


if __name__ == '__main__':
    main()
