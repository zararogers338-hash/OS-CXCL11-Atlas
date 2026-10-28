# 数据集目录与核实流程

`config/config.yaml` 是唯一的事实来源，本文件说明怎样获取和核实这些数据。下表里的样本量是**预期值**，一律以下载后实际解析出来的数字为准。

## 目录

| ID | 类型 | 预期 n | 终点 | 角色 | 获取方式 |
|---|---|---|---|---|---|
| TARGET-OS | RNA-seq | ~88 | OS, EFS | 发现队列 | UCSC Xena GDC hub（`py/fetch_target.py`），候选文件名见脚本 |
| GSE21257 | Illumina 芯片 | 53 | OS, 无转移生存 | 验证 | GEO series matrix（`py/fetch_geo.py`） |
| GSE16091 | HG-U133A | 34 | OS | 验证 | 同上 |
| GSE39055 | WG-DASL | 37 | OS, 复发 | 验证 | 同上 |
| GSE42352 | Illumina 芯片 | ~84 例肿瘤 | 无转移生存 | 验证，含正常参照 | 同上；含细胞系和 MSC，需要按样本类型过滤 |
| GSE152048 | 10x scRNA | 11 | — | 单细胞图谱 | GEO 补充文件（较大，单独规则下载） |
| GSE162454 | 10x scRNA | 6 | — | 单细胞图谱 | 同上 |
| JHO 2024 OS 空间数据 | 空间转录组 | ? | — | 空间共定位 | 先确认是否公开、在哪里存放 |
| IMvigor210 | RNA-seq | ~348 | 响应, OS | ICB 迁移验证 | IMvigor210CoreBiologies 数据包 |
| GSE91061 | RNA-seq | ~109 | 响应 | ICB 迁移验证 | GEO |
| GSE78220 | RNA-seq | ~28 | 响应 | ICB 迁移验证 | GEO |
| PRJEB23709 | RNA-seq | ~91 | 响应 | ICB 迁移验证 | ENA（原始 reads；优先使用已发表的处理后矩阵） |
| DepMap | 细胞系 | — | 依赖性 | 机制旁证 | DepMap portal 的发布文件 |
| GDSC2 | 药敏 | — | IC50 | oncoPredict 训练集 | oncoPredict 自带或 GDSC 官网 |
| TCGA-SARC | RNA-seq | ~260 | OS | 泛肉瘤敏感性分析 | Xena |

ICB 队列都**不是骨肉瘤**，只能作为间接证据。

## 核实流程（每个队列都要走一遍）

1. 下载后用脚本解析，不要看着网页手抄数字。
2. 记录以下内容：实际样本数；按样本类型（肿瘤、细胞系、正常组织）过滤后的样本数；平台；表达值的尺度（是否已经 log 过：最大值大于 50 一般说明还没 log）；生存时间的单位和事件编码；缺失情况。
3. 写数据卡片 `docs/data_cards/<ID>.md`，格式见下方模板。
4. 把 `config.yaml` 里该队列的 `verified` 改成 `true`，同时修正 `n_expected`。
5. 如果和文献报道的样本量不一致，在卡片里说明原因，例如重复样本或缺少随访。

## 数据卡片模板

```markdown
# <ID>
- 来源 / 下载日期 / 文件与 sha256：
- 平台与注释（GPL、探针到基因的映射规则）：
- 样本：原始 n → 过滤后 n（过滤规则）
- 表达尺度与处理：
- 临床变量（字段名 → 标准名）：
- 终点：时间单位、事件编码、中位随访时间、事件数
- 已知问题与处理：
- 在本研究中的角色：
```

## 标准化的临床字段名

`sample_id, patient_id, age, sex, site, metastasis_dx, histologic_response, os_time_months, os_event, efs_time_months, efs_event, mfs_time_months, mfs_event, cohort`。时间统一换算成月，事件统一编码为 1/0。
