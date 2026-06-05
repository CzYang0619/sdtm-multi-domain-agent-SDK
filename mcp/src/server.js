import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import process from "node:process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// repoRoot = .../sdtm-multi-domain-agent
const repoRoot = path.resolve(__dirname, "..", "..");

function runPythonSkill(skillName, args, { timeoutMs = 10 * 60 * 1000 } = {}) {
  return new Promise((resolve, reject) => {
    // 获取 Python 虚拟环境路径
    const pythonPath = process.env.PYTHON_PATH || path.resolve(repoRoot, "venv", "Scripts", "python");
    
    // 运行 Python 脚本
    const proc = spawn(pythonPath, [
      "-c",
      `
import sys
import io
import json
# 强制 UTF-8 编码处理（关键修复）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '${repoRoot}')
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
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False))
`
    ], {
      cwd: repoRoot,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: repoRoot
      }
    });

    let stdout = "";
    let stderr = "";

    const timer = setTimeout(() => {
      try {
        proc.kill();
      } catch {
        // ignore
      }
      reject(new Error(`Timeout after ${timeoutMs}ms. stderr: ${stderr}`));
    }, timeoutMs);

    proc.stdout.on("data", (d) => (stdout += d.toString()));
    proc.stderr.on("data", (d) => (stderr += d.toString()));

    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });

    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        return reject(new Error(`Python skill failed (code ${code}). stderr: ${stderr}`));
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`Failed to parse Python output as JSON: ${e.message}. stdout=${stdout}`));
      }
    });
  });
}

const server = new Server(
  {
    name: "sdtm-multi-domain-tools",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "read_source_data",
        description: "Read a raw Excel/CSV file and summarize columns, types, missing rates, and samples.",
        inputSchema: z
          .object({
            sourcePath: z.string().describe("Path to source file (xlsx/csv), absolute or relative to repo root."),
          })
          .strict(),
      },
      {
        name: "retrieve_sdtm_rules",
        description: "Retrieve SDTMIG rules and guidance for a query and optional domain using RAG.",
        inputSchema: z
          .object({
            query: z.string().describe("Query text"),
            domain: z.string().optional().describe("SDTM domain (AE/CM/LB/VS/DM) or omit for general"),
          })
          .strict(),
      },
      {
        name: "propose_column_mapping",
        description: "Propose source->SDTM column mapping for a domain.",
        inputSchema: z
          .object({
            sourcePath: z.string(),
            domain: z.string().describe("SDTM domain (AE/CM/LB/VS/DM)"),
          })
          .strict(),
      },
      {
        name: "transform_to_sdtm",
        description: "Transform raw data to SDTM domain using the built-in mapping. Generates SDTM_{DOMAIN}.xlsx.",
        inputSchema: z
          .object({
            sourcePath: z.string(),
            domain: z.string(),
          })
          .strict(),
      },
      {
        name: "validate_sdtm",
        description: "Validate an SDTM file (xlsx/csv) for a domain.",
        inputSchema: z
          .object({
            sdtmPath: z.string().describe("Path to SDTM output file"),
            domain: z.string(),
          })
          .strict(),
      },
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  try {
    let result;
    switch (name) {
      case "read_source_data":
        result = await runPythonSkill("read_source_data", [args.sourcePath]);
        break;
      case "retrieve_sdtm_rules":
        result = await runPythonSkill("retrieve_sdtm_rules", [args.query, args.domain]);
        break;
      case "propose_column_mapping":
        result = await runPythonSkill("propose_column_mapping", [args.sourcePath, args.domain]);
        break;
      case "transform_to_sdtm":
        result = await runPythonSkill("transform_to_sdtm", [args.sourcePath, args.domain]);
        break;
      case "validate_sdtm":
        result = await runPythonSkill("validate_sdtm", [args.sdtmPath, args.domain]);
        break;
      default:
        throw new Error(`Unknown tool: ${name}`);
    }

    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(result, null, 2),
        },
      ],
      isError: false,
    };
  } catch (e) {
    return {
      content: [
        {
          type: "text",
          text: String(e?.stack || e?.message || e),
        },
      ],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
