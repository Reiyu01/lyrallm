"""
安全標籤與分類系統

定義了內容安全分類、風險等級、機密資料類型等資料結構。
用於 SLM 分析後的安全評估和策略決策。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class SafetyLevel(str, Enum):
    """安全等級枚舉"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidentialDataType(str, Enum):
    """機密資料類型枚舉"""
    NONE = "none"
    PII = "pii"                      # 個人身份資訊 (Personal Identifiable Information)
    FINANCIAL = "financial"          # 財務資訊 (信用卡、銀行帳號)
    MEDICAL = "medical"              # 醫療健康資訊
    TRADE_SECRET = "trade_secret"    # 商業機密
    CREDENTIALS = "credentials"      # 憑證資訊 (密碼、API key、Token)
    INTERNAL = "internal"            # 內部資料


@dataclass
class SafetyLabels:
    """
    安全標籤資料結構
    
    包含多個維度的安全評估結果，用於決定內容是否可以處理、
    需要何種級別的權限、是否需要審計等。
    """
    
    # 內容安全維度
    violence: SafetyLevel = SafetyLevel.NONE
    sexual: SafetyLevel = SafetyLevel.NONE
    hate_speech: SafetyLevel = SafetyLevel.NONE
    self_harm: SafetyLevel = SafetyLevel.NONE
    
    # 資料安全維度
    confidential_data: ConfidentialDataType = ConfidentialDataType.NONE
    
    # 攻擊檢測
    jailbreak_attempt: bool = False
    
    # 整體風險評估
    risk_level: SafetyLevel = SafetyLevel.NONE
    
    # 詳細資訊
    details: List[str] = field(default_factory=list)
    jailbreak_indicators: List[str] = field(default_factory=list)
    
    def is_safe(self) -> bool:
        """
        判斷內容是否安全可處理
        
        Returns:
            bool: True 表示內容安全，可以正常處理
        """
        return (
            self.risk_level in [SafetyLevel.NONE, SafetyLevel.LOW] and
            not self.jailbreak_attempt and
            self.violence in [SafetyLevel.NONE, SafetyLevel.LOW] and
            self.sexual in [SafetyLevel.NONE, SafetyLevel.LOW] and
            self.hate_speech in [SafetyLevel.NONE, SafetyLevel.LOW] and
            self.self_harm in [SafetyLevel.NONE, SafetyLevel.LOW]
        )
    
    def requires_escalation(self) -> bool:
        """
        判斷是否需要升級處理（通知管理員、記錄告警等）
        
        Returns:
            bool: True 表示需要升級處理
        """
        return (
            self.risk_level in [SafetyLevel.HIGH, SafetyLevel.CRITICAL] or
            self.jailbreak_attempt or
            self.violence in [SafetyLevel.HIGH, SafetyLevel.CRITICAL] or
            self.sexual in [SafetyLevel.HIGH, SafetyLevel.CRITICAL] or
            self.confidential_data in [
                ConfidentialDataType.TRADE_SECRET, 
                ConfidentialDataType.CREDENTIALS
            ]
        )
    
    def requires_privileged_access(self) -> bool:
        """
        判斷是否需要特權存取（企業級帳號、特定角色等）
        
        Returns:
            bool: True 表示需要特權存取
        """
        return self.confidential_data in [
            ConfidentialDataType.FINANCIAL,
            ConfidentialDataType.MEDICAL,
            ConfidentialDataType.TRADE_SECRET,
            ConfidentialDataType.CREDENTIALS
        ]
    
    def get_max_safety_level(self) -> SafetyLevel:
        """
        獲取所有安全維度中的最高風險等級
        
        Returns:
            SafetyLevel: 最高風險等級
        """
        levels = [self.violence, self.sexual, self.hate_speech, self.self_harm, self.risk_level]
        
        # 定義等級順序
        level_order = {
            SafetyLevel.NONE: 0,
            SafetyLevel.LOW: 1,
            SafetyLevel.MEDIUM: 2,
            SafetyLevel.HIGH: 3,
            SafetyLevel.CRITICAL: 4
        }
        
        # 找出最高等級
        max_level = max(levels, key=lambda x: level_order.get(x, 0))
        return max_level
    
    def to_dict(self) -> Dict[str, Any]:
        """
        轉換為字典格式，方便序列化和記錄
        
        Returns:
            Dict[str, Any]: 字典格式的安全標籤
        """
        return {
            'violence': self.violence.value,
            'sexual': self.sexual.value,
            'hate_speech': self.hate_speech.value,
            'self_harm': self.self_harm.value,
            'confidential_data': self.confidential_data.value,
            'jailbreak_attempt': self.jailbreak_attempt,
            'risk_level': self.risk_level.value,
            'details': self.details,
            'jailbreak_indicators': self.jailbreak_indicators,
            'is_safe': self.is_safe(),
            'requires_escalation': self.requires_escalation(),
            'requires_privileged_access': self.requires_privileged_access()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SafetyLabels':
        """
        從字典創建 SafetyLabels 實例
        
        Args:
            data: 包含安全標籤資訊的字典
            
        Returns:
            SafetyLabels: 新的實例
        """
        return cls(
            violence=SafetyLevel(data.get('violence', 'none')),
            sexual=SafetyLevel(data.get('sexual', 'none')),
            hate_speech=SafetyLevel(data.get('hate_speech', 'none')),
            self_harm=SafetyLevel(data.get('self_harm', 'none')),
            confidential_data=ConfidentialDataType(data.get('confidential_data', 'none')),
            jailbreak_attempt=data.get('jailbreak_attempt', False),
            risk_level=SafetyLevel(data.get('risk_level', 'none')),
            details=data.get('details', []),
            jailbreak_indicators=data.get('jailbreak_indicators', [])
        )
    
    @classmethod
    def create_safe_default(cls) -> 'SafetyLabels':
        """
        創建一個安全的預設實例（所有指標都是安全的）
        
        Returns:
            SafetyLabels: 安全的預設實例
        """
        return cls(
            violence=SafetyLevel.NONE,
            sexual=SafetyLevel.NONE,
            hate_speech=SafetyLevel.NONE,
            self_harm=SafetyLevel.NONE,
            confidential_data=ConfidentialDataType.NONE,
            jailbreak_attempt=False,
            risk_level=SafetyLevel.NONE,
            details=["Default safe labels - no analysis performed"],
            jailbreak_indicators=[]
        )
