#!/usr/bin/env python
"""
Skill: 提议列映射方案
"""
import sys
import json
import pandas as pd
from core.sdtm_converter import SDTMTransformer

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: propose_mapping.py <source_file> <domain>"}, ensure_ascii=False))
        sys.exit(1)
    
    source_file = sys.argv[1]
    domain = sys.argv[2]
    
    try:
        # 读取源文件
        if source_file.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(source_file)
        elif source_file.endswith('.csv'):
            df = pd.read_csv(source_file)
        else:
            raise ValueError(f"Unsupported file format: {source_file}")
        
        # 初始化转换器
        transformer = SDTMTransformer(domain)
        
        # 分析源数据
        schema = transformer.infer_source_schema(df)
        
        # 提议映射
        mapping = transformer.propose_mapping(schema)
        
        result = {
            "success": True,
            "domain": domain,
            "proposed_mapping": mapping,
            "issues": transformer.issues,
            "unmapped_columns": [
                col for col in df.columns 
                if col not in mapping
            ],
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
