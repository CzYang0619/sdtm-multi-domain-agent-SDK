/**
 * 使用 OpenAI API 作为 Copilot 的替代实现
 * 
 * 这是一个临时解决方案，用于绕过 Copilot 许可证问题
 * 您可以使用 OpenAI API 密钥来测试完整的 SDTM 转换工作流
 * 
 * 前置条件：
 * 1. 设置 OPENAI_API_KEY 环境变量
 * 2. 有有效的 OpenAI 账户
 */

import { spawn } from "child_process";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, "../..");

/**
 * 调用真实的 Python 核心模块
 */
async function callPythonModule(moduleName, args) {
  return new Promise((resolve, reject) => {
    const pythonPath = process.env.PYTHON_PATH || "python";
    const pythonScript = resolve(projectRoot, `core/${moduleName}.py`);

    const argString = JSON.stringify(args);
    const process_obj = spawn(pythonPath, ["-c", `
import json
import sys
sys.path.insert(0, '${projectRoot}')
from core.${moduleName} import main
result = main(${argString})
print(json.dumps(result))
`], {
      cwd: projectRoot,
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    process_obj.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    process_obj.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    process_obj.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`Python error: ${stderr}`));
      } else {
        try {
          resolve(JSON.parse(stdout));
        } catch (e) {
          reject(new Error(`Invalid JSON from Python: ${stdout}`));
        }
      }
    });
  });
}

/**
 * 使用 OpenAI API 调用 Agent
 */
