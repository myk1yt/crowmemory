# Crow Memory — System Prompt Rules

> These rules were evolved by Crow and approved by the user.
> They represent statistically significant coding biases.
> Do not edit manually — use the Crow MCP evolve tools.

<!-- This file is managed by crow_mcp_server.py -->
<!-- Last initialized: 2026-05-25 -->

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: 모든 응답 전에 crow_recall(domain="all")을 호출하여 사용자의 코딩 스타일, 버그 직관, 아키텍처 선호도, 개인 취향, 철학, 현재 컨텍스트를 확인하라. domain="all"(기본값)은 8개 레지스터(style, bug, arch, context, life_pref, life_avoid, life_phil, life_context)를 한 번에 조회한다. 반환된 힌트를 응답에 반영하라.

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: 모든 응답 후에는 사용자가 드러낸 선호도, 철학, 수정 사항, 컨텍스트를 crow_ingest로 기록하라. 사용자가 명시적으로 "기억해"라고 말하지 않아도 스스로 판단하여 적절한 register와 polarity로 ingest하라. 코드 작업 후에는 crow_ingest_from_build로 빌드 결과를 자동 평가하라.

<!-- adopted: 2026-05-25 07:38 KST -->
RULE: 문서 편집, git 조작, 설정 변경 등 비코딩 작업에서도 위 recall+ingest 규칙을 생략하지 말고 항상 실행하라.
