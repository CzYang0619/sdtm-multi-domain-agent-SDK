/**
 * Next.js API Route: /api/convert
 * 
 * Lab 2 风格的实现 - 在网页上直接调用 Copilot SDK Agent
 * 
 * 功能：
 * - 初始化 Copilot Client
 * - 注册 5 个 Skills
 * - 启动 Agent 自主工作流
 * - 通过 Server-Sent Events 实时流式推送进度
 */

import { initializeCopilotClient, defineSkills, getSystemPrompt } from "@/lib/copilot-agent";

async function handleSSE(res, sourceFile, domain) {
  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  const sendEvent = (type, data) => {
    const event = {
      type,
      timestamp: new Date().toISOString(),
      ...data
    };
    res.write(`data: ${JSON.stringify(event)}\n\n`);
  };

  try {
    // Step 1: 初始化 Copilot Client
    console.log("[API] 初始化 Copilot Client...");
    const client = initializeCopilotClient();
    sendEvent("log", {
      level: "info",
      message: "✅ Copilot Client 已初始化",
    });

    // Step 2: 定义并注册 Skills
    console.log("[API] 注册 Skills...");
    const skills = defineSkills();
    sendEvent("log", {
      level: "info",
      message: `✅ 已注册 ${skills.length} 个 Skills: ${skills.map(s => s.name).join(", ")}`,
    });

    // Step 3: 创建 Session
    console.log("[API] 创建 Session...");
    const session = await client.createSession({
      skills: skills,
      systemPrompt: getSystemPrompt(),
    });
    sendEvent("log", {
      level: "info",
      message: "✅ Session 已创建，Agent 准备就绪",
    });

    // Step 4: 构建用户请求
    const userQuery = domain 
      ? `请将文件 ${sourceFile} 转换为 ${domain} 域的 SDTM 格式`
      : `请将文件 ${sourceFile} 转换为 SDTM 格式`;

    sendEvent("log", {
      level: "info",
      message: `📝 用户请求: ${userQuery}`,
    });

    sendEvent("log", {
      level: "info",
      message: "🤖 Agent 开始自主工作流...",
    });

    // Step 5: 启动 Agent（流式处理事件）
    let skillCount = 0;
    const startTime = Date.now();

    const eventHandler = async (event) => {
      console.log("[Agent Event]", event.type);

      if (event.type === "tool_call") {
        skillCount++;
        sendEvent("skill_start", {
          skillNumber: skillCount,
          skillName: event.toolName || event.name,
          message: `🛠️ [步骤 ${skillCount}] 调用 Skill: ${event.toolName || event.name}`,
        });
      } else if (event.type === "tool_result") {
        sendEvent("skill_result", {
          skillNumber: skillCount,
          skillName: event.toolName || event.name,
          status: event.isError ? "error" : "success",
          message: event.isError 
            ? `❌ 执行失败: ${event.result}`
            : `✓ 步骤 ${skillCount} 完成`,
        });
      } else if (event.type === "message") {
        sendEvent("log", {
          level: "info",
          message: event.message || event.content || "Agent 思考中...",
        });
      } else if (event.type === "error") {
        sendEvent("log", {
          level: "error",
          message: `⚠️ 错误: ${event.message}`,
        });
      }
    };

    // 启动 Agent
    try {
      await session.run(userQuery, {
        onEvent: eventHandler,
      });

      sendEvent("complete", {
        success: true,
        message: "✅ 转换完成",
        outputDir: "data/output",
        files: {
          sdtmFile: "SDTM_AE.xlsx",
          mappingFile: "mapping_AE.json",
          reportFile: "report_AE.json",
        },
        duration: Math.round((Date.now() - startTime) / 1000),
      });
    } catch (agentError) {
      console.error("[Agent Error]", agentError);
      sendEvent("error", {
        message: `Agent 执行失败: ${agentError.message}`,
      });
    }

    res.end();
  } catch (error) {
    console.error("[Fatal Error]", error);
    sendEvent("error", {
      message: `致命错误: ${error.message}`,
    });
    res.end();
  }
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "只支持 POST 方法" });
  }

  const { sourceFile, domain } = req.body;

  if (!sourceFile) {
    return res.status(400).json({ error: "sourceFile 为必填项" });
  }

  await handleSSE(res, sourceFile, domain);
}
