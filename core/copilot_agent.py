#!/usr/bin/env python
"""
Copilot SDK Integration - SDTM Multi-Domain Agent
该脚本可被 Copilot SDK 的 Node.js 后端直接调用
"""
import os
import sys
import json
import tempfile
from pathlib import Path

# 假设工作目录是 session dir
from core.sdtm_converter import (
    SDTMTransformer, 
    ValidationReport, 
    process_sdtm_conversion,
    DOMAIN_METADATA
)
from core.rag_retriever import get_retriever, format_retrieved


class SDTMCopilotAgent:
    """Copilot SDK Agent 接口"""
    
    SYSTEM_PROMPT = """
你是一名高级临床数据 AI 程序员，擅长多域 SDTM 转换。你必须遵循 SDTMIG v3.3 规范。

## 支持的医学数据域（SDTM Domains）
- **AE（不良事件）**：用于记录研究期间发生的不良事件。
- **CM（伴随用药）**：用于记录研究期间的伴随用药信息。
- **LB（实验室检查）**：用于记录实验室检测结果。
- **VS（生命体征）**：用于记录血压、心率等生命体征数据。
- **DM（人口统计学）**：用于记录受试者的人口学特征（年龄、性别、种族等）。

## 工作流（必须按顺序）

1. **识别目标域**：如果用户未明确指定，根据文件内容自动检测（文件名、列名、样本值）。
2. **调用 read_source_data skill**：分析源数据的列名、数据类型、缺失率、样本值。
3. **调用 retrieve_sdtm_rules skill**：查询对应域的 SDTMIG 规范要求和关键变量定义。
4. **调用 propose_column_mapping skill**：提议源列与 SDTM 标准列的对应关系，标记缺失的必需字段。
5. **获取用户确认**（如有歧义）：显示映射预览，请用户确认或提供派生规则。
6. **调用 transform_to_sdtm skill**：执行转换、标准化、生成 SDTM 表。
7. **调用 validate_sdtm skill**：进行质量检查（必需变量完整性、缺失率、序列号连续性）。
8. **生成最终报告**：包括映射关系 JSON、数据质量问题、修复建议。

## 必须规避的错误

- **STUDYID/USUBJID**：不能盲目选择；必须先看数据取值，再选择更合理的列。
- **日期格式**：必须转为 ISO 8601 格式（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS）。
- **受控术语映射**：需按 SDTM 标准列表或本地编码表映射，不得低阈值强配。
- **必需变量缺失**：若映射中缺少任何必填变量（Req），必须追问用户或标记为错误。
- **序列号**：如果域有 key_sequence_var（如 AESEQ、CMSEQ），必须按记录顺序递增分配（1,2,3,...）。
- **数据丢失**：禁止默认过滤记录；除非用户明确要求。

## 输出要求

- **SDTM_{domain}.xlsx**：转换后的数据表，包含所有必需和期望变量。
- **mapping_{domain}.json**：源列 → SDTM 列的映射关系文档（便于人工审核）。
- **report_{domain}.json**：数据质量报告（问题列表、严重级别、摘要统计）。

## 交互指南

- 如果用户只给文件路径，不给域名：询问用户这是哪个 SDTM 域的数据。
- 如果检测到映射缺陷：标记问题，请用户补充信息或确认派生规则。
- 如果数据质量差（>50% 缺失）：警告用户，确认是否继续。
- 最终完成：总结输出文件位置、映射关系、问题清单。

## 关键原则

1. **规范优先**：始终遵循 SDTMIG v3.3，不得因方便而破坏规范。
2. **完整性优先**：所有必需变量必须存在，不能跳过。
3. **可追踪性**：导出映射和报告，便于审计和复查。
4. **用户参与**：在关键决策点追问用户，不要假设。
""".strip()
    
    def __init__(self, session_dir: str):
        self.session_dir = session_dir
        # 尝试从多个位置找到 rag_store
        possible_rag_stores = [
            os.path.join(os.path.dirname(__file__), "rag_store"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "sdtm-multi-domain-agent", "rag_store"),
            "rag_store",
        ]
        
        self.rag_store = None
        for path in possible_rag_stores:
            if os.path.exists(os.path.join(path, "sdtmig.faiss")):
                self.rag_store = os.path.abspath(path)
                break
        
        # 如果没找到，用默认路径（会在使用时报错）
        if not self.rag_store:
            self.rag_store = os.path.join(os.path.dirname(__file__), "rag_store")
        
    def list_supported_domains(self) -> dict:
        """列出支持的域"""
        return {
            "domains": list(DOMAIN_METADATA.keys()),
            "descriptions": {
                domain: DOMAIN_METADATA[domain]["description"]
                for domain in DOMAIN_METADATA.keys()
            }
        }
    
    def read_and_analyze_source(self, source_path: str) -> dict:
        """读取并分析源数据"""
        import pandas as pd
        
        if not os.path.exists(source_path):
            return {"error": f"Source file not found: {source_path}"}
        
        try:
            if source_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(source_path)
            elif source_path.endswith('.csv'):
                df = pd.read_csv(source_path)
            else:
                return {"error": f"Unsupported file format: {source_path}"}
            
            transformer = SDTMTransformer("AE")  # 暂时用 AE 只是为了 infer_source_schema
            schema = transformer.infer_source_schema(df)
            
            return {
                "success": True,
                "shape": list(df.shape),
                "columns": schema["columns"],
                "dtypes": schema["dtypes"],
                "missing_rate": schema.get("missing_rates", {}),
                "missing_rates": schema.get("missing_rates", {}),
                "sample_values": schema["sample_values"],
            }
        except Exception as e:
            return {"error": str(e)}
    
    def retrieve_sdtm_specification(self, query: str, domain: str = None) -> dict:
        """检索 SDTM 规范"""
        try:
            if not self.rag_store or not os.path.exists(self.rag_store):
                return {
                    "success": False,
                    "error": f"RAG store not found at {self.rag_store}",
                    "query": query,
                    "domain": domain
                }
            
            retriever = get_retriever(self.rag_store)
            
            # 如果指定了域，增强查询
            if domain:
                enhanced_query = f"[{domain}] {query}"
            else:
                enhanced_query = query
            
            chunks = retriever.retrieve(enhanced_query, top_k=5)
            
            return {
                "success": True,
                "query": query,
                "domain": domain,
                "chunks_count": len(chunks),
                "results": [
                    {
                        "page": c.page,
                        "score": round(float(c.score), 4),
                        "text": c.text,
                    }
                    for c in chunks
                ],
                "formatted": format_retrieved(chunks),
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "query": query,
                "domain": domain
            }
            return {"error": str(e)}
    
    def propose_mapping_strategy(self, source_path: str, domain: str) -> dict:
        """提议映射策略（包含 RAG 规范参考）"""
        import pandas as pd
        
        if domain not in DOMAIN_METADATA:
            return {"error": f"Unsupported domain: {domain}"}
        
        if not os.path.exists(source_path):
            return {"error": f"Source file not found: {source_path}"}
        
        try:
            if source_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(source_path)
            elif source_path.endswith('.csv'):
                df = pd.read_csv(source_path)
            else:
                return {"error": f"Unsupported file format: {source_path}"}
            
            # 先检索该域的规范
            rag_result = self.retrieve_sdtm_specification(
                f"Domain {domain} required variables and standards",
                domain=domain
            )
            rag_context = rag_result.get("formatted", "") if rag_result.get("success") else ""
            
            transformer = SDTMTransformer(domain)
            schema = transformer.infer_source_schema(df)
            mapping = transformer.propose_mapping(schema, rag_context=rag_context)
            
            return {
                "success": True,
                "domain": domain,
                "proposed_mapping": mapping,
                "required_vars": DOMAIN_METADATA[domain]["required_vars"],
                "expected_vars": DOMAIN_METADATA[domain]["expected_vars"],
                "unmapped_columns": [
                    col for col in schema["columns"]
                    if col not in mapping
                ],
                "rag_context_available": bool(rag_context),
                "issues": transformer.issues,
                "guidance": self._generate_mapping_guidance(transformer.issues),
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    
    def execute_conversion(self, source_path: str, domain: str, mapping: dict = None) -> dict:
        """执行 SDTM 转换"""
        import pandas as pd
        
        if domain not in DOMAIN_METADATA:
            return {"success": False, "error": f"Unsupported domain: {domain}"}
        
        if not os.path.exists(source_path):
            return {"success": False, "error": f"Source file not found: {source_path}"}
        
        try:
            if source_path.endswith(('.xlsx', '.xls')):
                df_source = pd.read_excel(source_path)
            elif source_path.endswith('.csv'):
                df_source = pd.read_csv(source_path)
            else:
                return {"success": False, "error": f"Unsupported file format: {source_path}"}
            
            transformer = SDTMTransformer(domain)
            
            # 如果提供了映射，使用；否则自动提议
            if mapping is None:
                schema = transformer.infer_source_schema(df_source)
                mapping = transformer.propose_mapping(schema)
            else:
                # 确保 mapping 是字典
                if isinstance(mapping, str):
                    mapping = json.loads(mapping)
                transformer.mapping = mapping
            
            # 标准化
            df_std, std_issues = transformer.standardize_data(df_source)
            
            # 转换
            df_sdtm, trans_issues = transformer.apply_mapping(df_std)
            
            # 验证
            validator = ValidationReport(domain, df_sdtm)
            validation_report = validator.validate()
            
            # 确保 session_dir 存在
            os.makedirs(self.session_dir, exist_ok=True)
            
            # 输出文件
            sdtm_file = os.path.join(self.session_dir, f"SDTM_{domain}.xlsx")
            df_sdtm.to_excel(sdtm_file, index=False, engine='openpyxl')
            
            mapping_file = os.path.join(self.session_dir, f"mapping_{domain}.json")
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
            
            report_file = os.path.join(self.session_dir, f"report_{domain}.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(validation_report, f, indent=2, ensure_ascii=False)
            
            # 确保所有返回值都是可序列化的
            return {
                "success": True,
                "domain": domain,
                "output_shape": list(df_sdtm.shape),
                "sdtm_file": str(sdtm_file),
                "mapping_file": str(mapping_file),
                "report_file": str(report_file),
                "rows_processed": int(len(df_sdtm)),
                "columns_created": int(len(df_sdtm.columns)),
                "validation_issue_count": len(validation_report.get("issues", [])),
                "validation_errors": len([i for i in validation_report.get("issues", []) if i.get("severity") == "error"]),
                "validation_warnings": len([i for i in validation_report.get("issues", []) if i.get("severity") == "warning"]),
            }
        
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "domain": domain
            }
    
    def _generate_mapping_guidance(self, issues: list) -> str:
        """生成映射指导"""
        if not issues:
            return "Mapping looks good! Proceed with conversion."
        
        guidance = "Mapping Issues Found:\n"
        for issue in issues:
            if issue["type"] == "missing_required_var":
                guidance += f"⚠️  Required variable '{issue['var']}' is missing. " \
                           f"Please specify which source column maps to it, or provide a derivation rule.\n"
        
        return guidance


def main():
    """CLI 入口（用于测试或被外部调用）"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: copilot_agent.py <command> [args...]"}, ensure_ascii=False))
        sys.exit(1)
    
    # 使用当前工作目录作为 session dir
    agent = SDTMCopilotAgent(os.getcwd())
    
    command = sys.argv[1]
    
    try:
        if command == "list_domains":
            result = agent.list_supported_domains()
        elif command == "read":
            result = agent.read_and_analyze_source(sys.argv[2])
        elif command == "retrieve":
            domain = sys.argv[3] if len(sys.argv) > 3 else None
            result = agent.retrieve_sdtm_specification(sys.argv[2], domain)
        elif command == "propose":
            result = agent.propose_mapping_strategy(sys.argv[2], sys.argv[3])
        elif command == "convert":
            mapping = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
            result = agent.execute_conversion(sys.argv[2], sys.argv[3], mapping)
        else:
            result = {"error": f"Unknown command: {command}"}
        
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
