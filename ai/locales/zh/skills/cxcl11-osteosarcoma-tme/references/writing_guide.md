# 写作指南

## 数字的写法
- 正文、摘要和图注里的统计量一律写成 `{{stat:key}}`；需要同时给出 95% CI 时写 `{{stat:key|ci}}`。
- 样本量、事件数这类数字也要从统计片段里登记，不要手写。
- 渲染之前先运行 `python py/audit_claims.py manuscript/*.md`，结果必须是零问题。
- 基因名、试剂版本等不属于统计量的数字（例如 IL-2、GPL96）所在的行，可以加注释 `<!-- audit:allow -->`。

## 结构（IMRaD）
**标题**：写清疾病、轴、核心发现和工具，例如 "Compartmental CXCL11–CXCR3/ACKR3 signalling in osteosarcoma: multi-cohort analysis and an interactive atlas" (hypothetical)。最终标题要等结果出来后再定，结果不支持的内容不能写进标题。

**摘要**（结构化，约 250 词）：Background → Methods（队列、样本量、方法）→ Results（3–4 个关键数字）→ Conclusions（结论措辞要和证据强度匹配）。

**引言**（4 段）：
1. 骨肉瘤现状，以及免疫治疗在骨肉瘤中的失败。
2. CXCR3 配体在招募 T 细胞中的作用。
3. CXCL11 的特殊性：它是唯一同时结合 ACKR3 的 CXCR3 配体，而 ACKR3 在骨肉瘤血管中表达。
4. 研究空白和本研究的目标。

**方法**：
- 数据来源（附各数据卡片的要点）
- 预处理
- 各轨道的分析方法
- ML 模型（逐条对应 TRIPOD+AI）
- 统计方法
- 代码可用性
- AI 使用声明

**结果**：按 8 张图的顺序写，每段先说要回答的问题，再说结果，最后一句点明意义。

**讨论**：
- 主要发现
- 和既往研究的对比，要引用 CXCR3 骨肉瘤 2019 和 CXCL10–CXCR3 双重作用两篇
- 机制推测（明确标为推测）
- 临床意义
- 局限性（见下方必写清单）
- 结论

## 局限性部分必须写到的内容
- 全部使用公共数据，没有湿实验验证；结论属于相关性证据，不能证明因果。
- ICB 队列不是骨肉瘤患者，迁移验证只是间接证据。
- 队列样本量小，平台不同，存在批次异质性。
- 单细胞数据中 CXCL11 很稀疏，检出受技术限制。
- 回顾性数据，可能有选择偏倚。

## 核对清单
**TRIPOD+AI（预后模型）**：
- 数据来源与参与者
- 结局的定义与时间点
- 预测变量的处理
- 样本量的考虑
- 缺失数据的处理
- 建模方法和超参数调优（嵌套 CV）
- 训练集与评估集如何分离
- 性能指标（区分度、校准度、临床效用）
- 模型的完整表述（系数或可获取的模型文件）
- 公平性和适用范围
- 代码和数据可用性

**REMARK（生物标志物）**：
- 患者和样本特征
- 检测方法（这里是表达谱平台）
- 研究设计
- 预设的统计分析方案
- 单因素和多因素结果
- 解读时的谨慎表述

完成后填好的清单作为补充材料提交。

## AI 使用声明模板（按目标期刊的格式调整）
> During the preparation of this work the authors used AI agents to assist with code development, workflow automation and language editing: <list every tool and model actually used, with versions — e.g. Claude Code (Anthropic, model …) and the AIPOCH Open-Science workbench (v…, model …)>. The agent instructions (skill and specialist definitions) are openly available in the project repository (ai/). All analyses were executed with the open-source pipeline described in Methods, and all reported statistics were generated programmatically and traced to the pipeline outputs. The authors reviewed and verified all code, results and text and take full responsibility for the content of the publication. No generative-AI tools were used to create or alter images.

填写时以实际用过的工具为准，不能遗漏，也不能写没用过的。可以对照 git 历史和 Open-Science 的 `.science` 会话记录来核实。

AI 不能列为作者。

## 数据和代码可用性声明
> All datasets analysed are publicly available (accessions in Supplementary Table S1). The complete analysis pipeline and the interactive atlas source code are available at <GitHub URL> and archived at Zenodo (<DOI>). The interactive atlas is accessible at <URL>.

## 投稿信要点
- 研究空白：CXCL11 的双受体平衡还没有人研究过。
- 方法学严谨性：多队列验证、嵌套 CV、预先设定的分析方案。
- 工具价值：公开的交互式图谱。
- 与期刊范围的契合点。

## 审稿回复格式
逐条回复：先引用审稿人原话，再写回复，然后说明修改在稿件中的位置（页码和行号），新增分析附上对应的 stats key。语气客气、具体，不和审稿人争执。
