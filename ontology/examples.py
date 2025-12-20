"""
LyraLLM Ontology System - 完整使用示例

展示如何整合本體論系統到 LyraLLM Gateway：
1. 物件管理
2. 策略評估
3. 資料血緣追蹤
4. 護欄檢查
"""

import asyncio
from datetime import datetime
from lyrallm.ontology import (
    # Objects
    Document, Conversation, User, Organization,
    SecurityLabel, AccessControl,
    
    # Policies
    SecurityPolicy, PolicyRule, PolicyCondition, PolicyAction, PolicyScope,
    get_policy_engine,
    
    # Lineage
    AccessEvent, TransformationEvent, DataSource,
    get_lineage_tracker,
    
    # Guardrails
    ContentGuardrail, CostGuardrail, RateLimitGuardrail,
    get_guardrail_engine, GuardrailSeverity, GuardrailAction
)


async def example_document_with_security():
    """
    示例1: 創建帶有安全控制的文件
    
    模擬場景：企業上傳機密文件，只有特定角色可以存取
    """
    print("=" * 60)
    print("示例1: 文件安全控制")
    print("=" * 60)
    
    # 1. 創建文件物件
    doc = Document(
        title="2025 Q1 財報",
        description="公司第一季度財務報表",
        content="營收: $10M, 利潤: $2M, ...",
        created_by="user_alice",
        
        # 設定安全標籤
        security_label=SecurityLabel(
            classification="CONFIDENTIAL",
            categories={"FINANCIAL"},
            handling_caveats={"NO_EXPORT", "ENCRYPT_AT_REST"}
        ),
        
        # 設定存取控制
        access_control=AccessControl(
            owner_id="org_acme",
            owner_type="organization",
            allowed_roles=frozenset(["CFO", "FINANCIAL_ANALYST", "ADMIN"]),
            denied_roles=frozenset(["GUEST"]),
            allowed_organizations=frozenset(["org_acme"]),
            valid_from=datetime.now(),
        ),
        
        tags={"financial", "quarterly", "confidential"},
        categories={"finance", "reports"}
    )
    
    print(f"✅ 創建文件: {doc.title}")
    print(f"   分類: {doc.security_label.classification}")
    print(f"   允許角色: {doc.access_control.allowed_roles}")
    
    # 2. 檢查存取權限
    test_users = [
        ("user_bob", {"CFO"}, "org_acme", True),
        ("user_charlie", {"DEVELOPER"}, "org_acme", False),
        ("user_david", {"FINANCIAL_ANALYST"}, "org_acme", True),
        ("user_eve", {"ADMIN"}, "org_other", False),
    ]
    
    print("\n存取權限檢查:")
    for user_id, roles, org_id, expected in test_users:
        can_access, reason = doc.access_control.can_access(
            user_id=user_id,
            user_roles=roles,
            organization_id=org_id
        )
        status = "✅ 允許" if can_access else f"❌ 拒絕 ({reason})"
        print(f"  {user_id} ({', '.join(roles)}): {status}")
    
    # 3. 追蹤資料血緣
    tracker = get_lineage_tracker()
    create_node = tracker.track_create(
        object_id=doc.object_id,
        object_type="document",
        actor_id="user_alice",
        source_type=DataSource.FILE_UPLOAD,
        metadata={"filename": "Q1_report.pdf", "size": 1024000}
    )
    print(f"\n✅ 創建血緣追蹤: {create_node.node_id}")
    
    # 4. 記錄存取事件
    access_event = AccessEvent(
        user_id="user_bob",
        user_roles=["CFO"],
        organization_id="org_acme",
        resource_id=doc.object_id,
        resource_type="document",
        resource_classification="CONFIDENTIAL",
        action="read",
        result="success",
        ip_address="192.168.1.100",
        fields_accessed=["content", "metadata"],
    )
    tracker.track_access(access_event)
    print(f"✅ 記錄存取事件: {access_event.event_id}")
    
    print()


