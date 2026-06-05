#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SDTM 智能 Agent - Copilot Chat 驱动
支持多个入口：
1. MCP skills（从 Copilot Chat 调用）
2. Python API（直接调用）
3. CLI（命令行）
"""

import os
import sys
import json
import glob
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# 强制 UTF-8 编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from core.sdtm_converter import (
    process_sdtm_conversion,
    DOMAIN_METADATA,
    ValidationReport
)
from core.rag_retriever import get_retriever, format_retrieved


# 获取项目根目录（agent.py 所在目录）
PROJECT_ROOT = Path(__file__).parent.absolute()


class SDTMAgent:
    """SDTM 智能转换 Agent - 核心引擎"""
    
    def __init__(self, work_dir: str = None):
        # 如果不指定 work_dir，默认使用项目根目录（不是当前工作目录）
        if work_dir is None:
            work_dir = str(PROJECT_ROOT)
        
        self.work_dir = Path(work_dir)
        self.data_raw = self.work_dir / "data" / "raw"
        self.data_output = self.work_dir / "data" / "output"
        self.data_output.mkdir(parents=True, exist_ok=True)
        
        # RAG 检索器
        rag_store = self.work_dir / "rag_store"
        self.retriever = get_retriever(str(rag_store)) if rag_store.exists() else None
        
        # 工作流状态
        self.state = {}
    
    @staticmethod
    def _format_validation_summary(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """格式化验证问题摘要（聚合低缺失率的 info 消息）"""
        summary = {"error": 0, "warning": 0, "info": 0, "issues": []}
        
        for issue in issues:
            severity = issue.get("severity", "info")
            summary[severity] += 1
            
            # 保留所有错误和警告
            if severity in ["error", "warning"]:
                summary["issues"].append(issue)
            # info 级别的消息：只保留汇总消息或高缺失率（> 1%）的消息
            elif issue.get("type") == "minor_missing_in_expected_vars":
                # 这是已聚合的低缺失率汇总
                summary["issues"].append(issue)
            elif issue.get("percentage", 0) >= 1.0:
                # 保留缺失率 >= 1% 的 info 消息
                summary["issues"].append(issue)
            # 否则忽略缺失率 < 1% 的单个 info 消息（已被汇总）
        
        return summary
    
    def detect_domain(self, df: pd.DataFrame, filename: str = "") -> Optional[str]:
        """自动识别数据域"""
        domain_markers = {
            "AE": "AEYN",
            "CM": "CMYN",
            "LB": "LBYN",
            "VS": "VSYN",
            "DM": "DMPOP"
        }
        
        # 优先从列标记检测
        for domain, marker in domain_markers.items():
            if marker in df.columns:
                return domain
        
        # 次优先从文件名检测
        filename_upper = filename.upper()
        for domain in DOMAIN_METADATA.keys():
            if domain in filename_upper:
                return domain
        
        return None
    
    def validate_source_file(self, filepath: str) -> Tuple[bool, str]:
        """验证源文件"""
        path = Path(filepath)
        
        if not path.is_absolute():
            path = self.data_raw / filepath
        
        if not path.exists():
            return False, f"文件不存在: {path}"
        
        if not path.suffix.lower() in ['.xlsx', '.xls', '.csv']:
            return False, f"不支持的文件格式: {path.suffix}"
        
        try:
            if path.suffix.lower() in ['.xlsx', '.xls']:
                pd.read_excel(path, nrows=1)
            else:
                pd.read_csv(path, nrows=1)
            return True, "ok"
        except Exception as e:
            return False, f"文件读取失败: {e}"
    
    def step_1_read_source(self, filepath: str) -> Dict[str, Any]:
        """
        工作流步骤 1: 读取源数据
        对应 MCP skill: read_source_data
        """
        valid, msg = self.validate_source_file(filepath)
        if not valid:
            return {"success": False, "error": msg}
        
        path = Path(filepath)
        if not path.is_absolute():
            path = self.data_raw / filepath
        
        try:
            if path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path)
            
            self.state['source_file'] = str(path)
            self.state['source_df'] = df
            self.state['record_count'] = len(df)
            
            return {
                "success": True,
                "file": str(path),
                "records": len(df),
                "columns": list(df.columns),
                "shape": df.shape
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def step_2_detect_domain(self) -> Dict[str, Any]:
        """
        工作流步骤 2: 自动检测或确认域
        对应 MCP skill: propose_column_mapping（包含域检测）
        """
        if 'source_df' not in self.state:
            return {"success": False, "error": "未读取源数据"}
        
        df = self.state['source_df']
        source_file = self.state.get('source_file', '')
        
        detected = self.detect_domain(df, source_file)
        
        if detected is None:
            supported = ", ".join(DOMAIN_METADATA.keys())
            return {
                "success": False,
                "error": f"无法自动检测域。支持的域: {supported}",
                "candidates": []
            }
        
        self.state['domain'] = detected
        
        return {
            "success": True,
            "domain": detected,
            "description": DOMAIN_METADATA[detected]["description"],
            "required_vars": DOMAIN_METADATA[detected]["required_vars"]
        }
    
    def step_3_retrieve_rules(self, query: str = None, domain: str = None) -> Dict[str, Any]:
        """
        工作流步骤 3: 检索 SDTM 规范
        对应 MCP skill: retrieve_sdtm_rules
        """
        if domain is None:
            domain = self.state.get('domain', 'AE')
        
        if not self.retriever:
            return {
                "success": False,
                "error": "RAG 检索器未初始化"
            }
        
        # 构造查询
        if query is None:
            query = f"Domain {domain} requirements and mandatory variables"
        else:
            query = f"[{domain}] {query}"
        
        try:
            chunks = self.retriever.retrieve(query, top_k=5)
            
            self.state['retrieved_rules'] = {
                "query": query,
                "chunks_count": len(chunks),
                "content": format_retrieved(chunks)
            }
            
            return {
                "success": True,
                "query": query,
                "chunks_count": len(chunks),
                "formatted": format_retrieved(chunks)
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"规范查询失败: {e}"
            }
    
    def step_4_propose_mapping(self) -> Dict[str, Any]:
        """
        工作流步骤 4: 提议列映射
        对应 MCP skill: propose_column_mapping
        """
        if 'source_df' not in self.state or 'domain' not in self.state:
            return {
                "success": False,
                "error": "未完成前置步骤"
            }
        
        domain = self.state['domain']
        
        # 这里简化处理，实际会由 core 模块的映射逻辑处理
        # 此处仅记录状态，实际映射在 transform 步骤执行
        mapping = {
            "mapped": True,
            "domain": domain,
            "required_vars": DOMAIN_METADATA[domain]["required_vars"]
        }
        
        self.state['mapping'] = mapping
        
        return {
            "success": True,
            "domain": domain,
            "mapping_ready": True
        }
    
    def step_5_transform(self) -> Dict[str, Any]:
        """
        工作流步骤 5: 执行转换
        对应 MCP skill: transform_to_sdtm
        """
        if 'source_file' not in self.state or 'domain' not in self.state:
            return {
                "success": False,
                "error": "未完成前置步骤"
            }
        
        source_path = Path(self.state['source_file'])
        domain = self.state['domain']
        
        try:
            success, result = process_sdtm_conversion(
                source_path.name,
                domain,
                str(self.data_output)
            )
            
            if not success:
                error_msg = result.get('errors', [{}])[0].get('error', '未知错误')
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # 查找输出文件
            pattern = str(self.data_output / f"SDTM_{domain}*.xlsx")
            output_files = glob.glob(pattern)
            if not output_files:
                return {
                    "success": False,
                    "error": "转换后未找到输出文件"
                }
            
            sdtm_file = output_files[0]
            self.state['output_file'] = sdtm_file
            
            return {
                "success": True,
                "output_file": sdtm_file,
                "domain": domain
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"转换异常: {e}"
            }
    
    def step_6_validate(self) -> Dict[str, Any]:
        """
        工作流步骤 6: 验证数据质量
        对应 MCP skill: validate_sdtm
        """
        if 'output_file' not in self.state or 'domain' not in self.state:
            return {
                "success": False,
                "error": "未完成前置步骤"
            }
        
        output_file = self.state['output_file']
        domain = self.state['domain']
        
        try:
            from core.sdtm_converter import ValidationReport
            
            sdtm_df = pd.read_excel(output_file)
            
            # 使用 ValidationReport 生成完整的验证报告
            validator = ValidationReport(domain, sdtm_df)
            validation_report = validator.validate()
            
            # 生成报告文件
            report_file = self.data_output / f"report_{domain}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(validation_report, f, ensure_ascii=False, indent=2)
            
            self.state['report_file'] = str(report_file)
            
            # 生成摘要（用于显示）
            issues = validation_report.get("issues", [])
            summary = self._format_validation_summary(issues)
            
            return {
                "success": True,
                "record_count": int(sdtm_df.shape[0]),
                "column_count": int(sdtm_df.shape[1]),
                "quality_summary": summary,
                "report_file": report_file
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"验证异常: {e}"
            }
    
    def convert(self, source_file: str, domain: Optional[str] = None, verbose: bool = True) -> Dict[str, Any]:
        """
        完整转换工作流
        这是 Agent 的主入口，支持：
        1. 直接 Python 调用
        2. MCP skills 调用
        3. CLI 调用
        """
        if verbose:
            print("\n" + "=" * 70)
            print("SDTM 智能转换 Agent - 开始工作流")
            print("=" * 70)
        
        # 步骤 1: 读取源数据
        if verbose:
            print("\n[步骤 1] 读取源数据...")
        result = self.step_1_read_source(source_file)
        if not result["success"]:
            return {
                "success": False,
                "error": result["error"],
                "source_file": source_file
            }
        if verbose:
            print(f"  ✓ 读取成功: {result['records']} 条记录")
        
        # 步骤 2: 检测或确认域
        if domain is None:
            if verbose:
                print("\n[步骤 2] 自动检测数据域...")
            result = self.step_2_detect_domain()
            if not result["success"]:
                return {
                    "success": False,
                    "error": result["error"]
                }
            domain = result["domain"]
            if verbose:
                print(f"  ✓ 检测到域: {domain} - {result['description']}")
        else:
            self.state['domain'] = domain
            if verbose:
                print(f"\n[步骤 2] 使用指定的域: {domain}")
        
        # 步骤 3: 检索规范
        if verbose:
            print("\n[步骤 3] 检索 SDTM 规范...")
        result = self.step_3_retrieve_rules(domain=domain)
        if result["success"]:
            if verbose:
                print(f"  ✓ 检索到 {result['chunks_count']} 个规范条文")
        else:
            if verbose:
                print(f"  ⚠️  规范检索失败: {result.get('error', '未知错误')}")
        
        # 步骤 4: 提议映射
        if verbose:
            print("\n[步骤 4] 分析列映射...")
        result = self.step_4_propose_mapping()
        if result["success"]:
            if verbose:
                print(f"  ✓ 映射分析完成")
        
        # 步骤 5: 执行转换
        if verbose:
            print("\n[步骤 5] 执行数据转换...")
        result = self.step_5_transform()
        if not result["success"]:
            return {
                "success": False,
                "error": result["error"]
            }
        if verbose:
            print(f"  ✓ 转换完成: {result['output_file']}")
        
        # 步骤 6: 验证
        if verbose:
            print("\n[步骤 6] 数据质量验证...")
        result = self.step_6_validate()
        if not result["success"]:
            return {
                "success": False,
                "error": result["error"]
            }
        
        quality_summary = result.get('quality_summary', {})
        error_count = quality_summary.get('error', 0)
        warning_count = quality_summary.get('warning', 0)
        info_count = quality_summary.get('info', 0)
        
        if verbose:
            msg = f"  ✓ 验证完成: {error_count} 个错误, {warning_count} 个警告"
            if info_count > 0:
                msg += f", {info_count} 条信息"
            print(msg)
        
        # 最终输出
        final_result = {
            "success": True,
            "domain": domain,
            "source_file": self.state['source_file'],
            "output_file": self.state['output_file'],
            "report_file": result['report_file'],
            "record_count": result['record_count'],
            "column_count": result['column_count'],
            "quality_summary": {
                "errors": error_count,
                "warnings": warning_count,
                "info": info_count
            }
        }
        
        if verbose:
            print("\n" + "=" * 70)
            print("✅ 转换工作流完成!")
            print("=" * 70)
            print(f"\n输出统计:")
            print(f"  记录数: {result['record_count']}")
            print(f"  列数: {result['column_count']}")
            print(f"\n质量检查: 错误={error_count}, 警告={warning_count}, 信息={info_count}")
            print(f"\n输出文件:")
            print(f"  - 数据: {self.state['output_file']}")
            print(f"  - 报告: {result['report_file']}")
            print("\n" + "=" * 70)
        
        return final_result


# ============ MCP Skills 入口（被 MCP 服务器调用） ============

def mcp_read_source_data(source_path: str) -> Dict[str, Any]:
    """MCP skill: 读取源数据"""
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
    return agent.step_1_read_source(source_path)


def mcp_retrieve_sdtm_rules(query: str, domain: Optional[str] = None) -> Dict[str, Any]:
    """MCP skill: 检索规范"""
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
    return agent.step_3_retrieve_rules(query=query, domain=domain)


def mcp_propose_column_mapping(source_path: str, domain: str) -> Dict[str, Any]:
    """MCP skill: 提议映射"""
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
    agent.step_1_read_source(source_path)
    return agent.step_4_propose_mapping()


def mcp_transform_to_sdtm(source_path: str, domain: str) -> Dict[str, Any]:
    """MCP skill: 执行转换"""
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
    agent.step_1_read_source(source_path)
    agent.state['domain'] = domain
    return agent.step_5_transform()


def mcp_validate_sdtm(sdtm_path: str, domain: str) -> Dict[str, Any]:
    """MCP skill: 验证数据"""
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
    # 确保 sdtm_path 是绝对路径
    sdtm_path_obj = Path(sdtm_path)
    if not sdtm_path_obj.is_absolute():
        sdtm_path_obj = agent.data_output / sdtm_path_obj.name
    agent.state['output_file'] = str(sdtm_path_obj)
    agent.state['domain'] = domain
    return agent.step_6_validate()


# ============ CLI 入口 ============

def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python agent.py <source_file> [domain]")
        print("\n示例:")
        print("  python agent.py CH3_ae.xlsx          # 自动检测域")
        print("  python agent.py CH3_ae.xlsx AE       # 指定 AE 域")
        sys.exit(1)
    
    source_file = sys.argv[1]
    domain = sys.argv[2] if len(sys.argv) > 2 else None
    
    agent = SDTMAgent(work_dir=str(PROJECT_ROOT))
