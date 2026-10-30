# 维护手册

需要 Python 3.10+，无第三方依赖。以下命令在资源仓库根目录运行。

## 1. 采集和浏览

```sh
python3 scripts/resources.py intake --roms /path/to/roms --collection /path/to/collection
```

来源目录只读，脚本不执行来源中的程序。明确识别的资源按 SHA-256 复制、去重保存于 Git 忽略的 `.local/objects/`。来源路径及未授权条目只记录在 `.local/`，不要提交。

从 `.local/REVIEW.md` 打开类型索引，或从 `.local/inventory.json` 逐层进入：

```text
.local/inventory/<类型>/<机型或运行环境>/
├── index.json
├── pages/0001.json       每页至多25个引用
└── entries/<候选ID>.json  单条明细及来源、文件摘要
```

`.local/summary.json` 是统计；`.local/skipped.json` 引用按来源拆分的跳过记录，每页最多 25 条。`.local/sources.json` 可保存操作人员自己的来源配置，不公开。

运行环境明确但机型不明的 BAS/LAV 可分别归入 gvbasic/lava，不得自动批准给所有机型。无明确目录分类线索的 BIN 等资源跳过。内核按 CLASSIFICATION.md 中的映射识别，所有 `.nand0` 均不采集。

重采集会重建当前清单及其分片，但保留已有对象。新增批次前先备份 `.local`；脚本不是自动增量合并器。旧对象不再被新清单引用时不会导出，也不会自动删除。初次扁平清单的分类快照保存在 `.local/archive/`，仅供追溯，不是有效目录。

## 2. 逐条审核

依次核实机型、版本、用途、依赖、导入方式及兼容性，然后核实作者、许可证和允许公开再分发的授权范围。NOR/NAND 必须检查是否含个人信息。作者署名和机型分类不能代替授权。

可公开授权说明放入 `licenses/evidence/`，敏感原件只放 `.local/`。每个条目在 `review/entries/<type>/<id>.json` 保存一个独立审批对象，不将所有记录合并成大数组。字段模板：

```json
{
  "status": "approved",
  "candidateId": "candidate-替换为候选ID",
  "id": "example-tool",
  "title": "已获授权的示例工具",
  "version": "1.0.0",
  "description": "资源简介",
  "logo": "previews/example/logo.webp",
  "screenshots": ["previews/example/screen-1.webp"],
  "author": "真实作者",
  "license": "真实许可证或明确再分发授权名称",
  "evidence": "licenses/evidence/example-tool.md",
  "models": ["nc1020"],
  "compatibilityNotes": "填写确认的固件、依赖及验证方式",
  "usage": "填写实际导入和启动步骤",
  "files": [{
    "sha256": "替换为候选文件的64位摘要",
    "path": "releases/download/resources-current/example.bin"
  }]
}
```

不要直接使用占位模板批准资源。机型列表仅能填写当前应用支持并已确认适用的型号。多文件包列入全部必要文件；审批可以选择候选中的部分文件，但不能从无关候选拼接未知固件。工具不能验证授权的法律效力或实际兼容性。

## 3. 校验和导出

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/resources.py build
python3 scripts/resources.py build --export
```

build 校验显式审批并生成分层公开目录；export 额外生成 `dist/` 中的同结构目录和 `dist/payloads/<相对路径>` 下的批准附件，不联网、不上传。已有 dist 时拒绝覆盖，先核对并移走旧目录，避免残留撤回资源。

人工检查公开文档、审批、目录及授权证据不含本机绝对路径、私人信息；核实每个下载地址、附件摘要和许可一致。测试使用合成文件，不执行采集程序。

## 4. 发布

先补充私密版权联系渠道，再人工创建独立 GitHub 仓库并设置 remote。仓库通常提交文档、工具、分片目录和审核记录；经明确审核的资源二进制可放 assets/ 或 Release 附件；优先通过 Release 分发。原始未授权对象仍不可提交。

1. 确认资源库远端为 `https://github.com/xtulnx/wqx-resources`，补齐授权审核。检查 `git diff --cached` 和 `git ls-files`，不提交 `.local/`、dist 或个人信息，不使用强制添加。只有明确审核过的文件才手动放入 assets/（已设置 Git 忽略例外）。
2. 将 dist/payloads/releases/download/<tag>/ 下的附件以对应文件名上传指定 Release；assets/ 文件须人工核对后按相对目录放置，不要强制提交未经授权的文件。Logo/截图按 previews/ 相对路径维护，推荐 WebP。
3. 发布附件并核实大小和摘要，再提交完整目录树及入口，避免引用尚不可用资源。
4. 允许同版本、同路径覆盖更新；每次替换须同步更新大小和摘要，先完成附件替换再更新目录。资源更新不绑定 APK 版本。

不提供自动上传工作流，避免未经审核的资源被发布。GitHub 公开文档只描述目录、分类、许可和使用方式，不写操作人员机器路径、采集批次统计或临时环境状态。

## 5. 撤回和清理

将条目审批改为 withdrawn 后重新 build；同时检查并移除争议 Release 附件及其他公开副本。生成工具会替换生成的目录分片，避免旧资源条目留在有效目录树中；应将分片删除一并提交。

目录隐藏不等于撤销历史下载。误上传敏感文件需按平台流程处理，必要时清理历史。不得删除使用者自己的设备数据或存档。

旧本地对象及归档不会发布，可核对来源备份和有效清单引用后手动清理；不要直接清空尚有保密授权证据的目录。

## 更新与图片维护

简介、Logo、截图为可选字段。图片也需核实授权，仓库目录和审批均使用相对路径。覆盖附件不要求提升版本文字；客户端按 SHA-256 识别更新，失败不会用未校验文件替换旧下载。公共加速线路可能短暂缓存旧目录或附件，出现校验失败先切换直连并刷新。

## 当前历史资源发布决定

维护者于2026-10-30明确决定先行公开当前候选，包括ROM/NOR/NAND。逐条记录使用 `maintainer-published-unverified`、`rightsStatus: unverified` 和 publicationDecision；这不是已获授权的 approved 审核，不能混淆。免责声明引用仅解释发布决定，不是作者许可证明。未知机型保留空 models，仅在全部机型视图列出，不臆测全机型兼容；已识别但当前应用不支持的型号也保持原标注。

收到可信投诉后先暂停下载，再核实和移除。撤回条目、附件及历史可访问副本都要检查，不得只修改声明。

## 上传当前导出附件

先提交并推送 main 分支，再执行 `python3 scripts/publish_release.py`。脚本使用本机 Git HTTPS 凭据或 GH_TOKEN/GITHUB_TOKEN，不在文件或输出中记录令牌；请勿把令牌发到聊天。它校验导出摘要，以最多两个并发上传到 resources-current Release，支持失败后重试并跳过已有同名同大小附件。新建 Release 在附件全部上传完成前保持草稿。全部完成前安卓端可能无法下载，不能把仅推送目录视为发布成功。不会自动删除旧附件；版权撤回需同时处理目录、附件和历史副本。
