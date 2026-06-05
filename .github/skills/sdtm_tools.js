#!/usr/bin/env node
/**
 * SDTM skills 集成
 * 这些脚本被 Copilot SDK 在 session 中调用
 */

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

// 工作目录应该是 session dir
const SESSION_DIR = process.cwd();

<<<<<<< HEAD
// 项目根目录（sdtm-multi-domain-agent）
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");

// 支持通过环境变量指定 Python 可执行名
const PYTHON_CMD = process.env.PYTHON || process.env.PYTHON_CMD || "python";

// CLI 场景下默认静默（避免 stdout 前缀日志污染 JSON）；可通过 SDTM_TOOLS_VERBOSE=1 打开
const VERBOSE = process.env.SDTM_TOOLS_VERBOSE === "1";

function log(...args) {
  if (VERBOSE) console.log(...args);
}

function withPythonPathEnv(extraEnv = {}) {
  // Windows 用 ;，类 unix 用 :
  const sep = process.platform === "win32" ? ";" : ":";
  const prev = process.env.PYTHONPATH || "";
  const pythonpath = prev ? `${PROJECT_ROOT}${sep}${prev}` : PROJECT_ROOT;
  return {
    ...process.env,
    ...extraEnv,
    PYTHONPATH: pythonpath,
  };
}

function previewText(text, limit = 8000) {
  if (!text) return "";
  if (text.length <= limit) return text;
  return text.slice(0, limit) + `\n... (truncated, total ${text.length} chars)`;
}
=======
// 支持通过环境变量指定 Python 可执行名
const PYTHON_CMD = process.env.PYTHON || process.env.PYTHON_CMD || 'python';
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc

/**
 * 调用 Python 脚本的通用函数
 */
