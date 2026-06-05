/**
 * 文件上传 API
 * 处理前端上传的文件，保存到 data/uploads 目录
 */

import { writeFile, mkdir } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import Busboy from 'busboy';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '../..');
const uploadDir = join(projectRoot, 'data', 'uploads');

export const config = {
  api: {
    bodyParser: false,
  },
};

async function ensureUploadDir() {
  if (!existsSync(uploadDir)) {
    await mkdir(uploadDir, { recursive: true });
  }
}

function generateFileName(originalName) {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);
  const ext = originalName.split('.').pop();
  return `${timestamp}-${random}.${ext}`;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: '只支持 POST 请求' });
  }

  try {
    await ensureUploadDir();

    const busboy = Busboy({ headers: req.headers });
    let fileData = null;
    let fileName = 'file.xlsx';
    let domain = '';

    busboy.on('field', (fieldname, val) => {
      if (fieldname === 'domain') {
        domain = val;
      }
    });

    busboy.on('file', (fieldname, file, filename) => {
      fileName = filename.filename || filename || 'file.xlsx';
      const chunks = [];

      file.on('data', (chunk) => {
        chunks.push(chunk);
      });

      file.on('end', () => {
        fileData = Buffer.concat(chunks);
      });
    });

    busboy.on('finish', async () => {
      try {
        if (!fileData || fileData.length === 0) {
          return res.status(400).json({ error: '未接收到有效文件' });
        }

        const newFileName = generateFileName(fileName);
        const filePath = join(uploadDir, newFileName);
        await writeFile(filePath, fileData);

        const relativePath = `data/uploads/${newFileName}`;

        res.status(200).json({
          success: true,
          filePath: relativePath,
          fileName: fileName,
          domain: domain,
          message: `文件 ${fileName} 上传成功`,
        });
      } catch (error) {
        console.error('[upload] 处理错误:', error);
        res.status(500).json({
          error: '文件处理失败',
          message: error.message,
        });
      }
    });

    req.pipe(busboy);
  } catch (error) {
    console.error('[upload] 错误:', error);
    res.status(500).json({
      error: '文件上传失败',
      message: error.message,
    });
  }
}
