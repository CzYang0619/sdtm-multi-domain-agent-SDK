#!/usr/bin/env python
"""
Skill: 读取源数据并分析结构
输出 JSON 到 stdout
"""
import sys
import json
import pandas as pd
from core.sdtm_converter import SDTMTransformer

def _json_safe(v):
    """将 pandas/numpy 类型转换成可 JSON 序列化的基础类型。"""
    if v is None:
        return None

    # pandas Timestamp / datetime-like
    try:
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
    except Exception:
        pass

    # numpy scalar
    try:
        import numpy as np

        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
    except Exception:
        pass

    # python datetime/date
    try:
        from datetime import datetime, date

        if isinstance(v, (datetime, date)):
            return v.isoformat()
    except Exception:
        pass

    # 其它类型：转字符串兜底
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: read_source.py <source_file> [domain]"}, ensure_ascii=False))
        sys.exit(1)
    
    source_file = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        # 读取文件
        if source_file.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(source_file)
        elif source_file.endswith('.csv'):
            df = pd.read_csv(source_file)
        else:
            raise ValueError(f"Unsupported file format: {source_file}")
        
        # 根据域类型筛选相关记录
        original_count = len(df)
        if domain == "AE" and "AEYN" in df.columns:
            # AE域：只保留AEYN='Yes'的记录
            df = df[df["AEYN"] == "Yes"].copy()
            print(f"[FILTER] AE domain: filtered {original_count} -> {len(df)} records (AEYN='Yes')", file=sys.stderr)
        elif domain == "CM" and "CMYN" in df.columns:
            # CM域：只保留CMYN='Yes'的记录
            df = df[df["CMYN"] == "Yes"].copy()
            print(f"[FILTER] CM domain: filtered {original_count} -> {len(df)} records (CMYN='Yes')", file=sys.stderr)
        elif domain == "LB" and "LBYN" in df.columns:
            # LB域：只保留LBYN='Yes'的记录
            df = df[df["LBYN"] == "Yes"].copy()
            print(f"[FILTER] LB domain: filtered {original_count} -> {len(df)} records (LBYN='Yes')", file=sys.stderr)
        
        # 分析源数据
        sample = {}
        for col in df.columns:
            vals = df[col].dropna().head(1).tolist()
            sample[col] = [_json_safe(x) for x in vals]

        result = {
            "success": True,
            "original_records": original_count,
            "filtered_records": len(df),
            "shape": [int(df.shape[0]), int(df.shape[1])],
            "columns": list(df.columns),
            "dtypes": {col: str(df[col].dtype) for col in df.columns},
            "missing_rate": {col: float(df[col].isna().sum() / len(df)) for col in df.columns},
            "sample": sample,
        }
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
