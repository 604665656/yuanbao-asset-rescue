# yuanbao-cache-recover

从**元宝 App** 的本地缓存里把对话中渲染过的图片全部抢救出来，整理成带清单和图廊的素材档案。

> 元宝没有「导出全部图片」的入口。对话聊多了，图要么没点过下载，要么散在各处。
> 但这些图其实都留在客户端缓存里——只要没清缓存、没重装，就还能捞回来。

本仓库是一套**通用工具 + 经验沉淀**，第一次是为了抢救「哈士喵（眼镜猫）」项目在元宝里十几轮对话的产出，之后任何元宝对话想留底都能复用。

[![路线图](https://img.shields.io/badge/路线图-Project-5cc8ff)](https://github.com/users/604665656/projects/11)
[![示例档案](https://img.shields.io/badge/示例-真实抢救成果-ffb454)](https://604665656.github.io/hashimiao-asset-archive/)

---

## 工具链

| 脚本 | 作用 |
|---|---|
| `recover.py` | 扫描元宝 `Cache_Data` → 按 magic byte 识别图片 → sha1 去重 → 绿占比/尺寸粗分桶 → 输出 `_yb_stage/_index.json` |
| `build_archive.py` | 读 `_index.json` → 分组编号 → 清单(CSV/JSON) → 缩略图 → 分组总览图 → 根目录 `index.html` 图廊 |
| `triage.py` | 出逐格审查图（带编号），用于人工挑出「不属于本项目」的图 |
| `push.py` | 大仓库分批提交+推送（代理不稳时），每批推完比对 sha |

依赖：`pip install pillow`。只跑工具不需要别的。

---

## 快速开始

```bash
# 1) 提取（自动探测元宝缓存路径；也可 --cache 指定）
python recover.py

# 2) 第一次整理（EXCLUDE 留空，先把所有图铺出来）
python build_archive.py --title "我的素材档案"

# 3) 出审查图，逐张目视，把不属于本项目的编号记下来
python triage.py
#   打开 _triage/ 下的图，记录要剔除的编号

# 4) 把编号填进 build_archive.py 的 EXCLUDE，重跑
#    EXCLUDE = {'大幅': [1,2,3,...], '其他': [1,2,...]}
python build_archive.py --title "我的素材档案"

# 5) 推送（可选：开 GitHub Pages 当在线图廊，记得仓库根放 .nojekyll）
set GH_TOKEN=你的token
python push.py --owner 你的名 --repo 仓库名 --desc "..."
```

---

## 踩过的坑（这是本仓库最值钱的部分）

### 1. 缓存是**整个 App 共用**的，不是按对话分目录

元宝是 WebView2 套壳，所有对话的图都在同一个 `Cache_Data` 里，没有「这是哪个对话」的维度。
提取脚本只能按 magic 认图片类型，没法按对话分。

**结论**：全捞出来后**必须人工分拣**。本项目第一次就混进了 68 张别的对话的图
（国徽、校徽、GitHub logo、钢琴、走势图、别的游戏截图……）。处理办法：把不属于本项目的
编号写进 `EXCLUDE`，脚本**只挪位不改号**（挪到 `其他对话/`），清单里标「其他对话」，可回查。
**千万别用删除**——编号会移位、清单对不上、以后想找也找不回。

### 2. 对话**正文**救不回来

缓存里 48 个条目命中项目关键词，但解开 gzip 后全是项目自己的 HTML 文档，不是聊天记录。
`Local Storage` / `Session Storage` / `IndexedDB` 搜关键词命中 0。

**根因**：元宝对话走流式响应，不写进磁盘缓存，正文只在服务端。
要留对话正文，只能在 App 里手动分享/导出。

### 3. 缓存里的 JPG 可能是**截断**的

7 条记录尾部缺 13~54 字节，Pillow 默认直接抛 `image file is truncated`。
不处理会静默丢图。

**修法**：`ImageFile.LOAD_TRUNCATED_IMAGES = True`。画面其实完整，只是缺了文件尾。

### 4. GitHub Pages 构建失败 → 加 `.nojekyll`

纯静态画廊不需要 Jekyll，但 Pages 默认用 Jekyll 处理，多批次推送的中间态会构建失败，
状态卡在 `errored`，页面一直服务上一次成功的旧版（看起来像「没更新」）。

**修法**：仓库根放空文件 `.nojekyll`，禁用 Jekyll，让 Pages 直接当静态文件服务。
这也是静态站点的标准做法。

### 5. 本地代理会**截断大响应**

`curl` 取页面时停在 32768 字节（恰好 32KB），误以为页面只生成一半。实际 GitHub 端完整。

**修法**：验证大文件别用 `curl` 看 body，用 API 取 blob 才是真值
（`GET /repos/{o}/{r}/git/blobs/{sha}` 拿 base64，再 decode 看长度）。

### 6. 大仓库推送：分批 + sha 校验 + 重试

代理长连接不稳，单次大推送必挂。按 18MB 左右切片，每批提交后比对本地 HEAD 与远端 sha，
不一致就重试。`http.version=HTTP/1.1` + `pack.threads=1` 能降单连接压力。

### 7. GitHub API 两个静默坑

- `PATCH /repos/{o}/{r}` 带 `topics` 会被**静默忽略**（返回 200 但没生效）。
  必须走 `PUT /repos/{o}/{r}/topics`，body `{"names":[...]}`。
- `PUT /topics` 是**覆盖**语义，会冲掉原有值。设置类接口一律先 GET 现值再并集。

---

## 经验复用清单（下次直接照做）

1. 先 `recover.py` 全捞（缓存不去重前可能几百张，正常）。
2. 看 `recover.py` 输出的桶分布，判断有没有混入别的对话的图。
3. `build_archive.py` 铺第一版 → `triage.py` 出审查图 → 目视填 `EXCLUDE` → 重跑。
4. 推送前确认仓库根有 `.nojekyll`（要开 Pages 的话）。
5. 推送用 `push.py`，别一次性推。
6. 验证线上用 API 取 blob，别用 `curl`（代理截断）。

---

## 许可

MIT。工具随便用；抢救出来的图片版权归原对话/原作者，本仓库不对图片内容负责。
