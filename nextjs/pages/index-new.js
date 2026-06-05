/**
 * SDTM 转换 Web UI - Lab 2 风格
 * 
 * 功能：
 * - 输入表单（文件路径、域名）
 * - 实时日志控制台
 * - 进度条和状态指示器
 * - 流式事件显示
 * - 结果下载链接
 */

import React, { useState, useRef, useEffect } from "react";
import styles from "@/styles/converter.module.css";

export default function SDTMConverter() {
  const [sourceFile, setSourceFile] = useState("data/raw/CH3_ae.xlsx");
  const [domain, setDomain] = useState("AE");
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("idle"); // idle, running, success, error
  const [result, setResult] = useState(null);
  const logsEndRef = useRef(null);

  // 自动滚动到最新日志
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleConvert = async () => {
    if (!sourceFile.trim()) {
      alert("请输入源文件路径");
      return;
    }

    setIsRunning(true);
    setLogs([]);
    setProgress(0);
    setStatus("running");
    setResult(null);

    try {
      const response = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sourceFile: sourceFile.trim(),
          domain: domain || null,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              
              // 添加日志
              setLogs((prev) => [...prev, event]);

              // 更新进度
              if (event.type === "skill_start") {
                setProgress((prev) => Math.min(prev + 15, 85));
              } else if (event.type === "skill_result") {
                setProgress((prev) => Math.min(prev + 3, 88));
              } else if (event.type === "complete") {
                setProgress(100);
                setStatus("success");
                setResult(event);
              } else if (event.type === "error") {
                setStatus("error");
              }
            } catch (e) {
              console.error("Failed to parse SSE:", e);
            }
          }
        }
      }
    } catch (error) {
      setLogs((prev) => [
        ...prev,
        {
          type: "error",
          level: "error",
          message: `连接错误: ${error.message}`,
          timestamp: new Date().toISOString(),
        },
      ]);
      setStatus("error");
    } finally {
      setIsRunning(false);
    }
  };

  const handleClear = () => {
    setLogs([]);
    setProgress(0);
    setStatus("idle");
    setResult(null);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>🔬 SDTM 智能转换系统</h1>
        <p>基于 GitHub Copilot SDK 的生产级 Agent</p>
      </div>

      {/* 输入表单 */}
      <div className={styles.panel}>
        <h2>📝 转换设置</h2>
        <div className={styles.formGroup}>
          <label>源数据文件路径</label>
          <input
            type="text"
            value={sourceFile}
            onChange={(e) => setSourceFile(e.target.value)}
            placeholder="例如: data/raw/CH3_ae.xlsx"
            disabled={isRunning}
            className={styles.input}
          />
          <small>支持 Excel 和 CSV 格式</small>
        </div>

        <div className={styles.formGroup}>
          <label>SDTM 域（可选）</label>
          <select
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={isRunning}
            className={styles.select}
          >
            <option value="">自动检测</option>
            <option value="AE">AE - 不良事件</option>
            <option value="CM">CM - 伴随用药</option>
            <option value="LB">LB - 实验室检查</option>
            <option value="VS">VS - 生命体征</option>
            <option value="DM">DM - 人口统计学</option>
          </select>
          <small>不确定时可留空，系统会自动检测</small>
        </div>

        <div className={styles.actions}>
          <button
            onClick={handleConvert}
            disabled={isRunning}
            className={`${styles.button} ${styles.primary}`}
          >
            {isRunning ? "⏳ 转换中..." : "🚀 开始转换"}
          </button>
          <button
            onClick={handleClear}
            disabled={isRunning}
            className={styles.button}
          >
            🗑️ 清空
          </button>
        </div>
      </div>

      {/* 进度条 */}
      {(isRunning || progress > 0) && (
        <div className={styles.panel}>
          <div className={styles.progressContainer}>
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill}
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className={styles.progressText}>{progress}%</span>
          </div>
          <p className={styles.status}>
            {status === "running" && "🔄 正在处理中..."}
            {status === "success" && "✅ 成功完成"}
            {status === "error" && "❌ 出现错误"}
          </p>
        </div>
      )}

      {/* 结果面板 */}
      {result && status === "success" && (
        <div className={`${styles.panel} ${styles.success}`}>
          <h3>✅ 转换成功</h3>
          <p>{result.message}</p>
          <div className={styles.files}>
            <p><strong>输出文件：</strong></p>
            <ul>
              <li>📊 {result.files?.sdtmFile}</li>
              <li>🗂️ {result.files?.mappingFile}</li>
              <li>📋 {result.files?.reportFile}</li>
            </ul>
            <p><strong>位置：</strong> {result.outputDir}</p>
            {result.duration && <p><strong>耗时：</strong> {result.duration} 秒</p>}
          </div>
        </div>
      )}

      {/* 日志控制台 */}
      <div className={styles.panel}>
        <h2>📜 实时日志</h2>
        <div className={styles.console}>
          {logs.length === 0 ? (
            <div className={styles.placeholder}>
              准备就绪，等待转换...
            </div>
          ) : (
            logs.map((log, idx) => (
              <div
                key={idx}
                className={`${styles.logLine} ${styles[`log-${log.type}`]}`}
              >
                <span className={styles.time}>
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={styles.type}>[{log.type}]</span>
                <span className={styles.message}>
                  {log.message || log.skillName || JSON.stringify(log).slice(0, 100)}
                </span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* 技术信息 */}
      <div className={styles.footer}>
        <p>
          <strong>🤖 Copilot SDK Agent</strong> - 
          自主规划、自主决策、自动重试 |
          <strong> 5 个 Skills </strong> - 
          自动编排调用
        </p>
      </div>
    </div>
  );
}
