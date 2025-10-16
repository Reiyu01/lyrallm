"""
工具需求與授權

定義了工具類型、工具需求、工具授權等資料結構。
用於 SLM 判斷使用者請求是否需要額外工具（如網頁搜尋、代碼解釋器等）。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set


class ToolType(str, Enum):
    """工具類型枚舉"""
    NONE = "none"
    WEB_SEARCH = "web_search"
    CODE_INTERPRETER = "code_interpreter"
    IMAGE_GENERATION = "image_generation"
    DATA_ANALYSIS = "data_analysis"
    FILE_UPLOAD = "file_upload"
    API_CALL = "api_call"
    DATABASE_QUERY = "database_query"
    DOCUMENT_RETRIEVAL = "document_retrieval"


class ToolPriority(str, Enum):
    """工具優先級枚舉"""
    OPTIONAL = "optional"      # 可選，可以不用工具回答
    RECOMMENDED = "recommended"  # 建議使用，但不強制
    REQUIRED = "required"      # 必須使用，否則無法正確回答


@dataclass
class ToolRequirement:
    """
    單一工具需求資料結構
    
    描述某個工具的需求詳情，包括工具類型、優先級、原因等。
    """
    
    tool_type: ToolType
    priority: ToolPriority = ToolPriority.OPTIONAL
    reason: str = ""
    
    # 工具特定參數（選填）
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'tool_type': self.tool_type.value,
            'priority': self.priority.value,
            'reason': self.reason,
            'parameters': self.parameters
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolRequirement':
        """從字典創建實例"""
        return cls(
            tool_type=ToolType(data['tool_type']),
            priority=ToolPriority(data.get('priority', 'optional')),
            reason=data.get('reason', ''),
            parameters=data.get('parameters', {})
        )


@dataclass
class ToolRequirements:
    """
    工具需求集合資料結構
    
    包含 SLM 分析後判斷的所有工具需求。
    """
    
    # 工具需求清單
    required_tools: List[ToolRequirement] = field(default_factory=list)
    
    # 是否需要任何工具
    needs_tools: bool = False
    
    # 分析詳情
    analysis_notes: List[str] = field(default_factory=list)
    
    def has_tool(self, tool_type: ToolType) -> bool:
        """
        檢查是否需要特定工具
        
        Args:
            tool_type: 工具類型
            
        Returns:
            bool: True 表示需要該工具
        """
        return any(req.tool_type == tool_type for req in self.required_tools)
    
    def get_tool_requirement(self, tool_type: ToolType) -> Optional[ToolRequirement]:
        """
        獲取特定工具的需求詳情
        
        Args:
            tool_type: 工具類型
            
        Returns:
            Optional[ToolRequirement]: 工具需求，如果不存在則返回 None
        """
        for req in self.required_tools:
            if req.tool_type == tool_type:
                return req
        return None
    
    def get_required_tools(self) -> List[ToolRequirement]:
        """
        獲取所有標記為 REQUIRED 的工具
        
        Returns:
            List[ToolRequirement]: 必須使用的工具清單
        """
        return [req for req in self.required_tools if req.priority == ToolPriority.REQUIRED]
    
    def get_recommended_tools(self) -> List[ToolRequirement]:
        """
        獲取所有標記為 RECOMMENDED 的工具
        
        Returns:
            List[ToolRequirement]: 建議使用的工具清單
        """
        return [req for req in self.required_tools if req.priority == ToolPriority.RECOMMENDED]
    
    def get_optional_tools(self) -> List[ToolRequirement]:
        """
        獲取所有標記為 OPTIONAL 的工具
        
        Returns:
            List[ToolRequirement]: 可選工具清單
        """
        return [req for req in self.required_tools if req.priority == ToolPriority.OPTIONAL]
    
    def get_tool_types(self) -> Set[ToolType]:
        """
        獲取所有需要的工具類型集合
        
        Returns:
            Set[ToolType]: 工具類型集合
        """
        return {req.tool_type for req in self.required_tools}
    
    def add_tool(
        self, 
        tool_type: ToolType, 
        priority: ToolPriority = ToolPriority.OPTIONAL,
        reason: str = "",
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        新增工具需求
        
        Args:
            tool_type: 工具類型
            priority: 優先級
            reason: 需要該工具的原因
            parameters: 工具特定參數
        """
        if parameters is None:
            parameters = {}
        
        # 避免重複新增
        if not self.has_tool(tool_type):
            self.required_tools.append(
                ToolRequirement(
                    tool_type=tool_type,
                    priority=priority,
                    reason=reason,
                    parameters=parameters
                )
            )
            self.needs_tools = True
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'required_tools': [req.to_dict() for req in self.required_tools],
            'needs_tools': self.needs_tools,
            'analysis_notes': self.analysis_notes,
            'tool_types': [t.value for t in self.get_tool_types()],
            'has_required_tools': len(self.get_required_tools()) > 0,
            'has_recommended_tools': len(self.get_recommended_tools()) > 0
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolRequirements':
        """從字典創建實例"""
        required_tools = [
            ToolRequirement.from_dict(req) 
            for req in data.get('required_tools', [])
        ]
        
        return cls(
            required_tools=required_tools,
            needs_tools=data.get('needs_tools', False),
            analysis_notes=data.get('analysis_notes', [])
        )
    
    @classmethod
    def create_no_tools(cls) -> 'ToolRequirements':
        """
        創建不需要任何工具的實例
        
        Returns:
            ToolRequirements: 不需要工具的實例
        """
        return cls(
            required_tools=[],
            needs_tools=False,
            analysis_notes=["No additional tools required"]
        )
    
    @classmethod
    def create_web_search(cls, reason: str = "需要即時資訊", priority: ToolPriority = ToolPriority.REQUIRED) -> 'ToolRequirements':
        """
        創建需要網頁搜尋的實例
        
        Args:
            reason: 需要的原因
            priority: 優先級
            
        Returns:
            ToolRequirements: 需要網頁搜尋的實例
        """
        instance = cls(needs_tools=True)
        instance.add_tool(ToolType.WEB_SEARCH, priority=priority, reason=reason)
        return instance
    
    @classmethod
    def create_code_interpreter(cls, reason: str = "需要執行代碼", priority: ToolPriority = ToolPriority.REQUIRED) -> 'ToolRequirements':
        """
        創建需要代碼解釋器的實例
        
        Args:
            reason: 需要的原因
            priority: 優先級
            
        Returns:
            ToolRequirements: 需要代碼解釋器的實例
        """
        instance = cls(needs_tools=True)
        instance.add_tool(ToolType.CODE_INTERPRETER, priority=priority, reason=reason)
        return instance


