# 许可证原文与文件清单

本目录保留许可证和归属说明原文，不对原文进行中文改写。收集时间为 2026-10-04。依赖概览见 [依赖说明](../DEPENDENCIES.md)。

当前收集 285 个文件，共 1,143,238 字节。逐文件来源、长度与 SHA-256 见 [JSON 清单](manifest.json) 和 [CSV 清单](FILES.csv)。

## 文件来源

- `installed:` 来源是当前虚拟环境中安装包随附的文件；保留包名和版本目录，包括安装工具内嵌依赖的许可证。
- `supplement: true` 是从 Qt 官方代码站 `v6.11.2` 获取的补充文件，清单给出精确 URL。当前 PySide6 安装包只附商业许可引用，未附完整 LGPL/GPL 文本。
- Qt 补充范围包括 Qt Base、PySide 的 `LICENSES`，以及 Qt Base 第三方目录中两层内的许可/归属说明。部分文件对应其他平台或未被应用使用的组件，它们属于参考集合，不是最终 EXE 的组件鉴定结果。
- 少量原文同时保留在简化路径与完整包路径中，清单标记 `duplicate_copy: true`；它们的内容哈希相同。

## Qt 许可入口

- [LGPL 3 原文](Qt-qtbase-6.11.2/LICENSES/LGPL-3.0-only.txt)
- [GPL 2 原文](Qt-qtbase-6.11.2/LICENSES/GPL-2.0-only.txt)
- [GPL 3 原文](Qt-qtbase-6.11.2/LICENSES/GPL-3.0-only.txt)
- [Qt GPL 许可例外](Qt-qtbase-6.11.2/LICENSES/Qt-GPL-exception-1.0.txt)

## 按包统计

| 安装包或官方源码仓库 | 文本/归属文件数 |
|---|---|
| aioquic | 2 |
| altgraph | 2 |
| anyio | 2 |
| asyncssh | 2 |
| attrs | 2 |
| certifi | 1 |
| cffi | 2 |
| colorama | 2 |
| cryptography | 6 |
| dnspython | 2 |
| h11 | 2 |
| h2 | 2 |
| hpack | 1 |
| httpcore | 2 |
| httpx | 2 |
| hyperframe | 3 |
| idna | 2 |
| iniconfig | 2 |
| packaging | 3 |
| pefile | 2 |
| pip | 37 |
| pluggy | 2 |
| psutil | 2 |
| pycparser | 2 |
| Pygments | 5 |
| pyinstaller | 2 |
| pyinstaller-hooks-contrib | 2 |
| pylsqpack | 2 |
| pyOpenSSL | 2 |
| pyside/pyside-setup.git | 8 |
| PySide6 | 1 |
| PySide6_Addons | 1 |
| PySide6_Essentials | 1 |
| pytest | 2 |
| pywin32-ctypes | 2 |
| qt/qtbase.git | 127 |
| scapy | 2 |
| service-identity | 2 |
| setuptools | 30 |
| shiboken6 | 5 |
| typing_extensions | 2 |
| websockets | 2 |

## 核验与后续分发

所有已登记文件均重新读取并校验哈希。未复制大体积 licenseheaders、源代码树或二进制库。原文和参考集合只能帮助识别许可，不能证明已经完成整个发行包的许可兼容性、源代码提供义务或 Qt 第三方归属审查。当前只进行了本地构建与验证，没有公开上传。未来公开分发仍需用户按实际打包清单审查。
