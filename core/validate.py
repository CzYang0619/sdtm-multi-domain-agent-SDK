#!/usr/bin/env python
"""
Skill: 验证 SDTM 数据质量
"""
import sys
import json
import pandas as pd
from core.sdtm_converter import ValidationReport

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: validate.py <sdtm_file> <domain>"}, ensure_ascii=False))
        sys.exit(1)
    
    sdtm_file = sys.argv[1]
    domain = sys.argv[2]
    
    try:
        # 读取 SDTM 文件
        if sdtm_file.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(sdtm_file)
        elif sdtm_file.endswith('.csv'):
            df = pd.read_csv(sdtm_file)
        else:
            raise ValueError(f"Unsupported file format: {sdtm_file}")
        
        # 验证
        validator = ValidationReport(domain, df)
        report = validator.validate()
        
        result = {
            "success": True,
            "validation_report": report,
        }
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
