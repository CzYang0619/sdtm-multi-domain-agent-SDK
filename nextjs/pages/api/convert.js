/**
 * ✅ 正确的 Copilot SDK 实现 - 基于 lab-agent-skills-sdk 参考项目
 * 使用真实的 Copilot SDK，SSE 流式响应
 */

import * as path from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
import { config as loadDotEnv } from 'dotenv';

// 获取项目根目录（从 nextjs 目录往上一级）
const projectRoot = path.resolve(process.cwd(), '..');

// 加载 .env
const dotenvResult = loadDotEnv({ path: path.join(projectRoot, '.env'), debug: false });
if (dotenvResult.error) {
  console.warn('[dotenv] failed to load .env', dotenvResult.error);
} else {
  console.log(`[dotenv] loaded keys: ${Object.keys(dotenvResult.parsed ?? {}).join(', ') || '(none)'}`);
}

console.log(`[env] COPILOT_GITHUB_TOKEN present=${Boolean(process.env.COPILOT_GITHUB_TOKEN)} len=${(process.env.COPILOT_GITHUB_TOKEN ?? '').length}`);

// ==================== 工具定义 ====================

async function callPythonModule(moduleName, functionName, args) {
  return new Promise((resolve, reject) => {
    // 使用 JSON.stringify 正确转义 Windows 路径中的反斜杠
    const projectRootPy = JSON.stringify(projectRoot);
    
    const pythonCode = `
import json
import sys
sys.path.insert(0, ${projectRootPy})
try:
  from core.${moduleName} import ${functionName}
  result = ${functionName}(**${JSON.stringify(args)})
  print(json.dumps(result))
except Exception as e:
  print(json.dumps({"error": str(e)}))
`;

    const proc = spawn('python', ['-c', pythonCode], {
      cwd: projectRoot,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Python error (${moduleName}.${functionName}): ${stderr}`));
      } else {
        try {
          const parsed = JSON.parse(stdout.trim());
          if (parsed.error) {
            reject(new Error(parsed.error));
          } else {
            resolve(parsed);
          }
        } catch (e) {
          reject(new Error(`Invalid JSON from Python: ${stdout}`));
        }
      }
    });
  });
}

// ==================== SSE 响应函数 ====================

function sseEvent(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function statusPayload(step, message) {
  return { step, message, timestamp: new Date().toISOString() };
}

// ==================== SDK 初始化 ====================

let bootstrapPromise = null;

async function loadCopilotSdk() {
  const sdkEntryFile = path.join(process.cwd(), 'node_modules', '@github', 'copilot-sdk', 'dist', 'index.js');
  const sdkEntryUrl = pathToFileURL(sdkEntryFile).href;
  console.log(`[SDK] Loading from: ${sdkEntryUrl}`);
  return import(/* webpackIgnore: true */ sdkEntryUrl);
}

function buildClientOptions() {
  const cliUrl = process.env.COPILOT_CLI_URL?.trim();
  const githubToken = process.env.COPILOT_GITHUB_TOKEN?.trim();
  
  console.log('[buildClientOptions]');
  console.log('  cliUrl:', cliUrl ? `${cliUrl.slice(0, 20)}...` : 'undefined');
  console.log('  githubToken:', githubToken ? `${githubToken.slice(0, 20)}...len=${githubToken.length}` : 'undefined');
  console.log('  useLoggedInUser:', githubToken ? false : undefined);
  
  return {
    cliUrl: cliUrl || undefined,
    githubToken: githubToken || undefined,
    useLoggedInUser: githubToken ? false : undefined,
  };
}

async function bootstrapClient() {
  if (bootstrapPromise) {
    return bootstrapPromise;
  }

  bootstrapPromise = (async () => {
    const { CopilotClient } = await loadCopilotSdk();
    const client = new CopilotClient(buildClientOptions());
    
    console.log('[SDK] Starting client...');
    await client.start();
    
    console.log('[SDK] Client started successfully');
    const modelId = process.env.COPILOT_MODEL?.trim() || 'gpt-5.3-codex';
    
    return { client, modelId };
  })();

  return bootstrapPromise;
}

// ==================== API 处理器 ====================

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { sourceFile, domain } = req.body;

  // 设置 SSE 响应头
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');

  const encoder = new TextEncoder();
  
  // 创建 ReadableStream 来处理 SSE 响应
  const readable = new ReadableStream({
    async start(controller) {
      let closed = false;
      
      const write = (event, data) => {
        if (closed) return;
        try {
          const eventStr = sseEvent(event, data);
          controller.enqueue(new TextEncoder().encode(eventStr));
        } catch (e) {
          console.error('Error writing event:', e);
        }
      };

      const close = () => {
        if (closed) return;
        closed = true;
        controller.close();
      };

      try {
        write('status', statusPayload('initializing', 'Starting Copilot SDK...'));

        // 验证参数
        if (!sourceFile || !domain) {
          write('error', { message: 'Missing sourceFile or domain' });
          close();
          return;
        }

        // 启动 Client
        console.log('[API] Bootstrapping client...');
        const { client, modelId } = await bootstrapClient();

        write('status', statusPayload('connected', `Connected to Copilot SDK (model: ${modelId})`));

        // 创建会话
        write('status', statusPayload('session_creating', 'Creating Copilot session...'));

        const approveAll = () => ({ kind: 'approved' });

        const session = await client.createSession({
          model: modelId,
          workingDirectory: path.join(process.cwd(), '..'), // 修改为项目根目录
          skillDirectories: [path.join(process.cwd(), '..', '.github', 'skills')], // 指向项目根的 skills 目录
          onPermissionRequest: approveAll,
          onUserInputRequest: (request) => ({
            answer: request.choices?.[0] ?? 'yes',
            wasFreeform: !(request.choices ?? []).includes('yes'),
          }),
          streaming: true,
          gitHubToken: process.env.COPILOT_GITHUB_TOKEN, // 添加 per-session GitHub token
        });

        write('status', statusPayload('session_ready', 'Copilot session created'));

        // 监听事件
        let toolExecutionCount = 0;
        let lastAssistantMessage = '';
        const unsubscribe = session.on((event) => {
          // 解析和转发事件
          write('sdk-event', {
            type: event.type,
            data: event.data || {},
            timestamp: new Date().toISOString(),
          });

          // 特殊处理工具执行
          if (event.type === 'tool.execution_start') {
            toolExecutionCount++;
            write('log', {
              level: 'info',
              message: `Tool execution started: ${event.data?.toolName || 'unknown'}`,
            });
          }

          if (event.type === 'tool.execution_complete') {
            const success = event.data?.success !== false;
            if (!success) {
              write('log', {
                level: 'error',
                message: `Tool failed: ${event.data?.toolName} - ${event.data?.error?.message}`,
              });
            }
          }

          if (event.type === 'assistant.message_delta' && event.data?.deltaContent) {
            write('log', {
              level: 'info',
              message: event.data.deltaContent,
            });
          }

          if (event.type === 'assistant.message') {
            lastAssistantMessage = event.data?.content || '';
            write('assistant_final', { content: lastAssistantMessage });
          }

          if (event.type === 'session.error') {
            write('log', {
              level: 'error',
              message: `Session error: ${event.data?.message}`,
            });
          }
        });

        // 构建提示词
        const prompt = `请使用项目的 SDTM 转换工具，完成以下任务：

源文件: ${sourceFile}
目标领域: ${domain}

工作流程:
1. 使用 read_source_data 工具读取源数据文件，了解其结构
2. 使用 retrieve_sdtm_rules 工具获取 ${domain} 领域的 SDTM 标准规则
3. 使用 propose_column_mapping 工具为源列与 SDTM 列之间生成映射建议
4. 使用 transform_to_sdtm 工具根据映射转换数据
5. 使用 validate_sdtm 工具验证转换后的数据是否符合 SDTM 标准

请按这个顺序执行，并为每一步提供详细的结果摘要。`;

        write('status', statusPayload('processing', 'Sending request to Copilot...'));
        write('log', {
          level: 'info',
          message: `Processing ${domain} domain conversion for file: ${sourceFile}`,
        });

        // 发送请求（异步发送，监听 session.idle 事件）
        await session.send({ prompt });

        // 监听 session.idle 事件
        session.on('session.idle', async () => {
          // 发送最后的assistant消息
          if (lastAssistantMessage) {
            write('log', {
              level: 'info',
              message: `Final assistant message: ${lastAssistantMessage}`,
            });
          }

          write('log', {
            level: 'info',
            message: 'Session idle, conversion complete.',
          });

          write('status', statusPayload('complete', `Conversion complete. Processed ${toolExecutionCount} tools.`));

          unsubscribe();
          await session.destroy();

          close();
        });
      } catch (error) {
        console.error('[API] Error:', error);
        write('error', {
          status: 'failed',
          message: error.message || 'Unknown error',
          stack: error.stack,
        });
        close();
      }
    },
  });

  // 发送流式响应
  try {
    // 将 ReadableStream 转换为 Node.js stream
    const reader = readable.getReader();
    
    const pump = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          res.write(Buffer.from(value));
        }
      } catch (e) {
        console.error('Stream error:', e);
      } finally {
        res.end();
      }
    };

    pump();
  } catch (error) {
    console.error('Response error:', error);
    res.status(500).json({ error: error.message });
  }
}
