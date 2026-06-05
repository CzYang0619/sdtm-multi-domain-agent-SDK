# SDTM Agent 架构说明

## 系统设计

SDTM Agent 是一个多入口的智能数据转换系统，支持三种调用方式：

```
┌─────────────────────────────────────────────────────────┐
│           User Interface / Entry Points                 │
├─────────────────────────────────────────────────────────┤
│  1️⃣  网页界面          2️⃣  命令行 CLI        3️⃣  Python API  │
│  (Next.js)          (python agent.py)   (import agent)  │
└────────────┬────────────────┬──────────────────┬────────┘
             │                │                  │
             ▼                ▼                  ▼
┌──────────────────────────────────────────────────────────┐
│              agent.py (核心编排层)                      │
│  - SDTMAgent 类                                         │
│  - 6 步工作流 (step_1 ~ step_6)                         │
│  - MCP Skills 导出 (mcp_*)                              │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────┐
│              core/ 模块（转换引擎）                     │
├──────────────────────────────────────────────────────────┤
│  sdtm_converter.py   - 核心转换逻辑 + ValidationReport  │
│  rag_retriever.py    - SDTM 规范 RAG 检索               │
│  transform.py        - 数据标准化与映射                 │
│  validate.py         - 数据质量验证                     │
└──────────────────────────────────────────────────────────┘
```

## 工作流详解

### 步骤 1: 读取源数据 (`step_1_read_source`)
```
输入: 源文件路径 (xlsx/csv)
│
├─ 验证文件存在和格式
├─ 读取数据到内存 (pandas DataFrame)
└─ 提取列名、数据类型、缺失率
│
输出: {
  "file": 文件路径,
  "records": 行数,
  "columns": 列名列表,
  "shape": (行, 列)
}
```

### 步骤 2: 检测域 (`step_2_detect_domain`)
```
输入: DataFrame + 文件名
│
├─ 优先级 1: 检查列标记 (AEYN, CMYN, LBYN, VSYN, DMPOP)
├─ 优先级 2: 从文件名检测域代码
└─ 若都失败，返回错误
│
输出: {
  "domain": "AE"|"CM"|"LB"|"VS"|"DM",
  "description": 域描述,
  "required_vars": 必需变量列表
}
```

### 步骤 3: 检索规范 (`step_3_retrieve_rules`)
```
输入: 域代码 + 可选查询
│
├─ 构造 RAG 查询: "[AE] domain requirements and..."
├─ 从 rag_store/ 中检索相关片段
└─ 格式化规范文本
│
输出: {
  "chunks_count": 检索到的规范片段数,
  "formatted": 规范文本摘要
}
```

### 步骤 4: 提议映射 (`step_4_propose_mapping`)
```
输入: 源列 + 目标域元数据
│
├─ 查看 DOMAIN_METADATA[domain] 配置
├─ 根据源列别名匹配 SDTM 标准列
├─ 标记必需变量 (DOMAIN, AESEQ 等)
└─ 生成映射建议
│
输出: {
  "domain": "AE",
  "mapping_ready": True,
  "suggested_mapping": {...}
}
```

### 步骤 5: 执行转换 (`step_5_transform`)
```
输入: 源文件 + 域 + 映射
│
├─ 调用 core.sdtm_converter.process_sdtm_conversion()
├─   ├─ 标准化数据 (日期格式、数据类型)
├─   ├─ 应用映射 (列重命名、派生计算)
├─   ├─ 行过滤 (AEYN=Yes)
├─   └─ 输出到 Excel
│
└─ 返回输出文件路径
│
输出: {
  "output_file": "data/output/SDTM_AE.xlsx",
  "shape": (757, 28)
}
```

### 步骤 6: 验证 (`step_6_validate`)
```
输入: SDTM 文件 + 域
│
├─ 读取转换后的 Excel 文件
├─ 初始化 ValidationReport(domain, df)
├─ 执行验证规则:
│   ├─ 检查必需变量
│   ├─ 计算缺失率
│   ├─ 验证受控术语
│   └─ 检查日期格式
│
└─ 生成 report_{domain}.json
│
输出: {
  "success": True,
  "quality_summary": {
    "error": 0,
    "warning": 0,
    "info": 5
  },
  "report_file": "data/output/report_AE.json"
}
```