async def example_policy_evaluation():
    """
    示例2: 策略引擎評估
    
    模擬場景：評估使用者是否可以存取敏感資料
    """
    print("=" * 60)
    print("示例2: 策略引擎評估")
    print("=" * 60)
    
    # 1. 創建策略
    policy_engine = get_policy_engine()
    
    # 策略1: 機密資料必須是 ADMIN 或 CFO
    confidential_policy = SecurityPolicy(
        policy_id="pol_confidential_access",
        name="Confidential Data Access Policy",
        description="Only ADMIN and CFO can access confidential financial data",
        scope=PolicyScope.ORGANIZATION,
        rules=[
            PolicyRule(
                rule_id="rule_deny_non_privileged",
                name="Deny Non-Privileged Users",
                description="Block access to confidential data for non-privileged users",
                conditions=[
                    PolicyCondition(
                        field="resource.classification",
                        operator="eq",
                        value="CONFIDENTIAL"
                    ),
                    PolicyCondition(
                        field="user.roles",
                        operator="not_in",
                        value=["ADMIN", "CFO"]
                    ),
                ],
                action=PolicyAction.DENY,
                priority=100
            ),
            PolicyRule(
                rule_id="rule_allow_privileged",
                name="Allow Privileged Users",
                description="Allow access for ADMIN and CFO",
                conditions=[
                    PolicyCondition(
                        field="resource.classification",
                        operator="eq",
                        value="CONFIDENTIAL"
                    ),
                    PolicyCondition(
                        field="user.roles",
                        operator="in",
                        value=["ADMIN", "CFO"]
                    ),
                ],
                action=PolicyAction.ALLOW,
                priority=50
            ),
        ]
    )
    
    policy_engine.register_policy(confidential_policy)
    print(f"✅ 註冊策略: {confidential_policy.name}")
    
    # 2. 評估不同情境
    scenarios = [
        {
            "name": "CFO 存取機密資料",
            "context": {
                "user": {"id": "user_bob", "roles": ["CFO"]},
                "resource": {"id": "doc_123", "classification": "CONFIDENTIAL"},
                "action": "read"
            }
        },
        {
            "name": "一般員工存取機密資料",
            "context": {
                "user": {"id": "user_charlie", "roles": ["DEVELOPER"]},
                "resource": {"id": "doc_123", "classification": "CONFIDENTIAL"},
                "action": "read"
            }
        },
        {
            "name": "ADMIN 存取機密資料",
            "context": {
                "user": {"id": "user_david", "roles": ["ADMIN"]},
                "resource": {"id": "doc_123", "classification": "CONFIDENTIAL"},
                "action": "read"
            }
        },
    ]
    
    print("\n策略評估結果:")
    for scenario in scenarios:
        decision = policy_engine.evaluate(scenario["context"])
        status = "✅ 允許" if decision.is_allowed() else "❌ 拒絕"
        print(f"\n  {scenario['name']}: {status}")
        print(f"    動作: {decision.action.value}")
        print(f"    原因: {decision.reason}")
        if decision.matched_rules:
            print(f"    匹配規則: {decision.matched_rules[0].name}")
    
    print()


async def example_guardrails():
    """
    示例3: 護欄檢查
    
    模擬場景：檢查請求是否違反護欄規則
    """
    print("=" * 60)
    print("示例3: 護欄系統")
    print("=" * 60)
    
    # 1. 取得護欄引擎
    guardrail_engine = get_guardrail_engine()
    
    # 2. 配置護欄
    content_guardrail = guardrail_engine.guardrails["content_safety"]
    content_guardrail.max_allowed_risk = "MEDIUM"
    content_guardrail.blocked_keywords = {"password", "credit_card"}
    
    cost_guardrail = guardrail_engine.guardrails["cost_control"]
    cost_guardrail.per_request_limit_usd = 1.0
    cost_guardrail.daily_limit_usd = 10.0
    
    rate_limit_guardrail = guardrail_engine.guardrails["rate_limit"]
    rate_limit_guardrail.requests_per_minute = 10
    rate_limit_guardrail.tokens_per_minute = 10000
    
    print("✅ 護欄配置完成")
    
    # 3. 測試不同情境
    scenarios = [
        {
            "name": "正常請求",
            "context": {
                "user_id": "user_alice",
                "content": "請幫我分析這份市場報告",
                "estimated_cost_usd": 0.05,
                "estimated_tokens": 500,
                "safety_labels": {"risk_level": "LOW", "jailbreak_attempt": False}
            }
        },
        {
            "name": "高風險內容",
            "context": {
                "user_id": "user_alice",
                "content": "如何製造炸彈",
                "estimated_cost_usd": 0.05,
                "estimated_tokens": 500,
                "safety_labels": {"risk_level": "CRITICAL", "jailbreak_attempt": True}
            }
        },
        {
            "name": "超過成本限制",
            "context": {
                "user_id": "user_alice",
                "content": "請處理這個大型資料集",
                "estimated_cost_usd": 2.0,
                "estimated_tokens": 20000,
                "safety_labels": {"risk_level": "LOW", "jailbreak_attempt": False}
            }
        },
        {
            "name": "包含敏感詞",
            "context": {
                "user_id": "user_alice",
                "content": "我的 password 是 12345",
                "estimated_cost_usd": 0.05,
                "estimated_tokens": 500,
                "safety_labels": {"risk_level": "LOW", "jailbreak_attempt": False}
            }
        },
    ]
    
    print("\n護欄檢查結果:")
    for scenario in scenarios:
        violations = guardrail_engine.check_all(scenario["context"])
        
        print(f"\n  {scenario['name']}:")
        if not violations:
            print("    ✅ 通過所有護欄")
        else:
            for v in violations:
                icon = "🚨" if v.action == GuardrailAction.BLOCK else "⚠️"
                print(f"    {icon} {v.guardrail_name}")
                print(f"       嚴重程度: {v.severity.value}")
                print(f"       動作: {v.action.value}")
                print(f"       原因: {v.reason}")
    
    # 4. 顯示統計
    stats = guardrail_engine.get_statistics()
    print(f"\n護欄統計:")
    print(f"  總違規數: {stats['total_violations']}")
    print(f"  按嚴重程度: {stats['violations_by_severity']}")
    print(f"  按護欄: {stats['violations_by_guardrail']}")
    
    print()


