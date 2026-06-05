from flask import Flask, request, jsonify, send_from_directory
import os
from werkzeug.utils import secure_filename

# 使用项目中的转换入口
from core.sdtm_converter import process_sdtm_conversion

# 项目路径配置（与 core 模块路径一致）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")

os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder="web_ui", static_url_path="")

@app.route('/')
def index():
    # 返回前端页面
    return app.send_static_file('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    try:
        domain = (request.form.get('domain') or 'AE').upper()

        # 优先使用上传文件
        uploaded = request.files.get('file')
        if uploaded and uploaded.filename:
            filename = secure_filename(uploaded.filename)
            save_path = os.path.join(RAW_DATA_DIR, filename)
            uploaded.save(save_path)
            source_file = filename
        else:
            # 可直接填写 data/raw 下的文件名或绝对路径
            source_file = request.form.get('source_file') or 'CH3_ae.xlsx'

        ok, result = process_sdtm_conversion(source_file=source_file, domain=domain, output_dir=OUTPUT_DIR)

        if ok:
            return jsonify({
                'ok': True,
                'sdtm_file': result.get('sdtm_file'),
                'mapping_file': result.get('mapping_file'),
                'report_file': result.get('report_file'),
                'details': result,
            })
        else:
            return jsonify({'ok': False, 'errors': result.get('errors', []), 'details': result}), 400

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/outputs/<path:filename>')
def outputs(filename):
    # 提供转换后的文件下载
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    # 开发模式下在本地运行
    app.run(host='127.0.0.1', port=8000, debug=True)
