/**
 * GitHub Copilot SDK Agent 后端
 * 
 * 这是 Copilot SDK 的官方集成示例
 * 它使用 Copilot 内置的 Agentic Core 来自动编排 Skills
 * 
 * 工作流：
 * 1. 前端发送用户请求 + 文件路径
 * 2. 后端初始化 CopilotClient (用 COPILOT_GITHUB_TOKEN 认证)
 * 3. 创建 Session，注册 5 个 Skills (Tools)
 * 4. Copilot Agent 自动决定何时调用哪个 Skill
 * 5. 流式推送事件到前端
 */

import { CopilotClient, SkillParameter } from "@github/copilot-sdk";
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "../../");

/**
 * 初始化 Copilot Client
 * 这里使用官方的 Copilot SDK，会自动使用环境变量中的 COPILOT_GITHUB_TOKEN
 */
function initializeCopilotClient() {
  const token = process.env.COPILOT_GITHUB_TOKEN;
  if (!token) {
    throw new Error(
      "COPILOT_GITHUB_TOKEN 未设置。请在 .env 中添加你的 token。"
    );
  }

  return new CopilotClient({
    token: token,
    // 使用官方的生产级 Agent 运行时
    agentic: true,
    // 启用流式事件
    streaming: true,
  });
}

/**
 * 执行 Python Skill
 * 
 * 这是对 Python 后端的调用包装器
 * 实际的业务逻辑（数据处理、转换等）还在 Python 中
 */
function executePythonSkill(skillName, args) {
  return new Promise((resolve, reject) => {
    const pythonPath = process.env.PYTHON_PATH || 
      path.resolve(projectRoot, "venv", "Scripts", "python");

    // 使用 JSON.stringify 正确转义 Windows 路径中的反斜杠
    const projectRootPy = JSON.stringify(projectRoot);
    
    const pythonCode = `
import sys
import json
sys.path.insert(0, ${projectRootPy})

from agent import *

try:
    if '${skillName}' == 'read_source_data':
        result = mcp_read_source_data('${args[0]}')
    elif '${skillName}' == 'retrieve_sdtm_rules':
        result = mcp_retrieve_sdtm_rules('${args[0]}', ${args[1] ? `'${args[1]}'` : 'None'})
    elif '${skillName}' == 'propose_column_mapping':
        result = mcp_propose_column_mapping('${args[0]}', '${args[1]}')
    elif '${skillName}' == 'transform_to_sdtm':
        result = mcp_transform_to_sdtm('${args[0]}', '${args[1]}')
    elif '${skillName}' == 'validate_sdtm':
        result = mcp_validate_sdtm('${args[0]}', '${args[1]}')
    else:
        result = {'success': False, 'error': 'Unknown skill'}
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}))
`;

    const proc = spawn(pythonPath, ["-c", pythonCode], {
      cwd: projectRoot,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: projectRoot,
      },
    });

    let stdout = "";
    let stderr = "";

    const timeout = setTimeout(() => {
      proc.kill();
      reject(new Error(`Skill execution timeout: ${skillName}`));
    }, 10 * 60 * 1000); // 10 分钟超时

    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));

    proc.on("close", (code) => {
      clearTimeout(timeout);
      if (code !== 0) {
        return reject(
          new Error(`Skill failed (${skillName}): ${stderr || stdout}`)
        );
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(
          new Error(
            `Failed to parse skill output: ${e.message}\nOutput: ${stdout}`
          )
        );
      }
    });
  });
}

/**
 * 定义 SDTM 转换的 Skills (Tools)
 * 这些会被注册到 Copilot Agent
 */
