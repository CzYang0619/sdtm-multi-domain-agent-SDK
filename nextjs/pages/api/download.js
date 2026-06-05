/**
 * 文件下载 API
 * 允许用户下载转换后的文件
 */

import { readFile, stat } from 'node:fs/promises';
import { join, basename } from 'node:path';
import { existsSync } from 'node:fs';

export default async function handler(req, res) {
  const { file } = req.query;

  if (!file) {
    return res.status(400).json({ error: '缺少文件参数' });
  }

  try {
    // 安全检查：防止目录遍历攻击
    const normalizedPath = join(process.cwd(), file);
    const projectRoot = process.cwd();

    if (!normalizedPath.startsWith(projectRoot)) {
      return res.status(403).json({ error: '访问被拒绝' });
    }

    // 检查文件是否存在
    if (!existsSync(normalizedPath)) {
      return res.status(404).json({ error: '文件不存在' });
    }

    // 获取文件信息
    const fileStats = await stat(normalizedPath);
    if (!fileStats.isFile()) {
      return res.status(400).json({ error: '不是有效的文件' });
    }

    // 读取文件
    const fileContent = await readFile(normalizedPath);
    const fileName = basename(normalizedPath);

    // 设置响应头
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(fileName)}"`);
    res.setHeader('Content-Length', fileStats.size);

    // 发送文件
    res.send(fileContent);
  } catch (error) {
    console.error('[download] 错误:', error);
    res.status(500).json({
      error: '文件下载失败',
      message: error.message,
    });
  }
}
