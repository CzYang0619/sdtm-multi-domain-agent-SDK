# 📚 文档导航

欢迎来到 SDTM Agent 文档中心！根据你的需求选择对应的文档：

---

## 🚀 快速上手

| 文档 | 内容 | 目标用户 |
|------|------|--------|
| **[QUICK_START.md](./QUICK_START.md)** | ⏱️ 5 分钟快速开始 | 新用户、演示 |
| **[README.md](./README.md)** | 📖 项目全面介绍 | 了解功能和架构 |

**👉 推荐从 `QUICK_START.md` 开始！**

---

## 📖 深入理解

| 文档 | 内容 | 适用场景 |
|------|------|--------|
| **[ARCHITECTURE.md](./ARCHITECTURE.md)** | 🏗️ 系统架构与设计 | 开发者、扩展功能 |
| **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** | 🔧 故障排除指南 | 遇到问题时 |

---

## 按用途查找

### 我想...

#### 🎯 **快速转换数据**
```
→ 查看 QUICK_START.md 的"方式 1: 网页界面"
→ 或"方式 2: Python CLI"
```

#### 🛠️ **修改映射规则**
```
→ 查看 ARCHITECTURE.md 的"关键配置"部分
→ 编辑 core/sdtm_converter.py 中的 DOMAIN_METADATA
```

#### 🐛 **解决问题**
```
→ 查看 TROUBLESHOOTING.md 查找具体问题
→ 按错误信息查找"❌ XXX 错误"部分
```

#### 🚀 **添加新功能**
```
→ 查看 ARCHITECTURE.md 的"扩展指南"
→ 或 TROUBLESHOOTING.md 的"重置与恢复"
```

#### 💻 **使用 Python API**
```
→ 查看 QUICK_START.md 的"方式 3: Python API"
→ 查看 core/sdtm_converter.py 中的类文档
```

#### 🔌 **集成 GitHub Copilot**
```
→ 查看 README.md 的"Copilot SDK 集成"部分
→ 查看 nextjs/lib/copilot-agent.js 的代码示例
```

---

## 📂 文件导航

### Python 核心模块
- `agent.py` - 主入口（CLI 和 API）
- `core/sdtm_converter.py` - 转换引擎 + 验证
- `core/rag_retriever.py` - SDTM 规范检索
- `core/transform.py` - 数据标准化

### Next.js Web 界面
- `nextjs/pages/index.js` - 前端 UI
- `nextjs/pages/api/upload.js` - 文件上传
- `nextjs/pages/api/convert.js` - 转换 API
- `nextjs/lib/copilot-agent.js` - 后端 SDK 集成

### 数据和配置
- `data/raw/` - 输入文件
- `data/output/` - 输出文件（自动生成）
- `data/uploads/` - 网页上传临时文件
- `rag_store/` - SDTM 规范向量索引

---

## 📊 工作流图解

```
用户上传 Excel 文件
    ↓
步骤 1: 读取源数据 (step_1_read_source)
    ↓
步骤 2: 检测域 (step_2_detect_domain)
    ↓
步骤 3: 检索 SDTM 规范 (step_3_retrieve_rules)
    ↓
步骤 4: 提议列映射 (step_4_propose_mapping)
    ↓
步骤 5: 执行转换 (step_5_transform)
    ↓
步骤 6: 质量验证 (step_6_validate)
    ↓
输出文件 (SDTM_AE.xlsx, mapping_AE.json, report_AE.json)
```

每个步骤的详细信息 → 见 [ARCHITECTURE.md](./ARCHITECTURE.md#工作流详解)

---

## 🎓 常见操作

### 1️⃣ 启动网页界面

```bash
cd nextjs
npm run dev
# 打开 http://localhost:3000
```

→ 详见 [QUICK_START.md - 方式 1](./QUICK_START.md#方式-1-网页界面推荐)

### 2️⃣ 从命令行转换

```bash
python agent.py data/raw/CH3_ae.xlsx AE
```

→ 详见 [QUICK_START.md - 方式 2](./QUICK_START.md#方式-2-python-cli命令行)

### 3️⃣ 在 Python 代码中使用

```python
from agent import SDTMAgent

agent = SDTMAgent()
result = agent.convert('data/raw/CH3_ae.xlsx', domain='AE')
```

→ 详见 [QUICK_START.md - 方式 3](./QUICK_START.md#方式-3-python-api)

### 4️⃣ 自定义映射规则

编辑 `core/sdtm_converter.py` → `DOMAIN_METADATA` → 搜索 `"source_column_aliases"`

→ 详见 [ARCHITECTURE.md - 关键配置](./ARCHITECTURE.md#关键配置)

---

## ⚡ 速查表

| 任务 | 命令 | 预期输出 |
|------|------|--------|
| 检查依赖 | `pip install -r requirements.txt` | 无错误 |
| 验证路径 | `python -c "from agent import SDTMAgent; print(SDTMAgent().data_output)"` | `C:\...\data\output` |
| 运行测试 | `python agent.py data/raw/CH3_ae.xlsx` | `✓ Success` + 3 个输出文件 |
| 启动网页 | `cd nextjs && npm run dev` | 打开 http://localhost:3000 |
| 查看帮助 | `python agent.py --help` | 显示所有命令 |

---

## 🆘 问题速查

| 症状 | 检查文档 | 关键词搜索 |
|------|--------|----------|
| 文件输出到错误位置 | TROUBLESHOOTING.md | "文件输出到错误位置" |
| 上传失败 | TROUBLESHOOTING.md | "网页上传失败" |
| 验证错误过多 | TROUBLESHOOTING.md | "验证报告中错误过多" |
| 模块未找到 | TROUBLESHOOTING.md | "Python 模块未找到" |
| 性能慢 | TROUBLESHOOTING.md | "性能优化" |

→ **立即前往** [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

## 📚 完整文档列表

### 主要文档（按优先级）
1. ✅ **QUICK_START.md** - 开始从这里
2. 📖 **README.md** - 项目介绍
3. 🏗️ **ARCHITECTURE.md** - 系统设计
4. 🔧 **TROUBLESHOOTING.md** - 问题解决
5. 📚 **DOC_INDEX.md** - 你现在在这里

### GitHub Skills 文档
- `.github/skills/sdtm/SKILL.md` - Copilot SDK 技能定义

---

## 💡 提示

- 🔍 使用浏览器的 Ctrl+F (Cmd+F) 搜索关键词
- 📖 遇到术语不懂？查看 README.md 的"术语表"
- 🆘 问题持续存在？收集日志文件从 `data/output/step*.json`
- 💬 有建议？在代码中留下注释或提出 Issue

---

**版本**: v1.0  
**最后更新**: 2024  
**维护**: SDTM Agent 开发团队
