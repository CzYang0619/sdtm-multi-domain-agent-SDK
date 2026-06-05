# 快速使用指南

## 1. 环境准备

### Windows PowerShell

```powershell
# 进入项目目录
cd C:\Users\ZhiyangCao\Desktop\work\SDK_test\sdtm-multi-domain-agent

# 复制 .env 文件
Copy-Item .env.example .env

# 编辑 .env，填入你的 GitHub token
# $env:COPILOT_GITHUB_TOKEN = "github_pat_..."

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

## 2. 测试核心功能

```bash
# 运行测试
python test_core.py
```

预期输出应包括：
- ✅ Domain metadata loaded
- ✅ SDTMTransformer initialized for all domains
- ✅ RAG retriever loaded with X vectors
- ✅ Copilot agent ready

## 3. 在 VS Code 中使用 Copilot Chat

### 打开工作区

```bash
code sdtm-agent.code-workspace
```

或直接在 VS Code 中：
1. File > Open Workspace from File
2. 选择 `sdtm-agent.code-workspace`

### 在聊天窗口中与 Copilot 交互

示例 1 - 基础转换：
```
我有一份 AE 数据文件 C:\path\to\ae_raw.xlsx，需要转换成 SDTM AE 域格式。
请帮我分析数据结构，提议列映射，然后执行转换。
```

示例 2 - 指定域：
```
转换 D:\data\conmed.csv 为 SDTM CM (伴随用药) 域
```

示例 3 - 查询规范：
```
SDTM AE 域中，AETERM 这个变量有什么要求？
```

示例 4 - 完整工作流：
```
请完成以下步骤：
1. 读取 C:\data\lab_raw.xlsx
2. 确认这是 LB (实验室) 域
3. 查询 SDTMIG 规范中关于 LBTEST 和 LBORRES 的要求
4. 提议列映射方案
5. 执行转换
6. 生成验证报告并列出任何问题
```

## 4. 直接调用 Python 脚本（高级）

### 读取源数据

```bash
python -m core.read_source "C:\data\ae_raw.xlsx"
```

### 查询规范

```bash
python -m core.retrieve_rules "AETERM definition" "AE"
```

### 提议映射

```bash
python -m core.propose_mapping "C:\data\ae_raw.xlsx" "AE"
```

### 执行转换

```bash
python -m core.transform "C:\data\ae_raw.xlsx" "AE" "mapping.json"
```

### 验证数据

```bash
python -m core.validate "output\SDTM_AE.xlsx" "AE"
```

## 5. 使用 Copilot Agent Python API

```python
from core.copilot_agent import SDTMCopilotAgent
import json

# 初始化
agent = SDTMCopilotAgent("./output")

# 1. 读取并分析源数据
schema = agent.read_and_analyze_source("C:/data/ae_raw.xlsx")
print(f"Shape: {schema['shape']}")
print(f"Columns: {schema['columns']}")

# 2. 查询规范
spec = agent.retrieve_sdtm_specification("AETERM requirements", domain="AE")
print("Retrieved rules:")
print(spec['formatted'])

# 3. 提议映射
proposal = agent.propose_mapping_strategy("C:/data/ae_raw.xlsx", "AE")
print("Proposed mapping:")
print(json.dumps(proposal['proposed_mapping'], indent=2))