## 关键配置

### DOMAIN_METADATA (core/sdtm_converter.py)

每个域都有完整的元数据配置：

```python
"AE": {
    "description": "Adverse Events",
    "key_seq_var": "AESEQ",
    "required_vars": ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM"],
    "expected_vars": [...],
    "source_column_aliases": {
        "AESTDTC": ["AESTDAT", "AE_START_DATE"],
        "AEENDTC": ["AEENDAT", "AE_END_DATE"],
    },
    "derived_columns": {
        "AESTDTC": {
            "source_col": "AESTDTC",
            "transform": "date_normalize",
        }
    },
    "row_filter": {
        "column": "AEYN",
        "keep_values": ["Yes"]
    }
}
```

## 路径处理

⚠️ **重要**: 项目根目录自动检测机制

```python
# agent.py
PROJECT_ROOT = Path(__file__).parent.absolute()

# 确保无论从哪里调用，都使用正确的路径
# - 网页（nextjs/）
# - CLI（项目根目录）
# - Python API（任意位置）

class SDTMAgent:
    def __init__(self, work_dir: str = None):
        if work_dir is None:
            work_dir = str(PROJECT_ROOT)  # 自动使用项目根
        self.data_output = Path(work_dir) / "data" / "output"
```

## Next.js 集成

### 文件上传流程

```
前端 (pages/index.js)
    ↓ POST /api/upload
API (pages/api/upload.js)
    ├─ 接收 multipart/form-data
    ├─ 保存到 data/uploads/
    └─ 返回文件路径
    ↓
前端 (pages/index.js)
    ↓ POST /api/convert (sourceFile, domain)
API (pages/api/convert.js)
    ├─ Copilot SDK 初始化
    ├─ 调用 lib/copilot-agent.js 的 skills
    ├─ Skills 通过 spawn 执行 Python
    └─ SSE 流式返回进度
    ↓
Python (nextjs/lib/copilot-agent.js → spawn)
    ├─ sys.path.insert(0, projectRoot)
    ├─ from agent import *
    ├─ mcp_transform_to_sdtm(...)
    └─ 输出写入 data/output/
```

### Windows 路径转义修复

关键修复（已应用）：

```javascript
// ✓ 正确做法：使用 JSON.stringify 转义路径
const projectRootPy = JSON.stringify(projectRoot);
const pythonCode = `sys.path.insert(0, ${projectRootPy})`;

// ✗ 错误做法：直接字符串拼接
const pythonCode = `sys.path.insert(0, '${projectRoot}')`;
// → 在 Windows 上 \ 被当作转义符，导致路径错误
```

## 调试技巧

### 查看实际路径

```python
import sys
print(f"PROJECT_ROOT={PROJECT_ROOT}", file=sys.stderr)
print(f"data_output={agent.data_output}", file=sys.stderr)
```

### 查看工作流状态

```python
agent = SDTMAgent()
agent.step_1_read_source("data/raw/CH3_ae.xlsx")
print(agent.state)  # {'source_file': ..., 'source_df': ..., ...}
```

### 测试单个步骤

```python
from agent import SDTMAgent

agent = SDTMAgent()
agent.step_1_read_source("data/raw/CH3_ae.xlsx")
agent.step_2_detect_domain()
result = agent.step_3_retrieve_rules()
print(result)
```

## 扩展指南

### 添加新域支持

1. 在 `core/sdtm_converter.py` 的 `DOMAIN_METADATA` 中添加：
```python
"XX": {
    "description": "...",
    "key_seq_var": "XXSEQ",
    "required_vars": [...],
    # ... 其他配置
}
```

2. 添加 RAG 规范文档（rag_store/ 中）

3. 测试转换流程

### 自定义映射规则

编辑 `source_column_aliases` 和 `derived_columns` 配置

### 添加新的验证规则

在 `core/sdtm_converter.py` 的 `ValidationReport` 类中添加验证方法