async function callOpenAIAgent(sourceFile, domain, tools) {
  const openaiApiKey = process.env.OPENAI_API_KEY;
  if (!openaiApiKey) {
    throw new Error(
      "❌ OPENAI_API_KEY 未设置。请检查 .env 文件。\n\n" +
      "✅ 解决方案:\n" +
      "1. 访问 https://platform.openai.com/api-keys\n" +
      "2. 创建 API Key\n" +
      "3. 设置 OPENAI_API_KEY=sk-..."
    );
  }

  // OpenAI 工具定义
  const openaiTools = tools.map((tool) => ({
    type: "function",
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters,
    },
  }));

  // 初始消息
  const messages = [
    {
      role: "system",
      content: `You are an expert in SDTM (Study Data Tabulation Model) data transformation. 
Your task is to guide the conversion of raw clinical data to SDTM format for the ${domain} domain.
Use the provided tools to: 
1. Read the source data
2. Retrieve SDTM rules for the domain
3. Propose column mapping
4. Transform data to SDTM format
5. Validate the result`,
    },
    {
      role: "user",
      content: `Please convert the file "${sourceFile}" to SDTM ${domain} domain. 
Execute all necessary steps in order: read source, retrieve rules, propose mapping, transform, and validate.`,
    },
  ];

  let allMessages = [...messages];
  const executedTools = new Set();

  // 模拟 Agent 循环
  for (let iteration = 0; iteration < 10; iteration++) {
    const response = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${openaiApiKey}`,
      },
      body: JSON.stringify({
        model: "gpt-4o-mini",
        messages: allMessages,
        tools: openaiTools,
        temperature: 0.7,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        `OpenAI API Error: ${error.error?.message || response.statusText}`
      );
    }

    const data = await response.json();
    const choice = data.choices[0];
    const assistantMessage = choice.message;

    // 添加 assistant 消息
    allMessages.push(assistantMessage);

    // 检查是否完成
    if (choice.finish_reason === "end_turn" || !assistantMessage.tool_calls) {
      return {
        success: true,
        finalMessage: assistantMessage.content,
        toolsExecuted: Array.from(executedTools),
      };
    }

    // 执行工具调用
    const toolResults = [];
    for (const toolCall of assistantMessage.tool_calls || []) {
      const toolName = toolCall.function.name;
      executedTools.add(toolName);

      const tool = tools.find((t) => t.name === toolName);
      if (!tool) {
        toolResults.push({
          tool_call_id: toolCall.id,
          result: `Tool ${toolName} not found`,
        });
        continue;
      }

      try {
        const args = JSON.parse(toolCall.function.arguments);
        const result = await tool.handler(args);
        toolResults.push({
          tool_call_id: toolCall.id,
          result: result.textResultForLlm,
        });
      } catch (error) {
        toolResults.push({
          tool_call_id: toolCall.id,
          result: `Error executing ${toolName}: ${error.message}`,
        });
      }
    }

    // 添加工具结果
    for (const result of toolResults) {
      allMessages.push({
        role: "user",
        content: result.result,
        tool_call_id: result.tool_call_id,
      });
    }
  }

  throw new Error("Agent loop exceeded maximum iterations");
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { sourceFile, domain } = req.body;

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  const sendEvent = (type, data) => {
    res.write(
      `data: ${JSON.stringify({
        type,
        timestamp: new Date().toISOString(),
        ...data,
      })}\n\n`
    );
  };

  try {
    sendEvent("log", {
      level: "info",
      message: "🚀 使用 OpenAI API 初始化 Agent...",
    });

    // 定义 SDTM 转换工具
    const tools = [
      {
        name: "read_source_data",
        description: "读取并分析源数据文件 (Excel/CSV)",
        parameters: {
          type: "object",
          properties: {
            file_path: { type: "string", description: "源文件路径" },
          },
          required: ["file_path"],
        },
        handler: async (args) => {
          sendEvent("log", {
            level: "info",
            message: `📂 正在读取源文件: ${args.file_path}...`,
          });
          const result = await callPythonModule("read_source", {
            file_path: args.file_path,
          });
          return {
            textResultForLlm: `成功读取文件: ${args.file_path}. 列数: ${result.columns?.length || 0}, 行数: ${result.rows || 0}`,
            resultType: "success",
          };
        },
      },
      {
        name: "retrieve_sdtm_rules",
        description: "检索 SDTM 标准规则和指导 (从 RAG 存储)",
        parameters: {
          type: "object",
          properties: {
            domain: { type: "string", description: "SDTM 域名 (如 AE, LB)" },
            query: { type: "string", description: "查询关键词 (可选)" },
          },
          required: ["domain"],
        },
        handler: async (args) => {
          sendEvent("log", {
            level: "info",
            message: `📚 正在检索 SDTM ${args.domain} 域规则...`,
          });
          const result = await callPythonModule("retrieve_rules", {
            domain: args.domain,
            query: args.query,
          });
          return {
            textResultForLlm: `SDTM 规则已检索. 关键信息: ${result.summary || ""}`,
            resultType: "success",
          };
        },
      },
      {
        name: "propose_column_mapping",
        description: "基于源数据和 SDTM 规则提议列映射",
        parameters: {
          type: "object",
          properties: {
            source_columns: {
              type: "array",
              description: "源数据的列名列表",
            },
            domain: { type: "string", description: "SDTM 域名" },
          },
          required: ["source_columns", "domain"],
        },
        handler: async (args) => {
          sendEvent("log", {
            level: "info",
            message: `🗂️ 正在为 ${args.domain} 域提议列映射...`,
          });
          const result = await callPythonModule("propose_mapping", {
            source_columns: args.source_columns,
            domain: args.domain,
          });
          return {
            textResultForLlm: `列映射已生成. 映射项数: ${Object.keys(result.mapping || {}).length}`,
            resultType: "success",
          };
        },
      },
      {
        name: "transform_to_sdtm",
        description: "使用映射将数据转换为 SDTM 格式",
        parameters: {
          type: "object",
          properties: {
            source_file: { type: "string", description: "源数据文件路径" },
            domain: { type: "string", description: "SDTM 域名" },
            mapping: {
              type: "object",
              description: "列映射对象",
            },
          },
          required: ["source_file", "domain", "mapping"],
        },
        handler: async (args) => {
          sendEvent("log", {
            level: "info",
            message: `⚙️ 正在转换数据为 SDTM ${args.domain} 格式...`,
          });
          const result = await callPythonModule("transform", {
            source_file: args.source_file,
            domain: args.domain,
            mapping: args.mapping,
          });
          return {
            textResultForLlm: `转换完成. 输出文件: ${result.output_file}, 转换行数: ${result.rows_converted}`,
            resultType: "success",
          };
        },
      },
      {
        name: "validate_sdtm",
        description: "验证转换后的 SDTM 数据是否符合标准",
        parameters: {
          type: "object",
          properties: {
            sdtm_file: { type: "string", description: "SDTM 文件路径" },
            domain: { type: "string", description: "SDTM 域名" },
          },
          required: ["sdtm_file", "domain"],
        },
        handler: async (args) => {
          sendEvent("log", {
            level: "info",
            message: `✅ 正在验证 SDTM ${args.domain} 数据...`,
          });
          const result = await callPythonModule("validate", {
            sdtm_file: args.sdtm_file,
            domain: args.domain,
          });
          return {
            textResultForLlm: `验证完成. 错误数: ${result.error_count}, 警告数: ${result.warning_count}`,
            resultType: "success",
          };
        },
      },
    ];

    sendEvent("log", {
      level: "info",
      message: "✅ 5 个 SDTM 转换工具已注册",
    });

    sendEvent("log", {
      level: "info",
      message: `📝 用户请求: 转换 ${sourceFile} 为 ${domain} 域`,
    });

    sendEvent("log", {
      level: "info",
      message: "🤖 OpenAI Agent 正在处理...",
    });

    // 调用 OpenAI Agent
    const result = await callOpenAIAgent(sourceFile, domain, tools);

    sendEvent("log", {
      level: "success",
      message: "✅ Agent 处理完成",
    });

    sendEvent("log", {
      level: "info",
      message: `已执行的工具: ${result.toolsExecuted.join(", ")}`,
    });

    sendEvent("message", {
      role: "assistant",
      content: result.finalMessage,
    });

    sendEvent("complete", {
      status: "success",
      message: "SDTM 转换流程完成",
    });

    res.end();
  } catch (error) {
    console.error("Error:", error);
    sendEvent("error", {
      status: "failed",
      message: `❌ ${error.message}`,
      solution:
        "✅ 解决方案:\n" +
        "1. 确保设置了 OPENAI_API_KEY\n" +
        "2. 检查 OpenAI 账户有足够的余额\n" +
        "3. 或者获取有效的 GitHub Copilot 许可证",
    });
    res.end();
  }
}