function defineSkills() {
  return [
    {
      name: "read_source_data",
      description:
        "读取并分析源数据文件（Excel/CSV），返回列信息、数据类型、缺失率、样本值",
      parameters: [
        {
          name: "source_path",
          description: "源数据文件路径（相对于项目根目录）",
          type: "string",
          required: true,
        },
      ],
      execute: async (params) => {
        return await executePythonSkill("read_source_data", [params.source_path]);
      },
    },
    {
      name: "retrieve_sdtm_rules",
      description:
        "从 RAG 检索 SDTMIG 规范，查询与特定域或变量相关的规则",
      parameters: [
        {
          name: "query",
          description: "查询内容（如：'AE domain requirements' 或 'AESEQ'）",
          type: "string",
          required: true,
        },
        {
          name: "domain",
          description: "SDTM 域名（可选，如 'AE', 'CM', 'LB'）",
          type: "string",
          required: false,
        },
      ],
      execute: async (params) => {
        return await executePythonSkill("retrieve_sdtm_rules", [
          params.query,
          params.domain,
        ]);
      },
    },
    {
      name: "propose_column_mapping",
      description: "提议源数据列与 SDTM 标准列的对应关系",
      parameters: [
        {
          name: "source_path",
          description: "源数据文件路径",
          type: "string",
          required: true,
        },
        {
          name: "domain",
          description: "SDTM 域名（如 'AE', 'CM'）",
          type: "string",
          required: true,
        },
      ],
      execute: async (params) => {
        return await executePythonSkill("propose_column_mapping", [
          params.source_path,
          params.domain,
        ]);
      },
    },
    {
      name: "transform_to_sdtm",
      description: "根据映射关系执行 SDTM 转换",
      parameters: [
        {
          name: "source_path",
          description: "源数据文件路径",
          type: "string",
          required: true,
        },
        {
          name: "domain",
          description: "SDTM 域名",
          type: "string",
          required: true,
        },
      ],
      execute: async (params) => {
        return await executePythonSkill("transform_to_sdtm", [
          params.source_path,
          params.domain,
        ]);
      },
    },
    {
      name: "validate_sdtm",
      description: "验证转换后的 SDTM 数据是否符合规范",
      parameters: [
        {
          name: "sdtm_path",
          description: "SDTM 文件路径（xlsx）",
          type: "string",
          required: true,
        },
        {
          name: "domain",
          description: "SDTM 域名",
          type: "string",
          required: true,
        },
      ],
      execute: async (params) => {
        return await executePythonSkill("validate_sdtm", [
          params.sdtm_path,
          params.domain,
        ]);
      },
    },
  ];
}

/**
 * 创建 SDTM 转换用的系统提示词
 * 这会被发送给 Copilot Agent 来指导其行为
 */
function getSystemPrompt() {
  return `你是一名高级临床数据 AI 程序员，擅长多域 SDTM 转换。你必须遵循 SDTMIG v3.3 规范。

## 支持的医学数据域（SDTM Domains）
- **AE（不良事件）**：用于记录研究期间发生的不良事件。
- **CM（伴随用药）**：用于记录研究期间的伴随用药信息。
- **LB（实验室检查）**：用于记录实验室检测结果。
- **VS（生命体征）**：用于记录血压、心率等生命体征数据。
- **DM（人口统计学）**：用于记录受试者的人口学特征（年龄、性别、种族等）。

## 工作流（必须按顺序）

1. **识别目标域**：如果用户未明确指定，根据文件内容自动检测（文件名、列名、样本值）。
2. **调用 read_source_data skill**：分析源数据的列名、数据类型、缺失率、样本值。
3. **调用 retrieve_sdtm_rules skill**：查询对应域的 SDTMIG 规范要求和关键变量定义。
4. **调用 propose_column_mapping skill**：提议源列与 SDTM 标准列的对应关系，标记缺失的必需字段。
5. **获取用户确认**（如有歧义）：显示映射预览，请用户确认或提供派生规则。
6. **调用 transform_to_sdtm skill**：执行转换、标准化、生成 SDTM 表。
7. **调用 validate_sdtm skill**：进行质量检查（必需变量完整性、缺失率、序列号连续性）。
8. **生成最终报告**：包括映射关系 JSON、数据质量问题、修复建议。

## 必须规避的错误

- **STUDYID/USUBJID**：不能盲目选择；必须先看数据取值，再选择更合理的列。
- **日期格式**：必须转为 ISO 8601 格式（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS）。
- **受控术语映射**：需按 SDTM 标准列表或本地编码表映射，不得低阈值强配。
- **必需变量缺失**：若映射中缺少任何必填变量（Req），必须追问用户或标记为错误。
- **序列号**：如果域有 key_sequence_var（如 AESEQ、CMSEQ），必须按记录顺序递增分配（1,2,3,...）。
- **数据丢失**：禁止默认过滤记录；除非用户明确要求。

## 关键原则

1. **规范优先**：始终遵循 SDTMIG v3.3，不得因方便而破坏规范。
2. **完整性优先**：所有必需变量必须存在，不能跳过。
3. **可追踪性**：导出映射和报告，便于审计和复查。
4. **用户参与**：在关键决策点追问用户，不要假设。
5. **智能决策**：根据实际数据情况动态调整转换策略。

你现在拥有一组 Skills（Tools）来完成任务。根据用户的需求自主决策：
- 什么时候调用 read_source_data
- 什么时候调用 retrieve_sdtm_rules
- 什么时候调用 propose_column_mapping
- 什么时候调用 transform_to_sdtm
- 什么时候调用 validate_sdtm

不要等待指示，自主完成整个 SDTM 转换任务。`;
}

export { initializeCopilotClient, defineSkills, getSystemPrompt, executePythonSkill };