@dataclass
class ToolAuthorization:
    """
    工具授權資料結構
    
    用於檢查使用者是否有權限使用特定工具。
    """
    
    # 使用者被授權的工具
    authorized_tools: Set[ToolType] = field(default_factory=set)
    
    # 被拒絕的工具（明確禁止）
    denied_tools: Set[ToolType] = field(default_factory=set)
    
    # 授權原因/來源
    authorization_source: str = "default"
    
    def is_authorized(self, tool_type: ToolType) -> bool:
        """
        檢查是否被授權使用特定工具
        
        Args:
            tool_type: 工具類型
            
        Returns:
            bool: True 表示有權限使用
        """
        # 明確拒絕優先
        if tool_type in self.denied_tools:
            return False
        
        # 檢查是否在授權清單中
        return tool_type in self.authorized_tools
    
    def can_use_all_tools(self, tool_requirements: ToolRequirements) -> bool:
        """
        檢查是否可以使用所有需要的工具
        
        Args:
            tool_requirements: 工具需求
            
        Returns:
            bool: True 表示所有需要的工具都有權限使用
        """
        for req in tool_requirements.required_tools:
            if not self.is_authorized(req.tool_type):
                return False
        return True
    
    def get_unauthorized_tools(self, tool_requirements: ToolRequirements) -> List[ToolType]:
        """
        獲取所有沒有權限的工具
        
        Args:
            tool_requirements: 工具需求
            
        Returns:
            List[ToolType]: 沒有權限的工具清單
        """
        unauthorized = []
        for req in tool_requirements.required_tools:
            if not self.is_authorized(req.tool_type):
                unauthorized.append(req.tool_type)
        return unauthorized
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'authorized_tools': [t.value for t in self.authorized_tools],
            'denied_tools': [t.value for t in self.denied_tools],
            'authorization_source': self.authorization_source
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolAuthorization':
        """從字典創建實例"""
        return cls(
            authorized_tools={ToolType(t) for t in data.get('authorized_tools', [])},
            denied_tools={ToolType(t) for t in data.get('denied_tools', [])},
            authorization_source=data.get('authorization_source', 'default')
        )
    
    @classmethod
    def create_free_tier(cls) -> 'ToolAuthorization':
        """
        創建免費版使用者的工具授權
        
        Returns:
            ToolAuthorization: 免費版授權（僅基礎工具）
        """
        return cls(
            authorized_tools={
                # 免費版僅支援基礎功能
            },
            denied_tools={
                ToolType.WEB_SEARCH,
                ToolType.CODE_INTERPRETER,
                ToolType.IMAGE_GENERATION,
                ToolType.DATA_ANALYSIS,
                ToolType.DATABASE_QUERY
            },
            authorization_source="free_tier"
        )
    
    @classmethod
    def create_pro_tier(cls) -> 'ToolAuthorization':
        """
        創建專業版使用者的工具授權
        
        Returns:
            ToolAuthorization: 專業版授權
        """
        return cls(
            authorized_tools={
                ToolType.WEB_SEARCH,
                ToolType.CODE_INTERPRETER,
                ToolType.IMAGE_GENERATION,
                ToolType.FILE_UPLOAD
            },
            authorization_source="pro_tier"
        )
    
    @classmethod
    def create_enterprise_tier(cls) -> 'ToolAuthorization':
        """
        創建企業版使用者的工具授權
        
        Returns:
            ToolAuthorization: 企業版授權（所有工具）
        """
        return cls(
            authorized_tools={
                ToolType.WEB_SEARCH,
                ToolType.CODE_INTERPRETER,
                ToolType.IMAGE_GENERATION,
                ToolType.DATA_ANALYSIS,
                ToolType.FILE_UPLOAD,
                ToolType.API_CALL,
                ToolType.DATABASE_QUERY,
                ToolType.DOCUMENT_RETRIEVAL
            },
            authorization_source="enterprise_tier"
        )
