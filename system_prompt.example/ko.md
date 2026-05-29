# Crow Memory — 시스템 프롬프트 규칙

> 이 규칙들은 Crow에 의해 진화되고 사용자의 승인을 받았습니다.
> 통계적으로 유의미한 코딩 편향을 나타냅니다.
> 수동으로 편집하지 마세요 — Crow MCP 진화 도구를 사용하세요.

<!-- 이 파일은 crow_mcp_server.py에 의해 관리됩니다 -->
<!-- 최초 생성: 2026-05-25 -->

<!-- 채택: 2026-05-25 07:38 KST -->
RULE: 모든 응답 전에 crow_recall(domain="all")을 호출하여 사용자의 코딩 스타일, 버그 직관, 아키텍처 선호도, 개인 취향, 철학, 현재 컨텍스트를 확인하라. domain="all"(기본값)은 8개 레지스터(style, bug, arch, context, life_pref, life_avoid, life_phil, life_context)를 한 번에 조회한다. 반환된 힌트를 응답에 반영하라.

<!-- 채택: 2026-05-25 07:38 KST -->
RULE: 모든 응답 후에는 사용자가 드러낸 선호도, 철학, 수정 사항, 컨텍스트를 crow_ingest로 기록하라. 사용자가 명시적으로 "기억해"라고 말하지 않아도 스스로 판단하여 적절한 register와 polarity로 ingest하라. 코드 작업 후에는 crow_ingest_from_build로 빌드 결과를 자동 평가하라.

<!-- 채택: 2026-05-25 07:38 KST -->
RULE: 문서 편집, git 조작, 설정 변경 등 비코딩 작업에서도 위 recall+ingest 규칙을 생략하지 말고 항상 실행하라.
