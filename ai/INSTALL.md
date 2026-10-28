# OS-CXCL11 Atlas 0.4.0 — 安装 / Installation

本套件包含中英文研究技能、六个专家包、可执行治理与研究任务计划，以及经过筛选的项目源码。它用于公共数据科研协作；B/C/D 轨道、汇合模型和图谱仍需按计划实现。工程升级不等于研究完成。

This kit contains the bilingual skill, six specialists, portable governance and task-planning scripts, and allowlisted project source. Planned research tracks are not yet a completed paper. Choose one language (`zh` or `en`).

## 1. 先验证 / Verify first

解压 `OS-CXCL11-OpenScience-Kit-0.4.0.zip`，在解压目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_kit.ps1 -VerifyOnly
```

清单会核对文件大小与 SHA-256，并检查 ZIP 内容路径。失败时停止，重新取得正确包或从经过检查的源码重建。不要删除校验步骤。包内清单不等于外部数字签名。

Verification checks file sizes, hashes and archive paths before mutation. A failure stops installation. An embedded manifest is an integrity check, not an independent publisher signature.

## 2. 安装技能 / Install the skill

双击 `install.cmd` 使用中文；或明确指定语言和已有项目目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_kit.ps1 -Lang zh -RepoRoot C:\path\OS-CXCL11-Atlas
```

如果尚未安装 Open-Science，脚本使用随附的官方安装程序，并验证其 Authenticode 签名。使用已有安装时可用 `-AppPath` 指定。技能升级会保留备份，失败时回退。请保留旧版 ZIP 和研究数据。

If Open-Science is absent, the script verifies and runs the bundled vendor installer. `-AppPath` selects an existing installation. Skill replacement is staged and keeps a backup for recovery.

已有研究仓库优先继续使用原目录。未指定 `-RepoRoot` 时只安装技能并提示后续配置。随包的 `project/` 是需要保持原样的源码快照：先复制到套件目录之外再开展研究、安装依赖或修改配置。随后用 `setup_openscience.ps1 -RepoRoot <复制后的目录>` 配置工作台。`project/` 提供公开源码起点，不包含下载数据、私有记录、稿件、本地环境或既有研究结果。Python、R 及其依赖仍按项目 README 安装；套件不附带完整科研环境。治理与计划脚本只依赖 Python 标准库。

Without `-RepoRoot`, only the skill is installed. Copy `project/` outside the immutable kit before research or dependency installation, then run `setup_openscience.ps1 -RepoRoot <working-copy>`. Continue in the existing repository when available. The `project/` source snapshot contains no private notes, manuscripts, data, local environment or existing research results. Restore research dependencies using its README. Governance and planning require only Python's standard library.

## 3. 专家和模型 / Specialists and model

在 Open-Science 的 Specialists → Import 中，从 `packages/zh/`（或 `packages/en/`）逐个导入六个专家 ZIP：

| ID | 职责 / Role |
|---|---|
| research-steward | 研究调度、任务与证据交接 / Research planning |
| bioinfo-analyst | 分析实现与数字登记 / Analysis |
| figure-artist | 图表与视觉验收 / Figures |
| manuscript-writer | 可追溯稿件 / Writing |
| reviewer-2 | 独立科学审查 / Scientific review |
| reproducibility-auditor | 独立复现与工程审计 / Reproducibility review |

选择一个模型提供商并在应用设置中填写自己的凭据，运行连接测试。不要把凭据放进项目、命令、聊天、报告或安装包。模型名称按提供商当前支持的列表选择。

Import the six specialist ZIPs in the app. Configure your provider and credentials only in app settings, then run its connection test. No real model session is implied by an offline package test.

## 4. 项目配置与最小权限 / Project setup

默认不新增连接器；已有项目上下文和会话默认值保留。需要变更时显式传入 `-EnableConnector`、`-UpdateProjectContext` 或 `-ApplySessionDefaults`。先检查脚本 `Get-Help` 与当前应用能力，再按实际需要配置。

Default setup enables no additional connectors and preserves existing project context/session defaults. Use the explicit switches only when intended. Role names in this kit describe responsibilities; they do not sandbox the application's tools.

## 5. 启动治理 / Start governance

在项目根目录执行：

```bash
python py/governance.py --root . status --json
python py/research_plan.py --root . --lang zh
python ai/skills/cxcl11-osteosarcoma-tme/scripts/stage_status.py --lang zh
```

历史决策记录保留为背景，不自动批准新版门控。按技能的 `references/governance.md` 提交现有证据并独立复核。哈希证明字节一致，不证明科学结论或身份真实性。

Historical decisions remain context. Establish reviewed evidence under the protocol in `references/governance.md`; do not convert old notes into approvals automatically.

## 6. 隔离验收 / Isolated acceptance

下面只在指定测试目录安装技能，不启动或配置真实应用：

```powershell
powershell -ExecutionPolicy Bypass -File .\install_kit.ps1 -OfflineProfileRoot C:\temporary\cxcl11-test-profile -Lang zh
```

在源码目录运行 Python 测试：

```bash
python -m pytest tests -q
```

离线测试不代表全新电脑应用安装通过，也不代表真实模型能遵循提示词。应分别记录运行的测试、结果与未测项。安装后的专家导入和模型配置仍需在软件中完成。

Offline tests do not certify fresh-machine application installation or actual model behavior. Record each validation scope separately.

## 构建 / Build

```bash
python py/build_ai_layer.py kit
python py/build_ai_layer.py all
```

AI 源码位于 `ai/`；生成的工具副本不手改。代码为 MIT，随附应用安装程序采用其第三方许可。私有研究证据不得进入公开发布包。更多说明见 `docs/ARCHITECTURE.md` 与 `docs/RELEASE-0.4.0.md`。