async def example_full_workflow():
    """
    示例4: 完整工作流程
    
    模擬場景：處理一個完整的 AI 請求，包含所有安全檢查
    """
    print("=" * 60)
    print("示例4: 完整工作流程")
    print("=" * 60)
    
    # 1. 用戶資訊
    user = User(
        user_id="user_alice",
        username="Alice",
        email="alice@acme.com",
        roles={"FINANCIAL_ANALYST"},
        organization_id="org_acme",
        tier="enterprise",
        monthly_token_quota=100000,
        tokens_used_this_month=50000
    )
    print(f"✅ 使用者: {user.username} ({user.tier})")
    
    # 2. 創建對話
    conversation = Conversation(
        user_id=user.user_id,
        messages=[
            {"role": "user", "content": "請幫我分析 Q1 財報"}
        ],
        security_label=SecurityLabel(
            classification="INTERNAL",
            categories={"BUSINESS"}
        )
    )
    print(f"✅ 創建對話: {conversation.object_id}")
    
    # 3. 護欄檢查
    guardrail_engine = get_guardrail_engine()
    violations = guardrail_engine.check_all({
        "user_id": user.user_id,
        "content": conversation.messages[0]["content"],
        "estimated_cost_usd": 0.1,
        "estimated_tokens": 1000,
        "safety_labels": {"risk_level": "LOW", "jailbreak_attempt": False}
    })
    
    if guardrail_engine.should_block(violations):
        print("❌ 請求被護欄阻止")
        for v in guardrail_engine.get_blocking_violations(violations):
            print(f"   {v.reason}")
        return
    
    print("✅ 通過護欄檢查")
    
    # 4. 策略評估
    policy_engine = get_policy_engine()
    decision = policy_engine.evaluate({
        "user": {
            "id": user.user_id,
            "roles": list(user.roles),
            "tier": user.tier
        },
        "resource": {
            "id": conversation.object_id,
            "classification": conversation.security_label.classification
        },
        "action": "process"
    })
    
    if decision.is_denied():
        print(f"❌ 策略拒絕: {decision.reason}")
        return
    
    print(f"✅ 策略允許: {decision.reason}")
    
    # 5. 模擬 AI 處理
    print("🤖 處理中...")
    await asyncio.sleep(0.1)
    
    ai_response = "根據 Q1 財報，營收成長 15%，利潤率提升至 20%..."
    conversation.messages.append({
        "role": "assistant",
        "content": ai_response
    })
    conversation.model_id = "gpt-4o"
    conversation.total_tokens = 1500
    conversation.total_cost_usd = 0.15
    
    print(f"✅ AI 回應完成 (tokens: {conversation.total_tokens}, cost: ${conversation.total_cost_usd})")
    
    # 6. 資料血緣追蹤
    tracker = get_lineage_tracker()
    
    # 追蹤轉換事件
    transform_event = TransformationEvent(
        input_objects=[conversation.object_id],
        output_objects=[conversation.object_id],
        transformation_type="chat_completion",
        model_used="gpt-4o",
        confidence_score=0.95,
        execution_time_ms=1200,
        tokens_used=1500,
        cost_usd=0.15
    )
    tracker.track_transformation(transform_event)
    
    print(f"✅ 記錄轉換事件: {transform_event.event_id}")
    
    # 7. 存取審計
    access_event = AccessEvent(
        user_id=user.user_id,
        user_roles=list(user.roles),
        organization_id=user.organization_id,
        resource_id=conversation.object_id,
        resource_type="conversation",
        resource_classification="INTERNAL",
        action="process",
        result="success",
        records_count=1,
        policy_decisions=[decision.to_dict()]
    )
    tracker.track_access(access_event)
    
    print(f"✅ 記錄存取審計: {access_event.event_id}")
    
    # 8. 生成審計報告
    audit_report = tracker.generate_audit_report(conversation.object_id)
    print(f"\n審計報告:")
    print(f"  總存取次數: {audit_report['total_accesses']}")
    print(f"  唯一使用者: {audit_report['unique_users']}")
    print(f"  最後更新: {audit_report['last_updated']}")
    
    print()


async def main():
    """執行所有示例"""
    await example_document_with_security()
    await example_policy_evaluation()
    await example_guardrails()
    await example_full_workflow()
    
    print("=" * 60)
    print("✅ 所有示例執行完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