# 4. 执行转换
result = agent.execute_conversion(
    "C:/data/ae_raw.xlsx", 
    "AE",
    mapping=proposal['proposed_mapping']
)
print(f"Output file: {result['sdtm_file']}")
print(f"Issues: {result['summary']}")
```

## 6. 输出文件说明

转换完成后，会在 session 目录（或 `output/`) 生成：

- **SDTM_{domain}.xlsx** - 转换后的 SDTM 数据表
  - 包含所有必需和期望变量
  - 列顺序符合 SDTM 规范
  - 自动生成序列号

- **mapping_{domain}.json** - 列映射关系文档
  ```json
  {
    "Source Column 1": "SDTM_VAR_1",
    "Source Column 2": "SDTM_VAR_2",
    ...
  }
  ```

- **report_{domain}.json** - 验证报告
  ```json
  {
    "domain": "AE",
    "shape": [100, 25],
    "issues": [
      {
        "type": "missing_values",
        "var": "AETERM",
        "count": 5,
        "percentage": 5.0,
        "severity": "error"
      }
    ],
    "summary": {
      "error": 1,
      "warning": 3,
      "info": 0
    }
  }
  ```

## 7. 常见场景

### 场景 A: 多个文件的批量转换

```bash
# 创建脚本 batch_convert.py
from core.copilot_agent import SDTMCopilotAgent
import os

agent = SDTMCopilotAgent("./output")

files = [
    ("ae_raw.xlsx", "AE"),
    ("conmed_raw.xlsx", "CM"),
    ("lab_raw.xlsx", "LB"),
]

for file, domain in files:
    result = agent.execute_conversion(file, domain)
    print(f"{domain}: {result['output_shape']}")
```

```bash
python batch_convert.py
```

### 场景 B: 使用自定义映射

```python
# 当自动映射不满足需求时
custom_mapping = {
    "EventID": "AESEQ",
    "AEDesc": "AETERM",
    "StartDate": "AESTDTC",
    "EndDate": "AEENDTC",
    "Serious": "AESER",
}

result = agent.execute_conversion(
    "ae_raw.xlsx",
    "AE",
    mapping=custom_mapping
)
```

### 场景 C: 验证已转换的数据

```python
from core.sdtm_converter import ValidationReport
import pandas as pd

df = pd.read_excel("SDTM_AE.xlsx")
validator = ValidationReport("AE", df)
report = validator.validate()

for issue in report['issues']:
    print(f"[{issue['severity']}] {issue['type']}: {issue.get('message', '')}")
```

## 8. 调试技巧

### 查看详细日志

编辑 `core/sdtm_converter.py`，添加更多 print 输出：

```python
print(f"[DEBUG] Processing column: {col}")
```

### 测试单个 skill

```bash
# 只测试映射提议
python core/propose_mapping.py "path/to/data.xlsx" "AE"
```

### 检查 RAG 检索质量

```python
from core.rag_retriever import get_retriever

retriever = get_retriever("./rag_store")

queries = [
    "AETERM requirements",
    "adverse event definition",
    "serious adverse event",
]

for q in queries:
    chunks = retriever.retrieve(q, top_k=3)
    print(f"Query: {q}")
    for c in chunks:
        print(f"  - page {c.page}, score {c.score:.4f}")
```

## 9. 故障排除

### 问题：`FAISS index not found`

**解决**：确保 `rag_store/` 目录完整：
```bash
ls -la rag_store/
# 应该看到:
# sdtmig.faiss
# sdtmig.meta.jsonl
# sdtmig.cfg.json
```

### 问题：`Unsupported domain`

**解决**：检查拼写，支持的域为：AE, CM, LB, VS, DM

```python
from core.sdtm_converter import DOMAIN_METADATA
print(list(DOMAIN_METADATA.keys()))
```

### 问题：转换后有很多缺失值

**原因**：源数据中某些必需列没有正确映射  
**解决**：检查 `mapping_{domain}.json`，手动调整后重新执行

```python
# 查看映射
with open("mapping_AE.json") as f:
    mapping = json.load(f)
    for src, tgt in mapping.items():
        print(f"{src} -> {tgt}")
```

## 10. 下一步

- [ ] 集成更多医学术语控制表（MedDRA, WHODD）
- [ ] 支持 SUPP 表自动生成
- [ ] 集成 Pinnacle21 规则检查
- [ ] 构建 Web UI（参考 `lab-agent-skills-sdk`）
- [ ] 支持更多源格式（SAS7BDAT, Parquet 等）

---

有问题？检查 [README.md](README.md) 获取详细文档。
