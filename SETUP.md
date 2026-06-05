# 初始化检查清单

请按以下步骤完成初始化：

## ✅ 第 1 步：复制文件

已完成的操作：
- [x] 创建了 `sdtm-multi-domain-agent/` 项目目录
- [x] 复制了 RAG 存储 (`rag_store/`) 到新项目
- [x] 创建了核心 Python 模块 (`core/`)
- [x] 创建了 Copilot SDK skills (`.github/skills/`)
- [x] 创建了配置文件和文档

## ✅ 第 2 步：安装依赖

```powershell
cd C:\Users\ZhiyangCao\Desktop\work\SDK_test\sdtm-multi-domain-agent

# 创建虚拟环境
python -m venv venv

# 激活
.\venv\Scripts\Activate.ps1

# 安装
pip install -r requirements.txt
```

预期时间：3-5 分钟（首次下载依赖较慢）

## ✅ 第 3 步：测试核心功能

```bash
python test_core.py
```

预期输出：
```
============================================================
SDTM Multi-Domain Agent - Test Suite
============================================================
✅ Testing domain metadata...
   Supported domains: ['AE', 'CM', 'LB', 'VS', 'DM']
   - AE: Adverse Events
   ...
✅ Testing SDTMTransformer...
   - AE: ✓ Initialized
   - CM: ✓ Initialized
   ...
✅ Testing RAG Retriever...
   - FAISS index loaded: XXXX vectors
   - Metadata entries: XXXX
   ...
✅ Testing Copilot Agent...
   - Supported domains: ['AE', 'CM', 'LB', 'VS', 'DM']

============================================================
✅ All tests completed!
============================================================
```

## ✅ 第 4 步：配置环境变量

```bash
# 复制示例文件
Copy-Item .env.example .env

# 编辑 .env，添加你的 GitHub token
# 在 GitHub 设置中生成 Fine-grained Personal Access Token
# 参考：https://github.com/settings/tokens/new
```

## ✅ 第 5 步：在 VS Code 中打开

```bash
code sdtm-agent.code-workspace
```

## ✅ 第 6 步：验证 Copilot 集成

在 VS Code Chat 窗口尝试：

```
列出支持的 SDTM 域有哪些？
```

预期：Copilot 会列出 AE, CM, LB, VS, DM

## 📁 项目结构验证

确保项目包含以下文件：

```
sdtm-multi-domain-agent/
├── .env.example ............................ ✓
├── .gitignore .............................. ✓
├── requirements.txt ........................ ✓
├── README.md .............................. ✓
├── QUICKSTART.md .......................... ✓
├── sdtm-agent.code-workspace .............. ✓
├── test_core.py ........................... ✓
│
├── .github/skills/
│   ├── SKILL.md ........................... ✓
│   └── sdtm_tools.js ...................... ✓
│
├── core/
│   ├── __init__.py ........................ ✓
│   ├── sdtm_converter.py .................. ✓ (多域转换核心)
│   ├── rag_retriever.py ................... ✓ (向量检索)
│   ├── copilot_agent.py ................... ✓ (SDK 接口)
│   ├── read_source.py ..................... ✓ (skill)
│   ├── retrieve_rules.py .................. ✓ (skill)
│   ├── propose_mapping.py ................. ✓ (skill)
│   ├── transform.py ....................... ✓ (skill)
│   └── validate.py ........................ ✓ (skill)
│
└── rag_store/
    ├── sdtmig.faiss ....................... ✓
    ├── sdtmig.meta.jsonl .................. ✓
    └── sdtmig.cfg.json .................... ✓
```

## 🧪 快速测试

创建一个测试数据文件来验证端到端流程：

```python
# 创建 test_e2e.py
import pandas as pd
from core.copilot_agent import SDTMCopilotAgent

# 创建示例源数据
test_data = {
    'STUDY_ID': ['STUDY001'] * 3,
    'SUBJECT_ID': ['001', '002', '003'],
    'EVENT_SEQ': [1, 1, 2],
    'EVENT_TERM': ['Headache', 'Nausea', 'Headache'],
    'START_DATE': ['2024-01-01', '2024-01-05', '2024-01-10'],
}
df = pd.DataFrame(test_data)
df.to_excel('test_ae_raw.xlsx', index=False)

# 测试转换
agent = SDTMCopilotAgent("./output")
result = agent.read_and_analyze_source('test_ae_raw.xlsx')
print("✓ Read test data:", result['shape'])

proposal = agent.propose_mapping_strategy('test_ae_raw.xlsx', 'AE')
print("✓ Proposed mapping:", len(proposal['proposed_mapping']), "columns")
```

```bash
python test_e2e.py
```

## 🚀 下一步

1. 在 VS Code Chat 中开始测试对话
2. 阅读 [QUICKSTART.md](QUICKSTART.md) 学习详细用法
3. 参考 [README.md](README.md) 了解架构和 API
4. 上传你自己的测试数据进行转换

## ❓ 问题排查

| 问题 | 解决方案 |
|-----|--------|
| `ModuleNotFoundError: No module named 'pandas'` | 运行 `pip install -r requirements.txt` |
| `FAISS index not found` | 检查 `rag_store/` 目录是否完整 |
| `Unsupported domain` | 只支持 AE, CM, LB, VS, DM |
| Copilot Chat 无法识别 skills | 检查 `.env` 中的 token 是否正确 |

## 📞 获取帮助

- 查看 [README.md](README.md) - 完整文档
- 查看 [QUICKSTART.md](QUICKSTART.md) - 使用示例
- 运行 `python test_core.py` - 诊断问题

---

**状态**: ✅ 项目已创建，准备好使用！
