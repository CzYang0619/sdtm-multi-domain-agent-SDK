#!/usr/bin/env python
"""
Skill: 执行 SDTM 转换
"""
import sys
import json
import os
import pandas as pd
from core.sdtm_converter import SDTMTransformer

def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "Usage: transform.py <source_file> <domain> <mapping_json_file>"}, ensure_ascii=False))
        sys.exit(1)
    
    source_file = sys.argv[1]
    domain = sys.argv[2]
    mapping_json_file = sys.argv[3]
    
    try:
        # 读取源文件（传递domain参数进行筛选）
        if source_file.endswith(('.xlsx', '.xls')):
            df_source = pd.read_excel(source_file)
        elif source_file.endswith('.csv'):
            df_source = pd.read_csv(source_file)
        else:
            raise ValueError(f"Unsupported file format: {source_file}")
        
        # 根据域元数据进行行过滤（泛化设计）
        original_count = len(df_source)
        transformer = SDTMTransformer(domain)
        row_filter = transformer.metadata.get("row_filter")
        
        if row_filter:
            filter_col = row_filter.get("column")
            keep_values = row_filter.get("keep_values", [])
            
            if filter_col and filter_col in df_source.columns and keep_values:
                df_source = df_source[df_source[filter_col].isin(keep_values)].copy()
                filtered_count = len(df_source)
                print(f"[FILTER] {domain} domain: filtered {original_count} -> {filtered_count} records ({filter_col} in {keep_values})", file=sys.stderr)
        
        # 读取映射（如果提供了映射文件）
        mapping = {}
        if len(sys.argv) >= 4:
            mapping_json_file = sys.argv[3]
            if os.path.exists(mapping_json_file):
                with open(mapping_json_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
        
        # 如果没有映射或映射为空，自动生成映射
        if not mapping:
            print(f"[MAPPING] 自动生成 {domain} 域的列映射...", file=sys.stderr)
            transformer = SDTMTransformer(domain)
            schema = transformer.infer_source_schema(df_source)
            mapping = transformer.propose_mapping(schema)
            
            # 保存自动生成的映射
            auto_mapping_file = f"data/output/mapping_{domain}_auto.json"
            os.makedirs(os.path.dirname(auto_mapping_file), exist_ok=True)
            with open(auto_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            print(f"[MAPPING] 自动映射已保存到: {auto_mapping_file}", file=sys.stderr)
        
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("无法生成有效的列映射。")
        
        # 初始化转换器
        transformer = SDTMTransformer(domain)
        transformer.mapping = mapping
        
        # 标准化数据
        df_std, std_issues = transformer.standardize_data(df_source)
        
        # 应用映射
        df_sdtm, trans_issues = transformer.apply_mapping(df_std)
        
        # 输出到 session dir
        # 检查是否有STUDYID列来生成文件名
        study_id = None
        if 'STUDYID' in df_sdtm.columns:
            study_ids = df_sdtm['STUDYID'].dropna().unique()
            if len(study_ids) == 1:
                study_id = str(study_ids[0]).replace('-', '_')
        
        if study_id:
            output_filename = f"{study_id}_SDTM_{domain}.xlsx"
        else:
            output_filename = f"SDTM_{domain}.xlsx"
            
        output_path = os.path.join(os.getcwd(), output_filename)
        df_sdtm.to_excel(output_path, index=False, engine='openpyxl')
        
        result = {
            "success": True,
            "domain": domain,
            "output_file": output_path,
            "shape": list(df_sdtm.shape),
            "standardization_issues": std_issues,
            "transformation_issues": trans_issues,
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
