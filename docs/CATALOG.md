# 分层目录协议 v2

## 分层读取

目录入口是 `catalog.json`，依次引用类型、机型／运行环境、分页和资源说明。每页最多 25 个引用，单个资源独立文件；单分组最多 25 页，超出后细分。

```text
catalog.json
catalog/<type>/index.json
catalog/<type>/<group>/index.json
catalog/<type>/<group>/pages/0001.json
catalog/<type>/<group>/entries/<resource-id>.json
```

各级使用 `schemaVersion: 2`；根为 `categories`，类型索引为 `groups`，分组索引为 `pages`，页为 `resources`。引用包含 `path`；资源引用另含 `id`。客户端按需读取并缓存分片。

## 相对路径

所有路径均相对于资源仓库根目录，不相对于当前分片。目录、授权说明、Logo 和截图均采用相对路径，不写死域名或机器路径。

文件附件使用 `path`，不使用绝对 `url`：

- `assets/bin/example.bin`：仓库中的资源文件。
- `releases/download/resources-current/example.bin`：仓库对应的 Release 附件。
- `previews/example/logo.webp`：图片。

客户端下载仓库文件时使用配置的 Raw 根地址；以 `releases/download/` 开头时使用仓库根 URL，避免将 Release URL 错当成 Raw 文件。禁止绝对路径、`..`、反斜杠、URL 协议、百分号编码及查询参数。

## 资源说明

```json
{
  "id": "example-tool",
  "title": "示例工具",
  "version": "1.0",
  "type": "bin",
  "models": ["nc1020"],
  "description": "资源简介，可说明用途和特性。",
  "logo": "previews/example/logo.webp",
  "screenshots": ["previews/example/screen-1.webp"],
  "author": "作者",
  "license": "实际许可证",
  "evidence": "licenses/evidence/example.md",
  "compatibilityNotes": "适用固件和依赖",
  "usage": "导入和启动步骤",
  "files": [{
    "name": "example.bin",
    "role": "bin",
    "bytes": 1234,
    "sha256": "填写实际64位摘要",
    "path": "releases/download/resources-current/example.bin"
  }]
}
```

`description`、`logo`、`screenshots` 可省略，最多 8 张截图；推荐 WebP，图片也必须有合法来源。`models` 为明确支持机型；NC2000/NC2600 可分别标注，客户端视为同一个模拟器机型。`role` 支持 rom/nor/nand/bin/bas/lav，`.nand0` 临时文件不发布。

## 覆盖更新与移除

允许同一资源、同一版本、同一路径覆盖内容。每次覆盖须同时更新文件大小与 SHA-256；客户端以内容摘要识别更新，不仅比较版本文字。校验失败时应刷新目录后重试，不降低校验要求。

移除资源时同步删除审批或标记 withdrawn，重建并提交分片删除；按需要移除附件和图片。版权撤回需要检查历史可访问副本，不能只删除入口引用。

下载前验证路径，下载后验证长度和摘要。新内容完整下载成功后再替换下载副本；不得自动覆盖设备的可写固件、模拟器内部文件和存档。服务器移除资源不意味着可以擅自删除用户已有数据。

SHA-256 是完整性校验，不是来源签名。公共加速线路可能缓存旧内容；线路失效应允许切换直连或其他线路。
