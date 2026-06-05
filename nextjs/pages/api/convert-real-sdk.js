/**
 * ✅ 真正的 Copilot SDK 实现
 * 使用官方方式：CopilotClient + createSession + 真实工具调用
 * 
 * 前置条件：
 * 1. GitHub 账户需要 Copilot 许可证
 * 2. COPILOT_GITHUB_TOKEN 必须是有效的 Personal Access Token
 * 3. GitHub CLI (gh) 已安装并认证
 */

import { CopilotClient } from "@github/copilot-sdk";
import { spawn } from "child_process";
import { resolve } from "path";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, "../..");

/**
 * 真实的工具处理器 - 调用实际的 Python 核心模块
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
      message: "🚀 初始化 GitHub Copilot SDK 客户端...",
    });

    const token = process.env.COPILOT_GITHUB_TOKEN;
    if (!token) {
      throw new Error(
        "❌ COPILOT_GITHUB_TOKEN 未设置。请检查 .env 文件。\n\n" +
        "✅ 解决方案:\n" +
        "1. 访问 https://github.com/settings/personal-access-tokens\n" +
        "2. 创建 Fine-grained token (需要 Copilot 许可)\n" +
        "3. 设置 COPILOT_GITHUB_TOKEN=your_token"
      );
    }

    // 创建 Copilot 客户端 - 这需要有效的许可证
    const client = new CopilotClient({
      env: {
        ...process.env,
        GITHUB_TOKEN: token,
      },
      useLoggedInUser: false,
    });

    sendEvent("log", {
      level: "info",
      message: "✅ Copilot Client 已创建，正在连接 CLI...",
    });

    // 启动 CLI 连接
    await client.start();

    sendEvent("log", {
      level: "info",
      message: "✅ CLI 已连接，创建 Agent 会话...",
    });

    // 定义 5 个真实的 SDTM 转换工具
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
          const result = await callPythonModule("retrieve_rules", {
            domain: args.domain,
            query: args.query,
          });
          return {
            textResultForLlm: `成功检索 ${args.domain} 域规则: ${result.count || 0} 条`,
            resultType: "success",
          };
        },
      },
      {
        name: "propose_column_mapping",
        description: "根据源数据和 SDTM 规则，提议最优列映射",
        parameters: {
          type: "object",
          properties: {
            source_columns: {
              type: "array",
              description: "源数据列名",
            },
            domain: { type: "string", description: "目标 SDTM 域" },
          },
          required: ["source_columns", "domain"],
        },
        handler: async (args) => {
          const result = await callPythonModule("propose_mapping", {
            columns: args.source_columns,
            domain: args.domain,
          });
          return {
            textResultForLlm: `成功生成列映射: ${Object.keys(result.mapping || {}).length} 个映射, 置信度 ${result.confidence || "未知"}`,
            resultType: "success",
          };
        },
      },
      {
        name: "transform_to_sdtm",
        description: "根据映射规则将源数据转换为 SDTM 格式",
        parameters: {
          type: "object",
          properties: {
            source_file: { type: "string", description: "源文件路径" },
            domain: { type: "string", description: "目标 SDTM 域" },
          },
          required: ["source_file", "domain"],
        },
        handler: async (args) => {
          const result = await callPythonModule("transform", {
            source_file: args.source_file,
            domain: args.domain,
          });
          return {
            textResultForLlm: `成功转换数据: ${result.recordsTransformed || 0} 条记录, 成功率 ${result.successRate || "未知"}`,
            resultType: "success",
          };
        },
      },
      {
        name: "validate_sdtm",
        description: "验证生成的 SDTM 数据是否符合标准规范",
        parameters: {
          type: "object",
          properties: {
            sdtm_file: { type: "string", description: "SDTM 文件路径" },
            domain: { type: "string", description: "SDTM 域名" },
          },
          required: ["sdtm_file", "domain"],
        },
        handler: async (args) => {
          const result = await callPythonModule("validate", {
            sdtm_file: args.sdtm_file,
            domain: args.domain,
          });
          return {
            textResultForLlm: `验证完成: 发现 ${result.issuesFound || 0} 个问题, ${result.warningsFound || 0} 个警告, 合规性分数 ${result.score || "未知"}`,
            resultType: "success",
          };
        },
      },
    ];

    sendEvent("log", {
      level: "info",
      message: "✅ 5 个 SDTM Conversion 工具已注册",
    });

    // 创建 Agent 会话
    const session = await client.createSession({
      tools,
      onPermissionRequest: async () => "approve",
    });

    sendEvent("log", {
      level: "info",
      message: "✅ Agent 会话已创建",
    });

    const userQuery = domain
      ? `请将文件 ${sourceFile} 转换为 ${domain} 域的 SDTM 格式。步骤：
1. 使用 read_source_data 读取源数据文件
2. 使用 retrieve_sdtm_rules 检索 ${domain} 域的 SDTM 规则
3. 使用 propose_column_mapping 提议列映射方案
4. 使用 transform_to_sdtm 执行数据转换
5. 使用 validate_sdtm 验证转换结果`
      : `请将文件 ${sourceFile} 转换为 SDTM 格式。自动选择合适的域并按照标准流程处理。`;

    sendEvent("log", {
      level: "info",
      message: `📝 用户请求: 转换 ${sourceFile}${domain ? ` 为 ${domain} 域` : ""}`,
    });

    sendEvent("log", {
      level: "info",
      message: "🤖 Copilot Agent 正在处理...",
    });

    let toolCount = 0;
    const startTime = Date.now();

    // 监听 Agent 事件
    session.on((event) => {
      if (event.type === "tool_call") {
        toolCount++;
        sendEvent("tool_call", {
          toolNumber: toolCount,
          toolName: event.data?.name,
          message: `🛠️ [步骤 ${toolCount}] Copilot 决策：调用工具 "${event.data?.name}"`,
        });
      } else if (event.type === "tool_result") {
        sendEvent("tool_result", {
          toolNumber: toolCount,
          toolName: event.data?.name,
          status: event.data?.error ? "error" : "success",
          message: event.data?.error
            ? `❌ 工具执行失败: ${event.data.error}`
            : `✓ 工具 ${toolCount} 执行成功`,
        });
      } else if (event.type === "assistant.message") {
        sendEvent("message", {
          content: event.data?.content || "Agent 正在处理...",
        });
      }
    });

    // 发送消息并等待 Agent 完成
    await session.sendAndWait({ prompt: userQuery }, 600000);

    const duration = ((Date.now() - startTime) / 1000).toFixed(2);

    sendEvent("complete", {
      status: "success",
      toolsExecuted: toolCount,
      duration,
      message: `✅ 转换完成！Copilot Agent 独立调用了 ${toolCount} 个工具，耗时 ${duration}s`,
      outputFile: `data/output/SDTM_${domain || "output"}.xlsx`,
    });

    // 清理
    await session.disconnect();
    await client.stop();

    res.end();
  } catch (error) {
    console.error("🔴 API Error:", error);

    // 检查是否是许可证问题
    if (error.message?.includes("No model available")) {
      sendEvent("error", {
        status: "failed",
        message: "❌ Copilot 许可证问题：你的 GitHub 账户没有 Copilot 许可。",
        solution: "✅ 解决方案：\n1. 购买 Copilot 订阅 (https://github.com/github-copilot/signup)\n2. 或加入拥有 Copilot 许可的组织\n3. 或使用免费的替代 LLM 实现",
      });
    } else {
      sendEvent("error", {
        status: "failed",
        message: `❌ 错误: ${error.message}`,
      });
    }
    res.end();
  }
}