<<<<<<< HEAD
function invokePython(scriptName, args, opts = {}) {
  const { timeoutMs } = opts;
  return new Promise((resolve, reject) => {
    // 通过模块方式运行，确保 Python 可以正确导入 package core
    const moduleName = path.basename(scriptName, ".py");
    const moduleArg = `-m`;
    const modulePath = `core.${moduleName}`;

    const proc = spawn(PYTHON_CMD, [moduleArg, modulePath, ...args], {
      // 关键：固定在项目根运行，避免 session dir 下 import core 失败
      cwd: PROJECT_ROOT,
      stdio: "pipe",
      env: withPythonPathEnv(),
=======
function invokePython(scriptName, args) {
  return new Promise((resolve, reject) => {
    const pythonPath = path.join(__dirname, "..", "..", "core", scriptName);
    // 使用可配置的 Python 可执行
    // 调整为通过模块方式运行，确保 Python 可以正确导入 package core
    const moduleName = path.basename(scriptName, '.py');
    const moduleArg = `-m`;
    const modulePath = `core.${moduleName}`;
    const proc = spawn(PYTHON_CMD, [moduleArg, modulePath, ...args], {
      cwd: SESSION_DIR,
      stdio: "pipe",
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
    });

    let stdout = "";
    let stderr = "";

<<<<<<< HEAD
    let killedByTimeout = false;
    let timer = null;
    if (timeoutMs && Number.isFinite(timeoutMs) && timeoutMs > 0) {
      timer = setTimeout(() => {
        killedByTimeout = true;
        try {
          proc.kill();
        } catch {
          // ignore
        }
      }, timeoutMs);
    }

=======
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
<<<<<<< HEAD
      if (timer) clearTimeout(timer);

      if (killedByTimeout) {
        return reject(
          new Error(
            `Python script timeout after ${timeoutMs}ms.\n` +
              `stderr:\n${previewText(stderr)}\n\nstdout:\n${previewText(stdout)}`
          )
        );
      }

      if (code !== 0) {
        // 返回 stderr/stdout 帮助排查（避免只看到一行）
        return reject(
          new Error(
            `Python script failed (code ${code}).\n` +
              `stderr:\n${previewText(stderr)}\n\nstdout:\n${previewText(stdout)}`
          )
        );
=======
      if (code !== 0) {
        // 返回 stderr 帮助排查
        return reject(new Error(`Python script failed (code ${code}): ${stderr || stdout}`));
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
      }

      // 尝试解析 stdout：优先解析最后一行 JSON，若失败则尝试提取第一个 {...} JSON 区块
      const tryParse = (text) => {
        // 1) 取最后一行非空
<<<<<<< HEAD
        const lines = text
          .trim()
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter((l) => l.length > 0);
        if (lines.length > 0) {
          const last = lines[lines.length - 1];
          try {
            return JSON.parse(last);
          } catch (e) {
            /* 继续尝试 */
          }
=======
        const lines = text.trim().split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
        if (lines.length > 0) {
          const last = lines[lines.length - 1];
          try { return JSON.parse(last); } catch (e) { /* 继续尝试 */ }
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
        }
        // 2) 提取第一个 JSON 对象（保守）
        const m = text.match(/\{[\s\S]*\}/);
        if (m) {
<<<<<<< HEAD
          try {
            return JSON.parse(m[0]);
          } catch (e) {
            /* 继续 */
          }
        }
        // 3) 解析整个 stdout
        try {
          return JSON.parse(text);
        } catch (e) {
          throw new Error("Failed to parse Python output as JSON");
        }
=======
          try { return JSON.parse(m[0]); } catch (e) { /* 继续 */ }
        }
        // 3) 解析整个 stdout
        try { return JSON.parse(text); } catch (e) { throw new Error('Failed to parse Python output as JSON'); }
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
      };

      try {
        const result = tryParse(stdout);
        // 如有 stderr，也作为额外字段返回，便于调试
<<<<<<< HEAD
        if (stderr && typeof result === "object") result._stderr = stderr;
        resolve(result);
      } catch (e) {
        reject(
          new Error(
            `Failed to parse Python output: ${e.message}. stdout: ${previewText(stdout)}, stderr: ${previewText(stderr)}`
          )
        );
=======
        if (stderr && typeof result === 'object') result._stderr = stderr;
        resolve(result);
      } catch (e) {
        reject(new Error(`Failed to parse Python output: ${e.message}. stdout: ${stdout}, stderr: ${stderr}`));
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
      }
    });
  });
}

<<<<<<< HEAD
function parseArgs(argv) {
  // 兼容两种调用：
  // 1) 位置参数：propose <source> <domain>
  // 2) 旗标参数：propose --source <source> --domain <domain>
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const val = argv[i + 1];
      if (val !== undefined && !val.startsWith("--")) {
        out[key] = val;
        i++;
      } else {
        out[key] = true;
      }
    } else {
      out._.push(a);
    }
  }
  return out;
}

=======
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
/**
 * Skill: 读取源数据并分析结构
 */
async function readSourceData(sourcePath) {
<<<<<<< HEAD
  log(`📖 Reading source data from: ${sourcePath}`);
=======
  console.log(`📖 Reading source data from: ${sourcePath}`);
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
  return invokePython("read_source.py", [sourcePath]);
}

/**
 * Skill: 从 RAG 检索 SDTM 规范
 */
async function retrieveSdtmRules(query, domain) {
<<<<<<< HEAD
  log(`📚 Retrieving SDTM rules for: ${query}`);
=======
  console.log(`📚 Retrieving SDTM rules for: ${query}`);
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
  return invokePython("retrieve_rules.py", [query, domain || "general"]);
}

/**
 * Skill: 提议列映射
 */
async function proposeColumnMapping(sourcePath, domain) {
<<<<<<< HEAD
  log(`🔗 Proposing mapping for domain: ${domain}`);
=======
  console.log(`🔗 Proposing mapping for domain: ${domain}`);
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
  return invokePython("propose_mapping.py", [sourcePath, domain]);
}

/**
 * Skill: 执行 SDTM 转换
 */
<<<<<<< HEAD
async function transformToSdtm(sourcePath, domain, mappingJson, opts = {}) {
  log(`⚙️  Transforming to SDTM domain: ${domain}`);

  // mapping 临时文件写到 SESSION_DIR，避免污染项目目录；但路径传给 Python 不受 cwd 影响
  const tempMappingFile = path.join(SESSION_DIR, `_mapping_${domain}.json`);
  fs.writeFileSync(tempMappingFile, JSON.stringify(mappingJson), "utf-8");

  const timeoutMs = opts.timeoutMs;
  return invokePython("transform.py", [sourcePath, domain, tempMappingFile], { timeoutMs }).finally(() => {
    if (fs.existsSync(tempMappingFile)) {
      fs.unlinkSync(tempMappingFile);
    }
  });
=======
async function transformToSdtm(sourcePath, domain, mappingJson) {
  console.log(`⚙️  Transforming to SDTM domain: ${domain}`);
  const tempMappingFile = path.join(SESSION_DIR, `_mapping_${domain}.json`);
  fs.writeFileSync(tempMappingFile, JSON.stringify(mappingJson), "utf-8");
  
  return invokePython("transform.py", [sourcePath, domain, tempMappingFile]).finally(
    () => {
      if (fs.existsSync(tempMappingFile)) {
        fs.unlinkSync(tempMappingFile);
      }
    }
  );
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
}

/**
 * Skill: 验证 SDTM 数据质量
 */
async function validateSdtm(sdtmPath, domain) {
<<<<<<< HEAD
  log(`✅ Validating SDTM data for domain: ${domain}`);
=======
  console.log(`✅ Validating SDTM data for domain: ${domain}`);
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
  return invokePython("validate.py", [sdtmPath, domain]);
}

// CLI 入口
async function main() {
<<<<<<< HEAD
  const [cmd, ...rawArgs] = process.argv.slice(2);
  const parsed = parseArgs(rawArgs);
=======
  const [cmd, ...args] = process.argv.slice(2);
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc

  try {
    let result;
    switch (cmd) {
<<<<<<< HEAD
      case "read": {
        const source = parsed.source || parsed._[0];
        result = await readSourceData(source);
        break;
      }
      case "retrieve": {
        const query = parsed.query || parsed._[0];
        const domain = parsed.domain || parsed._[1];
        result = await retrieveSdtmRules(query, domain);
        break;
      }
      case "propose": {
        const source = parsed.source || parsed._[0];
        const domain = parsed.domain || parsed._[1];
        result = await proposeColumnMapping(source, domain);
        break;
      }
      case "transform": {
        const source = parsed.source || parsed._[0];
        const domain = parsed.domain || parsed._[1];

        const timeoutMsRaw = parsed["timeout-ms"] || parsed.timeoutMs;
        const timeoutMs = timeoutMsRaw ? Number(timeoutMsRaw) : undefined;

        let mapping;
        if (parsed["mapping-file"]) {
          const mappingFile = parsed["mapping-file"];
          const mappingStr = fs.readFileSync(mappingFile, "utf-8");
          mapping = JSON.parse(mappingStr);
        } else {
          const mappingStr = parsed.mapping || parsed._[2];
          mapping = JSON.parse(mappingStr);
        }

        result = await transformToSdtm(source, domain, mapping, { timeoutMs });
        break;
      }
      case "validate": {
        const sdtm = parsed.sdtm || parsed._[0];
        const domain = parsed.domain || parsed._[1];
        result = await validateSdtm(sdtm, domain);
        break;
      }
=======
      case "read":
        result = await readSourceData(args[0]);
        break;
      case "retrieve":
        result = await retrieveSdtmRules(args[0], args[1]);
        break;
      case "propose":
        result = await proposeColumnMapping(args[0], args[1]);
        break;
      case "transform":
        const mapping = JSON.parse(args[2]);
        result = await transformToSdtm(args[0], args[1], mapping);
        break;
      case "validate":
        result = await validateSdtm(args[0], args[1]);
        break;
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
      default:
        throw new Error(`Unknown command: ${cmd}`);
    }

<<<<<<< HEAD
    // 输出 JSON 结果
    process.stdout.write(JSON.stringify(result, null, 2));
  } catch (err) {
    // 输出结构化错误，避免 PowerShell/流水线吞信息
    const payload = {
      error: err?.message || String(err),
      stack: err?.stack,
    };
    process.stdout.write(JSON.stringify(payload, null, 2));
=======
    console.log(JSON.stringify(result, null, 2));
    process.exit(0);
  } catch (err) {
    console.error(JSON.stringify({ error: err.message, stack: err.stack }, null, 2));
>>>>>>> 91b9a8b6bf8a44bf35c713853df7378ada863dcc
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = {
  readSourceData,
  retrieveSdtmRules,
  proposeColumnMapping,
  transformToSdtm,
  validateSdtm,
};
