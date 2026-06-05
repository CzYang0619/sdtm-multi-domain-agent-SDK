"""
多域 SDTM 转换核心逻辑 - 支持 AE, CM, LB, VS, DM 等
泛化设计，通过元数据驱动
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import os
import pandas as pd
import numpy as np
import json
import traceback
import sys

# ============ 数据路径配置（泛化设计） ============
# 获取项目根目录（agent.py 所在目录，而不是 core/ 所在目录）
# 注意：core/sdtm_converter.py 在 core/ 子目录，所以需要向上两级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
REFERENCE_DATA_DIR = os.path.join(DATA_DIR, "reference")
OUTPUT_DATA_DIR = os.path.join(DATA_DIR, "output")

# 确保输出目录存在
os.makedirs(OUTPUT_DATA_DIR, exist_ok=True)

# 域元数据：定义每个 SDTM 域的必需/期望变量及处理策略
DOMAIN_METADATA = {
    "AE": {
        "description": "Adverse Events",
        "key_seq_var": "AESEQ",
        "required_vars": ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM"],
        "expected_vars": [
            # 识别变量
            "SUBJID", "AESPID",
            # MedDRA编码变量
            "AEDECOD", "AELLT", "AELLTCD", "AEPTCD", "AEHLT", "AEHLTCD", 
            "AEHLGT", "AEHLGTCD", "AEBODSYS", "AEBDSYCD", "AESOC", "AESOCCD",
            # 核心AE变量
            "AESER", "AEACN", "AEREL", "AEOUT", "AEENRF", "AESTDTC", "AEENDTC", "AESTDY", "AEENDY", "AETOXGR", "EPOCH"
        ],
        "controlled_term_vars": ["AESER", "AESDTH", "AESLIFE", "AESHOSP", "AESDISAB", "AESCONG", "AESMIE", "AECONTRT", "AEACN", "AEREL", "AEOUT"],
        "med_dict_vars": ["AEDECOD", "AELLT", "AELLTCD", "AEPTCD", "AEHLT", "AEHLTCD", "AEHLGT", "AEHLGTCD", "AEBODSYS", "AEBDSYCD", "AESOC", "AESOCCD"],
        "med_dict_type": "meddra",  # 字典类型
        "med_dict_search_col": "AETERM",  # 用于检索的源列
        "med_dict_output_cols": ["AELLT", "AELLTCD", "AEDECOD", "AEPTCD", "AEHLT", "AEHLTCD", "AEHLGT", "AEHLGTCD", "AEBODSYS", "AEBDSYCD", "AESOC", "AESOCCD"],
        "core_vars_only": False,  # 只保留核心SDTM变量
        "keep_only_sdtm_cols": True,  # 只保留必需列和期望列，移除源数据的多余列
        "row_filter": {"column": "AEYN", "keep_values": ["Yes", "是"]},  # 行过滤规则：只保留 AEYN='Yes' 或 '是' 的记录
        "column_order": [
            "STUDYID", "DOMAIN", "USUBJID", "SUBJID", "AESEQ", "AESPID", "AETERM",
            "AELLT", "AELLTCD", "AEDECOD", "AEPTCD", "AEHLT", "AEHLTCD",
            "AEHLGT", "AEHLGTCD", "AEBODSYS", "AEBDSYCD", "AESOC", "AESOCCD",
            "AESER", "AEACN", "AEREL", "AEOUT", "AEENRF", "AESTDTC", "AEENDTC", "AESTDY", "AEENDY", "AETOXGR", "EPOCH"
        ],
        "numeric_cols": ["AETOXGR", "AESTDY", "AEENDY"],  # 该域的数值列
        "date_cols": ["AESTDTC", "AEENDTC"],  # 该域的日期列
        # 【新增】源列别名映射（泛化处理不同命名约定的源数据）
        "source_column_aliases": {
            "AESTDTC": ["AESTDAT", "AE_START_DATE", "AESTARTDATE"],  # AESTDTC 的可能源列名
            "AEENDTC": ["AEENDAT", "AE_END_DATE", "AEENDDATE"],      # AEENDTC 的可能源列名
            "AETOXGR": ["AECTCAE", "TOX_GRADE", "AEGRADE"],           # AETOXGR 的可能源列名
        },
        # 【新增】派生规则（基于源列进行转换）
        "derived_columns": {
            # AESTDTC: 从源日期列转换（自动日期格式转换）
            "AESTDTC": {
                "source_col": "AESTDTC",  # 自动从别名中查找源列
                "transform": "date_normalize",  # 日期标准化转换
                "date_format": "YYYY-MM-DD"
            },
            # AEENDTC: 从源日期列转换
            "AEENDTC": {
                "source_col": "AEENDTC",
                "transform": "date_normalize",
                "date_format": "YYYY-MM-DD"
            },
            # AETOXGR: 从 AECTCAE 中提取等级（去掉 "Grade" 前缀）
            "AETOXGR": {
                "source_col": "AETOXGR",
                "transform": "extract_grade",  # 提取毒性等级
                "pattern": "Grade",  # 要移除的前缀
            }
        },
        "usubjid_derivation": {
            "format": "{study}-{subject}",  # 格式字符串，用 {study} 和 {subject} 占位符
            "study_col": "project",  # 源列名（会自动检测，可覆盖）
            "subject_col": "Subject",  # 源列名（会自动检测，可覆盖）
            "subject_padding": 0,  # subject_col 不需要补零，已经是 SUBJ_XXXX 格式
            "subject_strip": "SUBJ_",  # 从 SUBJ_0051 中提取 0051
        },
        "relative_day_cols": {  # 相对天数计算规则
            "AESTDY": {"date_col": "AESTDTC", "reference_date": None},  # reference_date=None 表示取第一个有效日期作为参考
            "AEENDY": {"date_col": "AEENDTC", "reference_date": None},
        },
        "quality_thresholds": {  # 数据质量阈值
            "missing_rate_warning": 0.3,  # 期望列缺失率>30%警告
            "missing_rate_error": 0.5,    # 期望列缺失率>50%错误
        }
    },
    "CM": {
        "description": "Concomitant Medications",
        "key_seq_var": "CMSEQ",
        "required_vars": ["STUDYID", "DOMAIN", "USUBJID", "CMSEQ", "CMTRT"],
        # 扩充 expected_vars：尽量覆盖 SDTMIG 常见 Perm/Exp（源里有就会被匹配输出）
        "expected_vars": [
            "CMDECOD", "CMCAT", "CMSCAT", "CMINDC",
            "CMDOSE", "CMDOSU", "CMDOSTXT", "CMDOSFRQ", "CMROUTE",
            "CMSTDTC", "CMENDTC", "CMSTDY", "CMENDY", "CMDUR",
            "CMLOT", "CMLOC", "CMPRIOR", "CMOCCUR",
            "CMSEQ",  # 兼容源里已经有同名
            "VISIT", "VISITNUM", "VISITDY", "EPOCH",
            "CMGRPID", "CMREFID", "CMSPID"
        ],
        "med_dict_vars": ["CMTRT"],
        "med_dict_type": None,
        "core_vars_only": False,
        "keep_only_sdtm_cols": True,
        "row_filter": {"column": "CMYN", "keep_values": ["Yes", "是"]},
        # 尽量按 SDTM 习惯顺序列出（存在才会输出）
        "column_order": [
            "STUDYID", "DOMAIN", "USUBJID",
            "CMSEQ", "CMGRPID", "CMREFID", "CMSPID",
            "CMTRT", "CMDECOD", "CMCAT", "CMSCAT", "CMINDC",
            "CMDOSE", "CMDOSU", "CMDOSTXT", "CMDOSFRQ", "CMROUTE",
            "CMSTDTC", "CMENDTC", "CMSTDY", "CMENDY", "CMDUR",
            "CMLOT", "CMLOC", "CMPRIOR", "CMOCCUR",
            "VISIT", "VISITNUM", "VISITDY", "EPOCH"
        ],
        "numeric_cols": ["CMDOSE"],
        "date_cols": ["CMSTDTC", "CMENDTC"],
        "usubjid_derivation": {"format": "{study}-{subject}", "subject_padding": 5},
        "quality_thresholds": {"missing_rate_warning": 0.2, "missing_rate_error": 0.5}
    },
    "LB": {
        "description": "Laboratory Test Results",
        "key_seq_var": "LBSEQ",
        "required_vars": ["STUDYID", "DOMAIN", "USUBJID", "LBSEQ", "LBTEST", "LBDTC"],
        # 扩充 expected_vars：常见 Findings 结构（LBTESTCD/LBCAT/标志等）
        "expected_vars": [
            "LBTESTCD", "LBCAT", "LBSCAT", "LBMETHOD", "LBLOINC",
            "LBSPEC", "LBSPCCND", "LBFAST",
            "LBDTC", "LBENDTC", "LBDY",
            "LBORRES", "LBORRESU",
            "LBSTRESC", "LBSTRESN", "LBSTRESU",
            "LBSTAT", "LBREASND", "LBNRIND",
            "LBORNRLO", "LBORNRHI", "LBSTNRLO", "LBSTNRHI",
            "LBBLFL", "LBCLSIG",
            "VISIT", "VISITNUM", "VISITDY", "EPOCH",
            "LBGRPID", "LBREFID", "LBSPID"
        ],
        "controlled_term_vars": ["LBNRIND", "LBSTAT", "LBBLFL", "LBFAST"],
        "med_dict_type": None,
        "core_vars_only": False,
        "keep_only_sdtm_cols": True,
        "row_filter": {"column": "LBYN", "keep_values": ["Yes"]},
        "column_order": [
            "STUDYID", "DOMAIN", "USUBJID",
            "LBSEQ", "LBGRPID", "LBREFID", "LBSPID",
            "LBTEST", "LBTESTCD", "LBCAT", "LBSCAT", "LBMETHOD", "LBLOINC",
            "LBSPEC", "LBSPCCND", "LBFAST",
            "LBDTC", "LBENDTC", "LBDY",
            "LBORRES", "LBORRESU",
            "LBSTRESC", "LBSTRESN", "LBSTRESU",
            "LBSTAT", "LBREASND", "LBNRIND",
            "LBORNRLO", "LBORNRHI", "LBSTNRLO", "LBSTNRHI",
            "LBBLFL", "LBCLSIG",
            "VISIT", "VISITNUM", "VISITDY", "EPOCH"
        ],
        "numeric_cols": ["LBSTRESN", "LBORNRLO", "LBORNRHI", "LBSTNRLO", "LBSTNRHI"],
        "date_cols": ["LBDTC", "LBENDTC"],
        "usubjid_derivation": {"format": "{study}-{subject}", "subject_padding": 5},
        "quality_thresholds": {"missing_rate_warning": 0.2, "missing_rate_error": 0.5}
    },
    "VS": {
        "description": "Vital Signs",
        "key_seq_var": "VSSEQ",
        "required_vars": ["STUDYID", "DOMAIN", "USUBJID", "VSSEQ", "VSTEST", "VSTESTCD", "VSDTC"],
        # 扩充 expected_vars：常见 VS 可选字段
        "expected_vars": [
            "VSCAT", "VSSCAT", "VSPOS", "VSLOC", "VSLAT", "VSDIR",
            "VSDTC", "VSDY",
            "VSORRES", "VSORRESU",
            "VSSTRESC", "VSSTRESN", "VSSTRESU",
            "VSSTAT", "VSREASND",
            "VISIT", "VISITNUM", "VISITDY", "EPOCH",
            "VSGRPID", "VSREFID", "VSSPID"
        ],
        "med_dict_type": None,
        "core_vars_only": False,
        "keep_only_sdtm_cols": True,
        "row_filter": None,
        "column_order": [
            "STUDYID", "DOMAIN", "USUBJID",
            "VSSEQ", "VSGRPID", "VSREFID", "VSSPID",
            "VSTEST", "VSTESTCD", "VSCAT", "VSSCAT",
            "VSPOS", "VSLOC", "VSLAT", "VSDIR",
            "VSDTC", "VSDY",
            "VSORRES", "VSORRESU",
            "VSSTRESC", "VSSTRESN", "VSSTRESU",
            "VSSTAT", "VSREASND",
            "VISIT", "VISITNUM", "VISITDY", "EPOCH"
        ],
        "numeric_cols": ["VSSTRESN"],
        "date_cols": ["VSDTC"],
        "usubjid_derivation": {"format": "{study}-{subject}", "subject_padding": 5},
        "quality_thresholds": {"missing_rate_warning": 0.2, "missing_rate_error": 0.5}
    },
    "DM": {
        "description": "Demographics",
        "key_seq_var": None,
        "required_vars": ["STUDYID", "USUBJID", "SUBJID", "RFSTDTC"],
        # 扩充 expected_vars：常见 DM 变量（只要源里有就会被匹配输出）
        "expected_vars": [
            "RFENDTC", "RFXSTDTC", "RFXENDTC",
            "SITEID", "INVID", "INVNAM",
            "BRTHDTC", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
            "ARMCD", "ARM", "ACTARMCD", "ACTARM",
            "COUNTRY",
            "DTHDTC", "DTHFL"
        ],
        "controlled_term_vars": ["SEX", "RACE", "ETHNIC", "DTHFL"],
        "med_dict_type": None,
        "core_vars_only": False,
        "keep_only_sdtm_cols": True,
        "row_filter": None,
        "column_order": [
            "STUDYID", "USUBJID", "SUBJID", "SITEID",
            "RFSTDTC", "RFENDTC", "RFXSTDTC", "RFXENDTC",
            "BRTHDTC", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
            "ARMCD", "ARM", "ACTARMCD", "ACTARM",
            "COUNTRY", "INVID", "INVNAM",
            "DTHDTC", "DTHFL"
        ],
        "numeric_cols": ["AGE"],
        "date_cols": ["RFSTDTC", "RFENDTC", "RFXSTDTC", "RFXENDTC", "BRTHDTC", "DTHDTC"],
        "usubjid_derivation": {"format": "{study}-{subject}", "subject_padding": 5},
        "quality_thresholds": {"missing_rate_warning": 0.1, "missing_rate_error": 0.3}
    },
}

# 标准化规则（缺失值处理、日期格式等）
STANDARDIZATION_RULES = {
    "missing_value_codes": ["NA", "N/A", "", "MISSING", "missing", "null", "NULL"],
    "date_formats": ["%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%m/%d/%Y"],
    "numeric_inference": True,
}


# ============ 数据加载辅助函数（泛化） ============
def get_source_file(domain: str, filename: Optional[str] = None) -> str:
    """
    获取源数据文件路径（泛化支持多个文件）
    
    Args:
        domain: SDTM 域名（如 'AE', 'CM'）
        filename: 具体文件名（如 'CH3_ae.xlsx'）。若为 None，自动查找
    
    Returns:
        完整文件路径
    """
    if filename:
        filepath = os.path.join(RAW_DATA_DIR, filename)
        if os.path.exists(filepath):
            return filepath
        raise FileNotFoundError(f"Source file not found: {filepath}")
    
    # 自动查找：优先匹配 {domain} 的 Excel 文件
    for file in os.listdir(RAW_DATA_DIR):
        if domain.lower() in file.lower() and file.endswith((".xlsx", ".xls", ".csv")):
            return os.path.join(RAW_DATA_DIR, file)
    
    raise FileNotFoundError(f"No source file found for domain '{domain}' in {RAW_DATA_DIR}")


def get_reference_file(reference_type: str = "meddra") -> str:
    """
    获取参考数据文件路径
    
    Args:
        reference_type: 参考数据类型（如 'meddra', 'whodd'）
    
    Returns:
        完整文件路径
    """
    for file in os.listdir(REFERENCE_DATA_DIR):
        if reference_type.lower() in file.lower() and file.endswith((".csv", ".xlsx", ".xls")):
            return os.path.join(REFERENCE_DATA_DIR, file)
    
    raise FileNotFoundError(f"No reference file for '{reference_type}' in {REFERENCE_DATA_DIR}")


def load_meddra_database() -> pd.DataFrame:
    """加载 MedDRA 数据库"""
    try:
        meddra_file = get_reference_file("meddra")
        df_meddra = pd.read_csv(meddra_file, dtype=str)
        return df_meddra
    except FileNotFoundError as e:
        print(f"[WARN]  Warning: {e}")
        return pd.DataFrame()  # 返回空 DataFrame，允许继续处理


# ============ MedDRA 语义搜索相关（泛化设计） ============
_MEDDRA_DF: pd.DataFrame | None = None
_MEDDRA_MODEL = None
_MEDDRA_EMB: np.ndarray | None = None
# 新增：对查询 term 的编码结果做缓存，避免重复计算
_MEDDRA_QUERY_CACHE: dict[str, dict] = {}


def _load_meddra_df(meddra_csv_path: str | None = None) -> pd.DataFrame:
    """加载MedDRA DataFrame（带缓存）"""
    global _MEDDRA_DF
    if _MEDDRA_DF is not None:
        return _MEDDRA_DF

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = meddra_csv_path or os.path.join(base, "data", "reference", "meddra_database.csv")
    if not os.path.isabs(path):
        path = os.path.join(base, path)

    try:
        _MEDDRA_DF = pd.read_csv(path, dtype=str)
    except Exception:
        _MEDDRA_DF = pd.DataFrame()
    return _MEDDRA_DF


def _get_embed_model(model_name: str = "BAAI/bge-small-en-v1.5"):
    """获取embedding模型（带缓存）"""
    global _MEDDRA_MODEL
    if _MEDDRA_MODEL is not None:
        return _MEDDRA_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        # 明确指定 device，避免某些环境里反复初始化导致重复 Loading weights
        device = "cuda" if os.environ.get("USE_CUDA", "0") == "1" else "cpu"
        _MEDDRA_MODEL = SentenceTransformer(model_name, device=device)
    except ImportError:
        raise ImportError("sentence_transformers not installed. Please install with: pip install sentence-transformers")
    return _MEDDRA_MODEL


def build_meddra_index(meddra_csv_path: str | None = None, text_col: str = "LLT_TERM", model_name: str = "BAAI/bge-small-en-v1.5") -> dict:
    """构建MedDRA向量索引"""
    global _MEDDRA_EMB
    df = _load_meddra_df(meddra_csv_path)
    if df.empty or text_col not in df.columns:
        return {"ok": False, "error": f"MedDRA dict empty or missing column {text_col}"}

    model = _get_embed_model(model_name)
    texts = df[text_col].astype(str).fillna("").tolist()
    emb = model.encode(texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False)
    _MEDDRA_EMB = np.asarray(emb, dtype=np.float32)
    return {"ok": True, "rows": int(len(texts)), "text_col": text_col, "model": model_name}


def semantic_search_meddra(term: str, top_k: int = 5, min_score: float = 0.55) -> dict:
    """
    语义检索 MedDRA 候选
    若最高分低于 min_score，返回 not_assigned=true
    """
    try:
        # 归一化 key：小写 + 压缩空白
        _term_key = " ".join(str(term).strip().lower().split())
        cache_key = f"{_term_key}||{int(top_k)}||{float(min_score):.3f}"

        global _MEDDRA_QUERY_CACHE
        if cache_key in _MEDDRA_QUERY_CACHE:
            return _MEDDRA_QUERY_CACHE[cache_key]

        df = _load_meddra_df()
        if df.empty or "LLT_TERM" not in df.columns:
            result = {"ok": False, "error": "MedDRA database not available"}
            _MEDDRA_QUERY_CACHE[cache_key] = result
            return result

        global _MEDDRA_EMB
        if _MEDDRA_EMB is None:
            build_meddra_index()  # 自动构建索引
            if _MEDDRA_EMB is None:
                result = {"ok": False, "error": "Failed to build MedDRA index"}
                _MEDDRA_QUERY_CACHE[cache_key] = result
                return result

        model = _get_embed_model()
        q = model.encode([str(term)], normalize_embeddings=True)
        q = np.asarray(q, dtype=np.float32)[0]

        scores = _MEDDRA_EMB @ q
        k = int(max(1, min(int(top_k), len(scores))))
        idx = np.argpartition(-scores, kth=k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]

        candidates = []
        for i in idx.tolist():
            row = df.iloc[i]
            candidates.append({
                "score": float(scores[i]),
                "LLT_TERM": str(row.get("LLT_TERM", "")),
                "LLT_CODE": str(row.get("LLT_CODE", "")),
                "PT_TERM": str(row.get("PT_TERM", "")),
                "PT_CODE": str(row.get("PT_CODE", "")),
                "HLT_TERM": str(row.get("HLT_TERM", "")),
                "HLT_CODE": str(row.get("HLT_CODE", "")),
                "HLGT_TERM": str(row.get("HLGT_TERM", "")),
                "HLGT_CODE": str(row.get("HLGT_CODE", "")),
                "SOC_TERM": str(row.get("SOC_TERM", "")),
                "SOC_CODE": str(row.get("SOC_CODE", ""))
            })

        best = candidates[0]["score"] if candidates else 0.0
        result = {
            "ok": True,
            "query": term,
            "top_k": k,
            "min_score": float(min_score),
            "best_score": float(best),
            "not_assigned": bool(best < float(min_score)),
            "candidates": candidates,
        }
        _MEDDRA_QUERY_CACHE[cache_key] = result
        return result
    except Exception as e:
        result = {"ok": False, "error": str(e)}
        try:
            _MEDDRA_QUERY_CACHE[cache_key] = result
        except Exception:
            pass
        return result


class SDTMTransformer:
    """多域泛化转换器"""
    
    def __init__(self, domain: str, cutoff_date: str = None):
        if domain not in DOMAIN_METADATA:
            raise ValueError(f"Unsupported domain: {domain}. Supported: {list(DOMAIN_METADATA.keys())}")
        
        self.domain = domain
        self.metadata = DOMAIN_METADATA[domain]
        self.mapping: Dict[str, str] = {}  # 源列 -> SDTM 列 映射
        self.derived_rules: Dict[str, callable] = {}  # 派生列规则
        self.issues: List[Dict[str, Any]] = []
        self.cutoff_date = cutoff_date  # 新增：cutoff 日期
    
    def infer_source_schema(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        【关键】源数据Schema推断方法 - 分析源数据的结构
        
        返回的schema包含：
        - shape: DataFrame 的形状 (行, 列)
        - columns: 所有列名列表
        - dtypes: 每列的数据类型
        - sample_values: 每列的样本值（前3行）
        - missing_rates: 每列的缺失率
        - unique_counts: 每列的唯一值个数
        """
        schema = {
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": {col: str(df[col].dtype) for col in df.columns},
            "sample_values": {},
            "missing_rates": {},
            "unique_counts": {},
        }
        
        # 收集样本值和统计信息
        for col in df.columns:
            # 样本值：取前3行非空值
            sample = df[col].dropna().unique()[:3].tolist()
            schema["sample_values"][col] = sample
            
            # 缺失率
            missing_rate = df[col].isna().sum() / len(df) if len(df) > 0 else 0
            schema["missing_rates"][col] = round(missing_rate, 4)
            
            # 唯一值个数
            schema["unique_counts"][col] = int(df[col].nunique())
        
        return schema
        
    def diagnose_source_schema(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        【关键】源数据诊断方法 - 防止映射错误的第一步
        
        这个方法的目的是：
        1. 理解源数据结构（列名、类型、样本值）
        2. 找到关键派生列（study/subject等）
        3. 生成诊断报告供人工审查
        
        使用场景：在编写 propose_mapping() 之前调用这个方法
        
        返回诊断信息，包括：
        - 所有列的基本信息
        - 发现的关键派生列
        - 建议的映射策略
        """
        print("\n[DIAGNOSIS] 开始源数据诊断...")
        
        schema = self.infer_source_schema(df)
        diagnosis = {
            "source_shape": schema['shape'],
            "all_columns": schema['columns'],
            "data_types": schema['dtypes'],
            "sample_values": schema['sample_values'],
            "key_findings": []
        }
        
        # 寻找关键列（通常用于派生字段）
        key_cols = {}
        
        # 寻找研究标识列
        for col in schema['columns']:
            if col.lower() in ["project", "studyid", "study_id", "study", "studyidentifier"]:
                key_cols['study_col'] = col
                diagnosis['key_findings'].append(f"[FOUND] 研究标识列: {col} = {schema['sample_values'].get(col, ['N/A'])[:1]}")
                break
        
        # 寻找受试者标识列
        for col in schema['columns']:
            if col.lower() in ["subject", "subjid", "subj_id", "subjectid", "subject_id"]:
                key_cols['subject_col'] = col
                diagnosis['key_findings'].append(f"[FOUND] 受试者标识列: {col} = {schema['sample_values'].get(col, ['N/A'])[:1]}")
                break
        
        # 对于AE域，寻找诊断项列
        if self.domain == "AE":
            for col in schema['columns']:
                if col.lower() in ["aeterm", "ae_term", "adverse_event", "diagnosis", "event"]:
                    key_cols['term_col'] = col
                    diagnosis['key_findings'].append(f"[FOUND] 诊断项列: {col} = {schema['sample_values'].get(col, ['N/A'])[:1]}")
                    break
        
        diagnosis['key_derivation_cols'] = key_cols
        
        # 打印诊断结果
        print(f"\n[INFO] 源数据形状: {diagnosis['source_shape']}")
        print(f"[INFO] 所有列({len(schema['columns'])}): {schema['columns']}")
        print("\n[FINDINGS] 关键发现:")
        for finding in diagnosis['key_findings']:
            print(f"  {finding}")
        
        if not diagnosis['key_findings']:
            print("  [WARNING] 未找到关键派生列，可能需要手工指定")
        
        return diagnosis
    
    def propose_mapping(self, source_schema: Dict[str, Any], rag_context: str = "") -> Dict[str, str]:
        """
        提议列映射方案（元数据驱动，支持泛化）
        返回 {源列: SDTM目标列}
        
        策略：
        1. 源列别名映射（如 AESTDAT → AESTDTC）【新增】
        2. 精确名称匹配（源列名大写后即为SDTM列名）
        3. 根据元数据中的通用模式匹配
        4. 特殊处理USUBJID（派生规则）
        5. 特殊处理STUDYID（使用 project 字段）
        6. 特殊处理SUBJID（从 Subject 提取）
        7. 检查并记录缺失的必需列
        """
        mapping = {}
        df_cols_lower = {col.lower(): col for col in source_schema["columns"]}
        processed_sdtm_vars = set()  # 跟踪已映射的 SDTM 变量
        
        # 【新增】策略 0: 源列别名映射
        # 允许原始列名（如 AESTDAT）映射到 SDTM 列名（如 AESTDTC）
        if "source_column_aliases" in self.metadata:
            for sdtm_col, source_aliases in self.metadata["source_column_aliases"].items():
                for alias in source_aliases:
                    # 不区分大小写的精确匹配
                    if alias.lower() in df_cols_lower:
                        raw_col = df_cols_lower[alias.lower()]
                        mapping[raw_col] = sdtm_col
                        processed_sdtm_vars.add(sdtm_col)
                        print(f"[MAPPING] 源列别名匹配: {raw_col} → {sdtm_col}")
                        break  # 找到后停止查找这个 SDTM 列的其他别名
        
        # 策略 1: 精确匹配（源列名大写后就是SDTM列名）
        all_sdtm_vars = self.metadata.get("required_vars", []) + self.metadata.get("expected_vars", [])
        for col in source_schema["columns"]:
            if col in mapping:  # 已在别名处理中映射过
                continue
            col_upper = col.upper()
            if col_upper in all_sdtm_vars and col_upper not in ["USUBJID", "STUDYID", "SUBJID"]:
                if col_upper not in processed_sdtm_vars:
                    mapping[col] = col_upper
                    processed_sdtm_vars.add(col_upper)
        
        # 策略 2: 通用启发式模式匹配（元数据驱动）
        source_cols_lower = {col.lower(): col for col in source_schema["columns"]}
        
        # 按照元数据定义的期望列，尝试模糊匹配（改进的启发式算法）
        for expected_var in self.metadata.get("expected_vars", []):
            if expected_var in mapping.values():
                continue  # 已映射
            
            # 将SDTM变量名分解为可能的关键词
            tokens = self._tokenize_sdtm_var(expected_var)
            
            # 在源列中寻找最佳匹配
            best_match = None
            best_score = 0
            
            for src_col_lower, src_col in source_cols_lower.items():
                if src_col in mapping:
                    continue  # 已映射
                
                # 改进的匹配评分算法：
                # 1. 完全匹配最高分
                if src_col_lower == expected_var.lower():
                    best_match = src_col
                    best_score = 100
                    break
                
                # 2. 包含匹配（整个SDTM变量名在源列中）
                if expected_var.lower() in src_col_lower:
                    match_score = 90 + len(expected_var) / len(src_col_lower) * 10
                    if match_score > best_score:
                        best_match = src_col
                        best_score = match_score
                    continue
                
                # 3. 关键词匹配（必须匹配所有关键词，不允许缺失）
                match_count = sum(1 for token in tokens if token in src_col_lower)
                if match_count == len(tokens):  # 严格：必须全部匹配
                    match_score = 70 + (len(tokens) / max(1, len(src_col_lower))) * 10
                    if match_score > best_score:
                        best_match = src_col
                        best_score = match_score
            
            # 应用最佳匹配（仅当分数足够高时）
            if best_match and best_score >= 70:  # 阈值：70分及以上
                mapping[best_match] = expected_var
        
        # 策略 3: 特殊处理 STUDYID（使用 project 字段）
        if "STUDYID" not in mapping.values():
            for col in source_schema["columns"]:
                if col.lower() in ["project", "studyid", "study_id", "study_code"]:
                    mapping[col] = "STUDYID"
                    break
            
            if "STUDYID" not in mapping.values():
                self.issues.append({
                    "type": "missing_required_var",
                    "var": "STUDYID",
                    "severity": "error",
                    "message": "Cannot find STUDYID column. Expected 'project', 'studyid', 'study_id', or 'study_code'",
                })
        
        # 策略 4: 特殊处理 SUBJID（从 Subject 提取）
        if "SUBJID" not in mapping.values():
            # 优先级：Subject > subjid > subject_id > ...
            subject_col = None
            for col in source_schema["columns"]:
                col_lower = col.lower()
                # 优先选择精确或接近的列名
                if col == "Subject":  # 完全匹配（区分大小写）
                    subject_col = col
                    break
            
            # 如果没找到 "Subject"，再用模糊匹配
            if not subject_col:
                for col in source_schema["columns"]:
                    col_lower = col.lower()
                    if col_lower in ["subject", "subjid", "subj_id", "subjectid", "subject_id"]:
                        subject_col = col
                        break
            
            if subject_col:
                mapping[subject_col] = "SUBJID"
        
        # 策略 5: 特殊处理 USUBJID（派生规则，使用元数据配置）
        if "USUBJID" not in mapping.values():
            study_col = None
            subject_col = None
            
            # 使用更明确的列名检测（优先精确匹配）
            for col in source_schema["columns"]:
                if not study_col and col.lower() == "project":
                    study_col = col
                    break
            
            # 如果 project 没找到，再用模糊匹配
            if not study_col:
                study_patterns = ["project", "studyid", "study_id", "study_code", "study"]
                for col in source_schema["columns"]:
                    col_lower = col.lower()
                    if col_lower in study_patterns:
                        study_col = col
                        break
            
            # 同样为 subject 列优先选择 "Subject"
            for col in source_schema["columns"]:
                if not subject_col and col == "Subject":
                    subject_col = col
                    break
            
            # 如果 "Subject" 没找到，再用模糊匹配
            if not subject_col:
                subject_patterns = ["subject", "subjid", "subj_id", "subjectid", "subject_id", "participant"]
                for col in source_schema["columns"]:
                    col_lower = col.lower()
                    if col_lower in subject_patterns:
                        subject_col = col
                        break
            
            # 优先级：study_col + subject_col → 派生规则
            if study_col and subject_col:
                mapping["_derived_usubjid"] = "USUBJID"
                
                # 使用元数据中的派生规则配置
                derivation_config = self.metadata.get("usubjid_derivation", {})
                format_str = derivation_config.get("format", "{study}-{subject}")
                subject_padding = derivation_config.get("subject_padding", 0)
                subject_strip = derivation_config.get("subject_strip", None)
                
                def create_usubjid(df, study_col=study_col, subject_col=subject_col, fmt=format_str, padding=subject_padding, strip=subject_strip):
                    # 对每一行应用转换，确保逐行处理
                    def derive_row(row):
                        study_val = str(row[study_col]).strip()
                        subject_val = str(row[subject_col]).strip()
                        
                        # 如果配置了 subject_strip，先剥离前缀（如 SUBJ_0051 → 0051）
                        if strip:
                            import re
                            subject_val = re.sub(f"^{strip}", "", subject_val)
                        
                        # 左补零（如果配置了）
                        if padding > 0:
                            subject_val = subject_val.zfill(padding)
                        
                        return fmt.format(study=study_val, subject=subject_val)
                    
                    return df.apply(derive_row, axis=1)
                
                self.derived_rules = {"USUBJID": create_usubjid}
            elif subject_col:
                mapping[subject_col] = "USUBJID"
            else:
                self.issues.append({
                    "type": "usubjid_construction_failed",
                    "severity": "error",
                    "message": "Cannot construct USUBJID: missing subject identifier column",
                })
        
        # 策略 6: 检查缺失的必需列
        mapped_targets = set(mapping.values())
        for req_var in self.metadata.get("required_vars", []):
            if req_var not in mapped_targets:
                self.issues.append({
                    "type": "missing_required_var",
                    "var": req_var,
                    "severity": "error",
                    "message": f"Required variable '{req_var}' not found in source. Please specify source column or provide derivation rule.",
                })
        
        self.mapping = mapping
        return mapping
    
    def _tokenize_sdtm_var(self, var_name: str) -> List[str]:
        """
        分解SDTM变量名为关键词
        例：LBSTRESN -> ["lb", "stresc", "n"]
        """
        var_lower = var_name.lower()
        
        # 提取域前缀（2字母）
        domain_prefix = var_lower[:2] if len(var_lower) >= 2 else ""
        
        # 移除域前缀，分解剩余部分
        rest = var_lower[2:] if len(var_lower) > 2 else ""
        
        # 简单分解：按常见后缀分割
        tokens = [domain_prefix] if domain_prefix else []
        
        # 尝试识别常见后缀
        suffixes = ["res", "stresc", "orres", "stresu", "orresu", "dtc", "dt", "dy", "cd", "n", "cd"]
        for suffix in suffixes:
            if rest.endswith(suffix):
                tokens.append(rest[:-len(suffix)])  # 添加前缀部分
                tokens.append(suffix)  # 添加后缀
                return tokens
        
        # 如果没有匹配的后缀，直接添加整个rest部分
        if rest:
            tokens.append(rest)
        
        return tokens
    
    def standardize_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        标准化数据：缺失值处理、类型转换、日期规范化（元数据驱动）
        返回 (标准化DF, 问题列表)
        """
        issues = []
        df_std = df.copy()
        
        # 获取该域定义的日期列和数值列
        domain_date_cols = self.metadata.get("date_cols", [])
        domain_numeric_cols = self.metadata.get("numeric_cols", [])
        
        for col in df_std.columns:
            # 1. 统一缺失值代码
            for miss_code in STANDARDIZATION_RULES["missing_value_codes"]:
                if miss_code and miss_code in df_std[col].astype(str).unique():
                    df_std.loc[df_std[col].astype(str) == miss_code, col] = np.nan
            
            # 2. 日期列检测和标准化
            # 优先级（从高到低）：
            #   1. 元数据中明确定义的日期列（最可靠）
            #   2. 列名以 DTC 结尾的（标准 SDTM 日期变量）
            #   3. 其他启发式检测（需要验证）
            is_date_col = False
            
            if col in domain_date_cols:
                # 最高优先级：元数据中明确定义
                is_date_col = True
            elif col.upper().endswith("DTC"):
                # 次高：标准 SDTM 日期变量（例 AESTDTC, CMENDTC）
                is_date_col = True
            elif col.upper().endswith("DT") and not col.upper().endswith(("_DT", "DAT", "EAT")):
                # 低优先级：以 DT 结尾但排除误判（不包括 ..._DT 或 ...DAT）
                is_date_col = True
            
            if is_date_col:
                try:
                    # 先尝试 pd.to_datetime 的自动推断
                    temp = pd.to_datetime(df_std[col], errors="coerce")
                    # 如果大部分都成功了，用自动推断的结果
                    if temp.isna().sum() / len(df_std) < 0.5:
                        df_std[col] = temp.dt.strftime("%Y-%m-%d")
                    else:
                        # 否则尝试特定格式
                        success = False
                        for fmt in STANDARDIZATION_RULES["date_formats"]:
                            try:
                                df_std[col] = pd.to_datetime(df_std[col], format=fmt, errors="coerce")
                                df_std[col] = df_std[col].dt.strftime("%Y-%m-%d")
                                success = True
                                break
                            except:
                                continue
                        if not success:
                            issues.append({
                                "type": "date_parse_warning",
                                "column": col,
                                "message": "Could not parse all date values, kept as is",
                                "severity": "warning"
                            })
                except Exception as e:
                    issues.append({
                        "type": "date_parse_error",
                        "column": col,
                        "error": str(e)[:100],
                        "severity": "warning"
                    })
            
            # 3. 数值列类型推断（元数据驱动，启发式规则谨慎使用）
            # 优先级：
            #   1. 元数据中明确定义（最可靠）
            #   2. 启发式规则：STRESC, STRESN, ORRES, ORRESU 等明确的数值列后缀（避免误判 AEYN 等控制术语列）
            
            is_numeric_col = col in domain_numeric_cols  # 只用元数据中明确定义的
            
            # 仅对很明确的数值列后缀应用启发式规则
            if not is_numeric_col:
                # 只匹配明确的数值列模式（避免匹配 AEYN, AESER 等控制术语列）
                numeric_suffixes = ["STRESN", "ORRESN", "N_", "STRESC", "ORRES"]  # 移除过于宽泛的 "N"
                is_numeric_col = any(col.endswith(suffix) for suffix in numeric_suffixes)
            
            if is_numeric_col and STANDARDIZATION_RULES.get("numeric_inference", True):
                try:
                    df_std[col] = pd.to_numeric(df_std[col], errors="coerce")
                except:
                    pass
        
        return df_std, issues
    
    def apply_mapping(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        应用映射、进行转换、生成 SDTM 表
        返回 (SDTM DF, 转换问题)
        """
        if not self.mapping:
            raise ValueError("No mapping defined. Call propose_mapping first.")

        issues = []

        # 【第0步】行过滤（基于元数据配置，如 AEYN='Yes'）
        row_filter_config = self.metadata.get("row_filter")
        if row_filter_config:
            filter_col = row_filter_config.get("column")
            keep_values = row_filter_config.get("keep_values", [])
            
            if filter_col and filter_col in df.columns:
                before_rows = len(df)
                mask = df[filter_col].isin(keep_values)
                df = df[mask].copy()
                after_rows = len(df)
                
                if after_rows < before_rows:
                    issues.append({
                        "type": "row_filter_applied",
                        "severity": "info",
                        "column": filter_col,
                        "keep_values": keep_values,
                        "filtered_count": before_rows - after_rows,
                        "message": f"Filtered {before_rows - after_rows} records: kept {after_rows} records where {filter_col} in {keep_values}"
                    })
                    self.issues.append(issues[-1])
        
        # AE 域 cutoff 过滤
        if self.domain == "AE" and self.cutoff_date:
            if "AESTDTC" in df.columns or "AESTDAT" in df.columns:
                try:
                    date_col_name = "AESTDTC" if "AESTDTC" in df.columns else "AESTDAT"
                    cutoff = pd.to_datetime(self.cutoff_date)
                    date_col = pd.to_datetime(df[date_col_name], errors="coerce")
                    before_rows = len(df)
                    df = df[date_col <= cutoff].copy()
                    after_rows = len(df)
                    if after_rows < before_rows:
                        self.issues.append({
                            "type": "cutoff_filter",
                            "severity": "info",
                            "message": f"Filtered {before_rows - after_rows} AE records after cutoff date {self.cutoff_date}"
                        })
                except Exception as e:
                    self.issues.append({
                        "type": "cutoff_filter_error",
                        "severity": "warning",
                        "message": f"Failed to filter by cutoff date: {e}"
                    })
        
        # 1. 应用派生规则（在重命名之前，因为派生规则引用原始列名）
        for derived_col, rule_func in self.derived_rules.items():
            try:
                derived_val = rule_func(df)
                # 兼容返回 DataFrame（例如 apply(axis=1) 的结果被包装）
                if isinstance(derived_val, pd.DataFrame):
                    if derived_val.shape[1] >= 1:
                        derived_val = derived_val.iloc[:, 0]
                    else:
                        raise ValueError(f"Derived rule for {derived_col} returned empty DataFrame")
                df[derived_col] = derived_val
            except Exception as e:
                self.issues.append({
                    "type": "derived_column_error",
                    "column": derived_col,
                    "error": str(e),
                    "severity": "error"
                })
        
        # 2. 重命名列（排除派生列的特殊映射）
        clean_mapping = {k: v for k, v in self.mapping.items() if not k.startswith("_derived")}
        df_sdtm = df.rename(columns=clean_mapping).copy()
        
        # 2.5 【新增】处理派生列（日期转换、等级提取等）
        derived_cols_config = self.metadata.get("derived_columns", {})
        for sdtm_col, transform_config in derived_cols_config.items():
            try:
                source_col_name = transform_config.get("source_col")
                transform_type = transform_config.get("transform")
                
                # 【步骤1】查找源列（使用别名）
                if source_col_name not in df_sdtm.columns:
                    # 从别名表中查找源列
                    source_aliases = self.metadata.get("source_column_aliases", {}).get(sdtm_col, [])
                    source_col_found = None
                    for alias in source_aliases:
                        for col in df_sdtm.columns:
                            if col.lower() == alias.lower():
                                source_col_found = col
                                break
                        if source_col_found:
                            break
                    if not source_col_found:
                        continue  # 源列未找到，跳过
                    source_col_name = source_col_found
                
                # 【步骤2】根据转换类型处理
                if transform_type == "date_normalize":
                    # 日期标准化：转换为 YYYY-MM-DD 格式
                    date_col = df_sdtm[source_col_name]
                    df_sdtm[sdtm_col] = pd.to_datetime(date_col, errors="coerce").dt.strftime('%Y-%m-%d')
                    print(f"[TRANSFORM] 日期标准化: {source_col_name} → {sdtm_col}")
                
                elif transform_type == "extract_grade":
                    # 提取毒性等级：从 "Grade X" 中提取 X
                    pattern = transform_config.get("pattern", "Grade")
                    import re
                    def extract_grade_value(val):
                        if pd.isna(val):
                            return None
                        val_str = str(val).strip()
                        # 移除 "Grade" 前缀，保留数字部分
                        result = re.sub(f"^{pattern}\\s*", "", val_str, flags=re.IGNORECASE).strip()
                        # 只保留数字部分（如 "1" 或 "1-2"）
                        result = re.match(r"[\d\-]+", result)
                        return result.group(0) if result else None
                    
                    df_sdtm[sdtm_col] = df_sdtm[source_col_name].apply(extract_grade_value)
                    print(f"[TRANSFORM] 等级提取: {source_col_name} → {sdtm_col}")
            
            except Exception as e:
                print(f"[WARNING] 派生列处理失败: {sdtm_col} - {e}")
                self.issues.append({
                    "type": "derived_column_transform_error",
                    "column": sdtm_col,
                    "transform": transform_type,
                    "error": str(e),
                    "severity": "warning"
                })
        
        # 3. 添加必需的固定列
        if "DOMAIN" not in df_sdtm.columns:
            df_sdtm.insert(1, "DOMAIN", self.domain)

        # key_seq_var（AESEQ/CMSEQ/LBSEQ/VSSEQ）：按受试者分组递增（优先 USUBJID，其次 SUBJID）
        key_seq_var = self.metadata.get("key_seq_var")
        if key_seq_var and key_seq_var not in df_sdtm.columns:
            try:
                subj_col = None
                if "USUBJID" in df_sdtm.columns:
                    subj_col = "USUBJID"
                elif "SUBJID" in df_sdtm.columns:
                    subj_col = "SUBJID"

                if subj_col:
                    # 保持原行顺序，在每个受试者内从 1 开始递增
                    df_sdtm[key_seq_var] = (
                        df_sdtm.groupby(subj_col, sort=False).cumcount() + 1
                    ).astype("int64")
                else:
                    # 回退：没有任何受试者标识时全局递增
                    df_sdtm[key_seq_var] = range(1, len(df_sdtm) + 1)
            except Exception as e:
                self.issues.append({
                    "type": "seq_derivation_error",
                    "severity": "warning",
                    "column": key_seq_var,
                    "message": f"Failed to derive {key_seq_var}: {e}",
                })
                df_sdtm[key_seq_var] = range(1, len(df_sdtm) + 1)

        # 3.5 派生额外的标识列（SUBJID, AESPID 等）
        # 【SUBJID】从 USUBJID 中提取（例如 2020-689-00CH3-0051 → 0051）
        if "SUBJID" not in df_sdtm.columns and "USUBJID" in df_sdtm.columns:
            try:
                usubjid_series = df_sdtm["USUBJID"].astype(str)
                # 取最后一个 '-' 后面的部分
                subjid_series = usubjid_series.str.split('-').str[-1]
                df_sdtm["SUBJID"] = subjid_series
            except Exception as e:
                self.issues.append({
                    "type": "subjid_derivation_error",
                    "error": str(e),
                    "severity": "warning"
                })

        # 【USUBJID】兜底派生：若缺少 USUBJID 但存在 STUDYID + SUBJID，则按 STUDYID-SUBJID 生成
        if "USUBJID" not in df_sdtm.columns and "STUDYID" in df_sdtm.columns and "SUBJID" in df_sdtm.columns:
            try:
                study_s = df_sdtm["STUDYID"].fillna("").astype(str).str.strip()
                subj_s = df_sdtm["SUBJID"].fillna("").astype(str).str.strip()
                # 避免出现前后多余的 '-'
                df_sdtm["USUBJID"] = (study_s + "-" + subj_s).str.strip("-")
            except Exception as e:
                self.issues.append({
                    "type": "usubjid_derivation_error",
                    "severity": "warning",
                    "message": f"Failed to derive USUBJID from STUDYID+SUBJID: {e}",
                })
        
        # 4. 计算相对天数（AESTDY, AEENDY 等）
        relative_day_cols = self.metadata.get("relative_day_cols", {})
        if relative_day_cols:
            df_sdtm = self._calculate_relative_days(df_sdtm, relative_day_cols)
        
        # 5. 应用医学字典编码（如果适用）
        df_sdtm = self.apply_dictionary_coding(df_sdtm)

        # 5.1 AE 域受控术语兜底（按你的规则）
        if self.domain == "AE":
            # AEOUT: 默认 NOT RECOVERED/NOT RESOLVED
            if "AEOUT" in df_sdtm.columns:
                aeout_col = df_sdtm["AEOUT"]
                if isinstance(aeout_col, pd.DataFrame):
                    aeout_col = aeout_col.iloc[:, 0]
                aeout_s = aeout_col.fillna("").astype(str).str.strip()
                df_sdtm["AEOUT"] = np.where(aeout_s.eq(""), "NOT RECOVERED/NOT RESOLVED", aeout_s)

            # AEENRF: 事件未结束（AEENDTC 为空）时，默认 ONGOING
            # 注：这里按你的口径把 AEENRF 用作标记“ONGOING”
            if "AEENRF" not in df_sdtm.columns:
                df_sdtm["AEENRF"] = ""

            aeenrf_col = df_sdtm["AEENRF"]
            if isinstance(aeenrf_col, pd.DataFrame):
                aeenrf_col = aeenrf_col.iloc[:, 0]
            aeenrf_s = aeenrf_col.fillna("").astype(str).str.strip()

            aeendtc_missing = pd.Series([True] * len(df_sdtm), index=df_sdtm.index)
            if "AEENDTC" in df_sdtm.columns:
                aeendtc_col = df_sdtm["AEENDTC"]
                if isinstance(aeendtc_col, pd.DataFrame):
                    aeendtc_col = aeendtc_col.iloc[:, 0]
                aeendtc_s = aeendtc_col.fillna("").astype(str).str.strip()
                aeendtc_missing = aeendtc_s.eq("")

            df_sdtm["AEENRF"] = np.where(aeenrf_s.eq("") & aeendtc_missing, "ONGOING", aeenrf_s)

        # 6. 按照 SDTM 标准顺序重排列列
        try:
            # 使用定义的列顺序，如果没有定义则使用默认顺序
            if "column_order" in self.metadata:
                sdtm_var_order = self.metadata["column_order"]
            else:
                sdtm_var_order = (
                    self.metadata["required_vars"] + 
                    self.metadata["expected_vars"] + 
                    [c for c in df_sdtm.columns if c not in (self.metadata["required_vars"] + self.metadata["expected_vars"])]
                )
            
            # 只选择实际存在的列
            existing_cols = [c for c in sdtm_var_order if c in df_sdtm.columns]

            # 如果设置了只保留SDTM列，则只保留必需列和期望列（并保持 column_order 顺序）
            if self.metadata.get("keep_only_sdtm_cols", False):
                required_vars = self.metadata.get("required_vars", [])
                expected_vars = self.metadata.get("expected_vars", [])
                allowed = set(required_vars + expected_vars)
                # 在“当前已经存在的列”里按顺序过滤，避免 set() 打乱顺序/误裁剪
                keep_cols = [c for c in existing_cols if c in allowed]
                df_sdtm = df_sdtm[keep_cols]
            # 如果设置了只保留核心变量，则只保留column_order中定义的变量
            elif self.metadata.get("core_vars_only", False):
                df_sdtm = df_sdtm[existing_cols]
            else:
                # 添加未在顺序中定义的列
                remaining_cols = [c for c in df_sdtm.columns if c not in existing_cols]
                final_order = existing_cols + remaining_cols
                df_sdtm = df_sdtm[final_order]
        except Exception as e:
            # 如果重排失败，保持原有列顺序
            pass
        
        # 7. 检查数据质量
        dq_issues = []
        for req_var in self.metadata["required_vars"]:
            if req_var not in df_sdtm.columns:
                dq_issues.append({
                    "type": "missing_required_column",
                    "var": req_var,
                    "severity": "error"
                })
            else:
                req_col = df_sdtm[req_var]
                # 兼容同名列导致的 DataFrame 返回：取第一列用于检查
                if isinstance(req_col, pd.DataFrame):
                    req_col = req_col.iloc[:, 0]

                has_missing = bool(req_col.isna().any())
                if has_missing:
                    missing_count = int(req_col.isna().sum())
                    dq_issues.append({
                        "type": "missing_values_in_required_var",
                        "var": req_var,
                        "count": missing_count,
                        "percentage": round(100 * missing_count / len(df_sdtm), 2),
                        "severity": "error"
                    })
        
        self.issues.extend(dq_issues)
        return df_sdtm, dq_issues
    
    def _calculate_relative_days(self, df: pd.DataFrame, relative_day_cols: Dict[str, Dict]) -> pd.DataFrame:
        """
        【新增】计算相对天数（AESTDY, AEENDY 等）
        
        配置示例（在 DOMAIN_METADATA 中）：
        "relative_day_cols": {
            "AESTDY": {"date_col": "AESTDTC", "reference_date": None},  # None 表示取该受试者第一个有效日期
            "AEENDY": {"date_col": "AEENDTC", "reference_date": None},
        }
        
        相对天数 = 事件日期 - 参考日期 + 1
        （+1 是因为 SDTM 规范中，参考日期本身算作第 1 天）
        """
        
        for relative_col, config in relative_day_cols.items():
            date_col = config.get("date_col")
            reference_date = config.get("reference_date")
            
            # 检查源日期列是否存在
            if date_col not in df.columns:
                self.issues.append({
                    "type": "missing_date_column_for_relative_days",
                    "target_col": relative_col,
                    "source_col": date_col,
                    "severity": "warning"
                })
                continue
            
            try:
                # 转换日期列为 datetime
                dates = pd.to_datetime(df[date_col], errors="coerce")
                
                if reference_date is None:
                    # 按受试者取第一个有效日期作为参考
                    if "USUBJID" in df.columns:
                        ref_dates = df.groupby("USUBJID")[date_col].apply(
                            lambda col: pd.to_datetime(col, errors="coerce").min()
                        )
                        # 创建一个映射
                        reference_series = df["USUBJID"].map(ref_dates)
                    else:
                        # 没有 USUBJID，取全局第一个有效日期
                        reference_series = pd.Series([dates.min()] * len(df))
                else:
                    # 使用指定的参考日期
                    reference_series = pd.Series([pd.to_datetime(reference_date)] * len(df))
                
                # 计算相对天数：（事件日期 - 参考日期）+ 1
                relative_days = (dates - reference_series).dt.days + 1
                
                # 填充到 DataFrame
                df[relative_col] = relative_days.fillna(np.nan)
                
                # 记录统计信息
                valid_count = relative_days.notna().sum()
                self.issues.append({
                    "type": "relative_days_calculated",
                    "target_col": relative_col,
                    "source_col": date_col,
                    "valid_count": int(valid_count),
                    "severity": "info"
                })
                
            except Exception as e:
                self.issues.append({
                    "type": "relative_days_calculation_error",
                    "target_col": relative_col,
                    "source_col": date_col,
                    "error": str(e)[:100],
                    "severity": "warning"
                })
        
        return df
    
    def apply_dictionary_coding(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        应用医学字典编码（泛化支持多个字典类型）
        通过元数据配置定义字典类型和输出列
        
        返回编码后的DataFrame
        """
        # 检查该域是否配置了字典编码
        dict_type = self.metadata.get("med_dict_type")
        if not dict_type:
            return df  # 不需要字典编码
        
        search_col = self.metadata.get("med_dict_search_col")
        output_cols = self.metadata.get("med_dict_output_cols", [])
        
        if not search_col or search_col not in df.columns:
            return df  # 源列不存在
        
        print(f"[CODING] 应用 {dict_type.upper()} 字典编码（列: {search_col}）...")
        
        # 策略：根据字典类型分发
        if dict_type == "meddra":
            # 支持通过环境变量临时禁用 MedDRA 编码（用于测试或环境无模型场景）
            if os.environ.get("DISABLE_MEDDRA", "0") == "1":
                print("[CODING] Skipping MedDRA coding because DISABLE_MEDDRA=1", file=sys.stderr)
                return df
            return self._apply_meddra_coding_impl(df, search_col, output_cols)
        else:
            print(f"[WARN] 暂不支持字典类型: {dict_type}")
            return df
    
    def _apply_meddra_coding_impl(self, df: pd.DataFrame, search_col: str, output_cols: List[str]) -> pd.DataFrame:
        """MedDRA字典编码的具体实现"""

        # 先对术语去重，大幅减少 semantic_search_meddra 调用次数
        terms = df[search_col].astype(str).fillna("").map(lambda x: x.strip())
        uniq_terms = [t for t in terms.unique().tolist() if t]
        total_uniq = len(uniq_terms)
        print(f"[CODING] MedDRA: unique terms={total_uniq}, rows={len(df)}")

        term_to_series: dict[str, pd.Series] = {}
        for idx, term in enumerate(uniq_terms, start=1):
            # 每 50 个打印一次进度，避免看起来“卡死”
            if idx == 1 or idx % 50 == 0 or idx == total_uniq:
                print(f"[CODING] MedDRA progress: {idx}/{total_uniq}")

            search_result = semantic_search_meddra(term, top_k=3, min_score=0.6)
            if (not search_result.get("ok", False)) or search_result.get("not_assigned", True):
                term_to_series[term] = pd.Series({col: np.nan for col in output_cols})
                continue

            best_candidate = search_result["candidates"][0]
            mapping = {
                'AETERM': 'LLT_TERM',
                'AELLT': 'LLT_TERM', 'AELLTCD': 'LLT_CODE',
                'AEDECOD': 'PT_TERM', 'AEPTCD': 'PT_CODE',
                'AEHLT': 'HLT_TERM', 'AEHLTCD': 'HLT_CODE',
                'AEHLGT': 'HLGT_TERM', 'AEHLGTCD': 'HLGT_CODE',
                'AEBODSYS': 'SOC_TERM', 'AEBDSYCD': 'SOC_CODE',
                'AESOC': 'SOC_TERM', 'AESOCCD': 'SOC_CODE'
            }
            out = {}
            for output_col in output_cols:
                key = mapping.get(output_col, output_col)
                out[output_col] = best_candidate.get(key, '')
            term_to_series[term] = pd.Series(out)

        # 回填到每一行
        meddra_cols = terms.map(lambda t: term_to_series.get(t, pd.Series({col: np.nan for col in output_cols})))
        meddra_cols = pd.DataFrame(list(meddra_cols), index=df.index)

        cols_to_add = [col for col in meddra_cols.columns if col not in df.columns]
        if cols_to_add:
            df_with_coding = pd.concat([df, meddra_cols[cols_to_add]], axis=1)
        else:
            df_with_coding = df.copy()

        # 统计编码成功率（只检查新添加的列）
        for output_col in output_cols:
            if output_col in df_with_coding.columns:
                col = df_with_coding[output_col]
                if isinstance(col, pd.DataFrame):
                    col = col.iloc[:, 0]
                encoded_mask = col.notna() & (col.astype(str).str.strip() != "")
                encoded_count = int(encoded_mask.sum())
                total_count = int(len(df_with_coding))
                encode_rate = float(encoded_count / total_count) if total_count > 0 else 0.0
                if encoded_count > 0:
                    print(
                        f"[PASS] {self.metadata.get('med_dict_type', 'MedDRA').upper()}/{output_col} 编码: "
                        f"{encoded_count}/{total_count} ({encode_rate:.1%}) 记录成功编码"
                    )
                break

        return df_with_coding


class ValidationReport:
    """数据质量和规范性检查报告"""

    def __init__(self, domain: str, df: pd.DataFrame):
        self.domain = domain
        self.df = df
        self.issues: List[Dict[str, Any]] = []
        self.metadata = DOMAIN_METADATA.get(domain, {})

    def validate(self) -> Dict[str, Any]:
        """
        执行全面检查（元数据驱动，支持域特定的质量阈值）
        """
        report = {
            "domain": self.domain,
            "timestamp": datetime.now().isoformat(),
            "shape": self.df.shape,
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0}
        }

        # 获取该域定义的质量阈值
        thresholds = self.metadata.get("quality_thresholds", {})
        missing_rate_warning = thresholds.get("missing_rate_warning", 0.2)  # 默认20%
        missing_rate_error = thresholds.get("missing_rate_error", 0.5)      # 默认50%

        # 检查必需列
        for req_var in self.metadata.get("required_vars", []):
            if req_var not in self.df.columns:
                issue = {
                    "type": "missing_required_column",
                    "var": req_var,
                    "severity": "error"
                }
                report["issues"].append(issue)
                report["summary"]["error"] += 1
            else:
                # 检查缺失值
                try:
                    missing_count = int(self.df[req_var].isna().sum())
                    if missing_count > 0:
                        issue = {
                            "type": "missing_values_in_required_var",
                            "var": req_var,
                            "count": missing_count,
                            "percentage": round(100 * missing_count / len(self.df), 2),
                            "severity": "error"
                        }
                        report["issues"].append(issue)
                        report["summary"]["error"] += 1
                except Exception:
                    pass

        # 检查期望列的缺失率（使用域特定阈值）
        # 业务兜底：某些变量缺失并不代表错误（例如 AEENRF 在本项目中用于标记 ONGOING）
        skip_missing_rate_vars = set(self.metadata.get("skip_missing_rate_vars", []))
        if self.domain == "AE":
            skip_missing_rate_vars.add("AEENRF")

        # 汇总低缺失率的 info 信息（避免过多的 info 消息）
        low_missing_vars = []  # 缺失率 < 1% 的变量
        info_threshold = 1.0  # info 级别的缺失率阈值

        for exp_var in self.metadata.get("expected_vars", []):
            if exp_var in skip_missing_rate_vars:
                continue
            if exp_var in self.df.columns:
                try:
                    missing_count = int(self.df[exp_var].isna().sum())
                    if missing_count > 0:
                        pct = 100 * missing_count / len(self.df)

                        # 根据域特定阈值判断严重性
                        if pct > missing_rate_error * 100:
                            severity = "error"
                        elif pct > missing_rate_warning * 100:
                            severity = "warning"
                        else:
                            severity = "info"

                        # 如果是 info 级别且缺失率 < 1%，加入汇总列表
                        if severity == "info" and pct < info_threshold:
                            low_missing_vars.append(f"{exp_var} ({pct:.2f}%)")
                        else:
                            # 否则单独生成问题项
                            issue = {
                                "type": "high_missing_in_expected_var",
                                "var": exp_var,
                                "count": missing_count,
                                "percentage": round(pct, 2),
                                "threshold": {"warning": missing_rate_warning * 100, "error": missing_rate_error * 100},
                                "severity": severity
                            }
                            report["issues"].append(issue)
                            report["summary"][severity] += 1
                except Exception:
                    pass

        # 若有汇总的低缺失率变量，生成一条 info 汇总消息
        if low_missing_vars:
            issue = {
                "type": "minor_missing_in_expected_vars",
                "vars": low_missing_vars,
                "count": len(low_missing_vars),
                "severity": "info",
                "message": f"Minor missing rates (<{info_threshold}%) in {len(low_missing_vars)} expected variables"
            }
            report["issues"].append(issue)
            report["summary"]["info"] += 1

        # 序列号检查：按受试者分组检查 1..n 连续（优先 USUBJID，其次 SUBJID）
        if self.metadata.get("key_seq_var"):
            seq_var = self.metadata["key_seq_var"]
            if seq_var in self.df.columns:
                try:
                    subj_col = None
                    if "USUBJID" in self.df.columns:
                        subj_col = "USUBJID"
                    elif "SUBJID" in self.df.columns:
                        subj_col = "SUBJID"

                    if subj_col:
                        bad_groups = 0
                        for _, grp in self.df.groupby(subj_col, sort=False):
                            seq_vals = pd.to_numeric(grp[seq_var], errors="coerce").dropna().astype(int)
                            if len(seq_vals) == 0:
                                continue
                            expected = list(range(1, len(seq_vals) + 1))
                            if list(seq_vals) != expected:
                                bad_groups += 1
                                if bad_groups >= 1:
                                    break
                        if bad_groups > 0:
                            issue = {
                                "type": "seq_not_sequential",
                                "var": seq_var,
                                "severity": "warning",
                                "message": f"{seq_var} not sequential within {subj_col} or has gaps"
                            }
                            report["issues"].append(issue)
                            report["summary"]["warning"] += 1
                    else:
                        # 没有受试者列时，退化为全表检查
                        seq_vals = pd.to_numeric(self.df[seq_var], errors='coerce').dropna().astype(int)
                        expected_seq = list(range(1, len(seq_vals) + 1))
                        if len(seq_vals) > 0 and list(seq_vals) != expected_seq:
                            issue = {
                                "type": "seq_not_sequential",
                                "var": seq_var,
                                "severity": "warning",
                                "message": f"{seq_var} not sequential or has gaps"
                            }
                            report["issues"].append(issue)
                            report["summary"]["warning"] += 1
                except Exception:
                    pass

        return report


def process_sdtm_conversion(
    source_file: str,
    domain: str,
    output_dir: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    完整的多域转换流程
    
    Args:
        source_file: 源文件路径，支持绝对路径或仅文件名（将在 data/raw 中查找）
        domain: SDTM 域（如 'AE', 'CM'）
        output_dir: 输出目录。若为 None，使用 data/output/
    
    返回 (成功标志, 结果字典)
    """
    # 解析输入文件路径（支持泛化）
    if not os.path.isabs(source_file):
        # 若为相对路径，在 RAW_DATA_DIR 中查找
        source_file = os.path.join(RAW_DATA_DIR, source_file)
    
    if not os.path.exists(source_file):
        return False, {

            "domain": domain,
            "source_file": source_file,
            "errors": [{"error": f"Source file not found: {source_file}"}]
        }
    
    # 若未指定输出目录，使用默认的 data/output/
    if output_dir is None:
        output_dir = OUTPUT_DATA_DIR
    
    result = {
        "domain": domain,
        "source_file": source_file,
        "output_dir": output_dir,
        "steps": [],
        "errors": [],
    }
    
    try:
        # 1. 读源文件
        print(f"[CONVERT] Reading source file: {source_file}")
        if source_file.endswith(".xlsx") or source_file.endswith(".xls"):
            df_source = pd.read_excel(source_file)
        elif source_file.endswith(".csv"):
            df_source = pd.read_csv(source_file)
        else:
            raise ValueError(f"Unsupported file format: {source_file}")
        
        result["steps"].append({
            "name": "read_source",
            "status": "success",
            "shape": df_source.shape
        })
        
        # 2. 初始化转换器
        transformer = SDTMTransformer(domain)
        
        # 3. 分析源数据
        source_schema = transformer.infer_source_schema(df_source)
        result["source_schema"] = source_schema
        result["steps"].append({
            "name": "infer_schema",
            "status": "success",
            "columns": len(source_schema["columns"])
        })
        
        # 4. 提议映射
        mapping = transformer.propose_mapping(source_schema)
        result["proposed_mapping"] = mapping
        result["steps"].append({
            "name": "propose_mapping",
            "status": "success",
            "mapped_cols": len(mapping)
        })
        
        # 5. 标准化数据
        df_std, std_issues = transformer.standardize_data(df_source)
        result["standardization_issues"] = std_issues
        result["steps"].append({
            "name": "standardize",
            "status": "success",
            "issues": len(std_issues)
        })
        
        # 6. 应用映射转换
        df_sdtm, map_issues = transformer.apply_mapping(df_std)
        result["transformation_issues"] = map_issues
        result["steps"].append({
            "name": "apply_mapping",
            "status": "success",
            "issues": len(map_issues),
            "output_shape": df_sdtm.shape
        })
        
        # 7. 验证
        validator = ValidationReport(domain, df_sdtm)
        validation_report = validator.validate()
        result["validation_report"] = validation_report
        result["steps"].append({
            "name": "validate",
            "status": "success",
            "issues_count": len(validation_report["issues"])
        })
        
        # 8. 输出
        os.makedirs(output_dir, exist_ok=True)
        
        sdtm_file = os.path.join(output_dir, f"SDTM_{domain}.xlsx")
        df_sdtm.to_excel(sdtm_file, index=False, engine="openpyxl")
        result["sdtm_file"] = sdtm_file
        
        mapping_file = os.path.join(output_dir, f"mapping_{domain}.json")
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
        result["mapping_file"] = mapping_file
        
        report_file = os.path.join(output_dir, f"validation_{domain}.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(validation_report, f, indent=2, ensure_ascii=False)
        result["report_file"] = report_file
        
        result["steps"].append({
            "name": "export",
 "status": "success",
            "files": [sdtm_file, mapping_file, report_file]
        })
        
        return True, result
    
    except Exception as e:
        result["errors"].append({
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        return False, result

