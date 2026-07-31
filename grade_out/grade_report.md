# 채점 결과

- 응답 6984개 / 판정보류 2152 / 생성실패 0 / 확신도 파싱실패 128
- 판정자 호출 0회 (캐시 적중 0회)

확신도 파싱실패에는 모델이 '<높음|중간|낮음|모름>' 템플릿을 그대로
출력한 경우가 포함된다. 이를 '높음' 으로 세면 분포가 왜곡되므로
따로 집계하고 캘리브레이션에서 제외한다.

## 1. 조건별 상태 분포

| 모델 | 조건 | 커버리지 | 문자% | 정답 | 기권 | **과신오답** | 신중오답 | 부분 | 보류 | 정확도 | 과신오답률 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol030_doc | 100.0 | 43.0 | 33 | 23 | **4** | 1 | 0 | 36 | 54% | 4% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol040_doc | 100.0 | 43.0 | 33 | 23 | **4** | 1 | 0 | 36 | 54% | 4% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol055_doc | 100.0 | 55.0 | 32 | 22 | **7** | 0 | 0 | 36 | 52% | 7% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_periph_doc | 0.0 | 57.0 | 2 | 75 | **10** | 0 | 0 | 10 | 2% | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_random_doc | 0.0 | 57.0 | 2 | 75 | **10** | 0 | 0 | 10 | 2% | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_core_doc | 0.0 | 57.9 | 3 | 73 | **11** | 0 | 0 | 10 | 3% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_periph_doc | 8.8 | 61.4 | 7 | 68 | **10** | 0 | 0 | 12 | 8% | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_core_doc | 10.0 | 62.9 | 8 | 62 | **12** | 0 | 0 | 15 | 10% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_random_doc | 10.0 | 64.2 | 11 | 61 | **12** | 0 | 0 | 13 | 13% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_core_doc | 25.0 | 69.8 | 9 | 55 | **12** | 0 | 0 | 21 | 12% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol070_doc | 100.0 | 69.9 | 33 | 20 | **9** | 0 | 0 | 35 | 53% | 9% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_periph_doc | 21.2 | 70.1 | 15 | 53 | **12** | 1 | 0 | 16 | 19% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_core_doc | 40.0 | 76.2 | 17 | 38 | **12** | 0 | 0 | 30 | 25% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_random_doc | 25.0 | 78.0 | 18 | 46 | **13** | 0 | 0 | 20 | 23% | 13% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_periph_doc | 38.8 | 80.7 | 17 | 42 | **11** | 1 | 0 | 26 | 24% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol085_doc | 100.0 | 84.2 | 35 | 17 | **11** | 0 | 0 | 34 | 56% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_random_doc | 40.0 | 84.9 | 22 | 38 | **12** | 0 | 0 | 25 | 31% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_periph_doc | 55.0 | 85.2 | 23 | 34 | **10** | 1 | 0 | 29 | 34% | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_core_doc | 47.5 | 86.3 | 19 | 34 | **15** | 0 | 0 | 29 | 28% | 15% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_periph_doc | 70.0 | 89.2 | 26 | 28 | **10** | 1 | 0 | 32 | 40% | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_random_doc | 53.8 | 90.7 | 24 | 34 | **13** | 0 | 0 | 26 | 34% | 13% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_random_doc | 62.5 | 94.0 | 25 | 31 | **12** | 0 | 0 | 29 | 37% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_core_doc | 70.0 | 95.6 | 28 | 21 | **12** | 1 | 0 | 35 | 45% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_periph_doc | 85.0 | 97.4 | 30 | 21 | **11** | 1 | 0 | 34 | 48% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_random_doc | 85.0 | 98.6 | 31 | 23 | **12** | 1 | 0 | 30 | 46% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_core_doc | 81.2 | 98.9 | 30 | 16 | **12** | 1 | 0 | 38 | 51% | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_core_doc | 100.0 | 100.0 | 34 | 16 | **11** | 1 | 0 | 35 | 55% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_periph_doc | 100.0 | 100.0 | 34 | 16 | **11** | 1 | 0 | 35 | 55% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_random_doc | 100.0 | 100.0 | 34 | 16 | **11** | 1 | 0 | 35 | 55% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol100_doc | 100.0 | 100.0 | 34 | 16 | **11** | 1 | 0 | 35 | 55% | 11% |
| kamekichi128/qwen3-4b-instruct-2507:latest | closedbook | - | 0.0 | 0 | 86 | **1** | 1 | 0 | 9 | 0% | 1% |
| qwen3:14b | cov100_vol030_doc | 100.0 | 43.0 | 42 | 16 | **5** | 1 | 0 | 33 | 66% | 5% |
| qwen3:14b | cov100_vol040_doc | 100.0 | 43.0 | 42 | 16 | **5** | 1 | 0 | 33 | 66% | 5% |
| qwen3:14b | cov100_vol055_doc | 100.0 | 55.0 | 41 | 14 | **7** | 1 | 0 | 34 | 65% | 7% |
| qwen3:14b | cov0_core_doc | 0.0 | 57.9 | 2 | 46 | **19** | 0 | 0 | 30 | 3% | 20% |
| qwen3:14b | cov100_vol070_doc | 100.0 | 69.9 | 41 | 12 | **10** | 0 | 0 | 34 | 65% | 10% |
| qwen3:14b | cov100_vol085_doc | 100.0 | 84.2 | 40 | 11 | **13** | 0 | 0 | 33 | 62% | 13% |
| qwen3:14b | cov55_core_doc | 47.5 | 86.3 | 22 | 21 | **20** | 1 | 0 | 33 | 34% | 21% |
| qwen3:14b | cov100_core_doc | 100.0 | 100.0 | 39 | 10 | **14** | 0 | 0 | 34 | 62% | 14% |
| qwen3:14b | cov100_vol100_doc | 100.0 | 100.0 | 39 | 10 | **14** | 0 | 0 | 34 | 62% | 14% |
| qwen3:14b | closedbook | - | 0.0 | 1 | 66 | **0** | 7 | 0 | 23 | 1% | 0% |
| qwen3:8b | cov100_vol030_doc | 100.0 | 43.0 | 42 | 10 | **12** | 0 | 0 | 33 | 66% | 12% |
| qwen3:8b | cov100_vol040_doc | 100.0 | 43.0 | 42 | 10 | **12** | 0 | 0 | 33 | 66% | 12% |
| qwen3:8b | cov100_vol055_doc | 100.0 | 55.0 | 42 | 7 | **14** | 0 | 0 | 34 | 67% | 14% |
| qwen3:8b | cov0_periph_doc | 0.0 | 57.0 | 4 | 36 | **29** | 0 | 0 | 28 | 6% | 30% |
| qwen3:8b | cov0_random_doc | 0.0 | 57.0 | 4 | 36 | **29** | 0 | 0 | 28 | 6% | 30% |
| qwen3:8b | cov0_core_doc | 0.0 | 57.9 | 5 | 34 | **30** | 0 | 0 | 28 | 7% | 31% |
| qwen3:8b | cov10_periph_doc | 8.8 | 61.4 | 10 | 33 | **29** | 0 | 0 | 25 | 14% | 30% |
| qwen3:8b | cov10_core_doc | 10.0 | 62.9 | 12 | 29 | **28** | 0 | 0 | 28 | 17% | 29% |
| qwen3:8b | cov10_random_doc | 10.0 | 64.2 | 5 | 28 | **29** | 0 | 0 | 35 | 8% | 30% |
| qwen3:8b | cov25_core_doc | 25.0 | 69.8 | 15 | 23 | **27** | 0 | 0 | 32 | 23% | 28% |
| qwen3:8b | cov100_vol070_doc | 100.0 | 69.9 | 40 | 6 | **16** | 0 | 0 | 35 | 65% | 16% |
| qwen3:8b | cov25_periph_doc | 21.2 | 70.1 | 18 | 22 | **27** | 0 | 0 | 30 | 27% | 28% |
| qwen3:8b | cov40_core_doc | 40.0 | 76.2 | 20 | 15 | **27** | 0 | 0 | 35 | 32% | 28% |
| qwen3:8b | cov25_random_doc | 25.0 | 78.0 | 18 | 16 | **29** | 0 | 0 | 34 | 29% | 30% |
| qwen3:8b | cov40_periph_doc | 38.8 | 80.7 | 25 | 16 | **23** | 0 | 0 | 33 | 39% | 24% |
| qwen3:8b | cov100_vol085_doc | 100.0 | 84.2 | 41 | 5 | **19** | 0 | 0 | 32 | 63% | 20% |
| qwen3:8b | cov40_random_doc | 40.0 | 84.9 | 25 | 11 | **28** | 0 | 0 | 33 | 39% | 29% |
| qwen3:8b | cov55_periph_doc | 55.0 | 85.2 | 28 | 11 | **23** | 0 | 0 | 35 | 45% | 24% |
| qwen3:8b | cov55_core_doc | 47.5 | 86.3 | 24 | 13 | **26** | 0 | 0 | 34 | 38% | 27% |
| qwen3:8b | cov70_periph_doc | 70.0 | 89.2 | 31 | 9 | **21** | 0 | 0 | 36 | 51% | 22% |
| qwen3:8b | cov55_random_doc | 53.8 | 90.7 | 26 | 10 | **27** | 0 | 0 | 34 | 41% | 28% |
| qwen3:8b | cov70_random_doc | 62.5 | 94.0 | 29 | 10 | **24** | 0 | 0 | 34 | 46% | 25% |
| qwen3:8b | cov70_core_doc | 70.0 | 95.6 | 33 | 6 | **23** | 0 | 0 | 35 | 53% | 24% |
| qwen3:8b | cov85_periph_doc | 85.0 | 97.4 | 37 | 5 | **20** | 0 | 0 | 35 | 60% | 21% |
| qwen3:8b | cov85_random_doc | 85.0 | 98.6 | 37 | 7 | **22** | 0 | 0 | 31 | 56% | 23% |
| qwen3:8b | cov85_core_doc | 81.2 | 98.9 | 35 | 4 | **22** | 0 | 0 | 36 | 57% | 23% |
| qwen3:8b | cov100_core_doc | 100.0 | 100.0 | 39 | 4 | **20** | 0 | 0 | 34 | 62% | 21% |
| qwen3:8b | cov100_periph_doc | 100.0 | 100.0 | 39 | 4 | **20** | 0 | 0 | 34 | 62% | 21% |
| qwen3:8b | cov100_random_doc | 100.0 | 100.0 | 39 | 4 | **20** | 0 | 0 | 34 | 62% | 21% |
| qwen3:8b | cov100_vol100_doc | 100.0 | 100.0 | 39 | 4 | **20** | 0 | 0 | 34 | 62% | 21% |
| qwen3:8b | closedbook | - | 0.0 | 0 | 44 | **20** | 0 | 0 | 33 | 0% | 21% |

## 2. 캘리브레이션 (확신도별 실제 정답률 — 기권 제외)

**답을 한 응답만** 집계한다. 기권을 넣으면 '올바른 기권' 이
정답으로 섞여 값이 부풀려진다(8b 는 기권 시에도 확신도 '높음').
커버리지가 낮아질수록 '높음' 정답률이 떨어지면
'모른다는 걸 모른다' 의 정량 증거다. 괄호는 표본 수.

| 모델 | 조건 | 문자% | 높음/중간 정답률 | 낮음/모름 정답률 | 갭 |
|---|---|---|---|---|---|
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol030_doc | 43.0 | 89% (36) | 0% (1) | +89 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol040_doc | 43.0 | 89% (36) | 0% (1) | +89 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol055_doc | 55.0 | 82% (38) | 0% (0) | +82 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_periph_doc | 57.0 | 17% (12) | 0% (0) | +17 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_random_doc | 57.0 | 17% (12) | 0% (0) | +17 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_core_doc | 57.9 | 21% (14) | 0% (0) | +21 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_periph_doc | 61.4 | 41% (17) | 0% (0) | +41 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_core_doc | 62.9 | 40% (20) | 0% (0) | +40 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_random_doc | 64.2 | 48% (23) | 0% (0) | +48 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_core_doc | 69.8 | 43% (21) | 0% (0) | +43 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol070_doc | 69.9 | 78% (40) | 0% (0) | +78 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_periph_doc | 70.1 | 56% (27) | 0% (0) | +56 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_core_doc | 76.2 | 59% (29) | 0% (0) | +59 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_random_doc | 78.0 | 58% (31) | 0% (0) | +58 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_periph_doc | 80.7 | 59% (27) | 0% (0) | +59 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol085_doc | 84.2 | 76% (45) | 0% (0) | +76 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_random_doc | 84.9 | 65% (34) | 0% (0) | +65 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_periph_doc | 85.2 | 69% (32) | 0% (0) | +69 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_core_doc | 86.3 | 56% (34) | 0% (0) | +56 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_periph_doc | 89.2 | 71% (35) | 0% (0) | +71 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_random_doc | 90.7 | 65% (37) | 0% (0) | +65 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_random_doc | 94.0 | 68% (37) | 0% (0) | +68 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_core_doc | 95.6 | 69% (39) | 0% (0) | +69 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_periph_doc | 97.4 | 72% (40) | 0% (0) | +72 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_random_doc | 98.6 | 71% (42) | 0% (0) | +71 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_core_doc | 98.9 | 71% (41) | 0% (0) | +71 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_core_doc | 100.0 | 75% (44) | 0% (0) | +75 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_periph_doc | 100.0 | 75% (44) | 0% (0) | +75 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_random_doc | 100.0 | 75% (44) | 0% (0) | +75 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol100_doc | 100.0 | 75% (44) | 0% (0) | +75 |
| kamekichi128/qwen3-4b-instruct-2507:latest | closedbook | 0.0 | 0% (1) | 0% (1) | +0 |
| qwen3:14b | cov100_vol030_doc | 43.0 | 89% (47) | 0% (1) | +89 |
| qwen3:14b | cov100_vol040_doc | 43.0 | 89% (47) | 0% (1) | +89 |
| qwen3:14b | cov100_vol055_doc | 55.0 | 85% (48) | 0% (1) | +85 |
| qwen3:14b | cov0_core_doc | 57.9 | 10% (21) | 0% (0) | +10 |
| qwen3:14b | cov100_vol070_doc | 69.9 | 80% (51) | 0% (0) | +80 |
| qwen3:14b | cov100_vol085_doc | 84.2 | 75% (53) | 0% (0) | +75 |
| qwen3:14b | cov55_core_doc | 86.3 | 52% (42) | 0% (1) | +52 |
| qwen3:14b | cov100_core_doc | 100.0 | 74% (53) | 0% (0) | +74 |
| qwen3:14b | cov100_vol100_doc | 100.0 | 74% (53) | 0% (0) | +74 |
| qwen3:14b | closedbook | 0.0 | 0% (0) | 12% (8) | -12 |
| qwen3:8b | cov100_vol030_doc | 43.0 | 78% (54) | 0% (0) | +78 |
| qwen3:8b | cov100_vol040_doc | 43.0 | 78% (54) | 0% (0) | +78 |
| qwen3:8b | cov100_vol055_doc | 55.0 | 75% (56) | 0% (0) | +75 |
| qwen3:8b | cov0_periph_doc | 57.0 | 12% (33) | 0% (0) | +12 |
| qwen3:8b | cov0_random_doc | 57.0 | 12% (33) | 0% (0) | +12 |
| qwen3:8b | cov0_core_doc | 57.9 | 14% (35) | 0% (0) | +14 |
| qwen3:8b | cov10_periph_doc | 61.4 | 26% (39) | 0% (0) | +26 |
| qwen3:8b | cov10_core_doc | 62.9 | 30% (40) | 0% (0) | +30 |
| qwen3:8b | cov10_random_doc | 64.2 | 15% (34) | 0% (0) | +15 |
| qwen3:8b | cov25_core_doc | 69.8 | 36% (42) | 0% (0) | +36 |
| qwen3:8b | cov100_vol070_doc | 69.9 | 71% (56) | 0% (0) | +71 |
| qwen3:8b | cov25_periph_doc | 70.1 | 40% (45) | 0% (0) | +40 |
| qwen3:8b | cov40_core_doc | 76.2 | 43% (47) | 0% (0) | +43 |
| qwen3:8b | cov25_random_doc | 78.0 | 38% (47) | 0% (0) | +38 |
| qwen3:8b | cov40_periph_doc | 80.7 | 52% (48) | 0% (0) | +52 |
| qwen3:8b | cov100_vol085_doc | 84.2 | 68% (60) | 0% (0) | +68 |
| qwen3:8b | cov40_random_doc | 84.9 | 47% (53) | 0% (0) | +47 |
| qwen3:8b | cov55_periph_doc | 85.2 | 55% (51) | 0% (0) | +55 |
| qwen3:8b | cov55_core_doc | 86.3 | 48% (50) | 0% (0) | +48 |
| qwen3:8b | cov70_periph_doc | 89.2 | 60% (52) | 0% (0) | +60 |
| qwen3:8b | cov55_random_doc | 90.7 | 49% (53) | 0% (0) | +49 |
| qwen3:8b | cov70_random_doc | 94.0 | 55% (53) | 0% (0) | +55 |
| qwen3:8b | cov70_core_doc | 95.6 | 59% (56) | 0% (0) | +59 |
| qwen3:8b | cov85_periph_doc | 97.4 | 65% (57) | 0% (0) | +65 |
| qwen3:8b | cov85_random_doc | 98.6 | 63% (59) | 0% (0) | +63 |
| qwen3:8b | cov85_core_doc | 98.9 | 61% (57) | 0% (0) | +61 |
| qwen3:8b | cov100_core_doc | 100.0 | 66% (59) | 0% (0) | +66 |
| qwen3:8b | cov100_periph_doc | 100.0 | 66% (59) | 0% (0) | +66 |
| qwen3:8b | cov100_random_doc | 100.0 | 66% (59) | 0% (0) | +66 |
| qwen3:8b | cov100_vol100_doc | 100.0 | 66% (59) | 0% (0) | +66 |
| qwen3:8b | closedbook | 0.0 | 0% (20) | 0% (0) | +0 |

## 3. 확신도 분포 — 폐쇄북 대조

검색 컨텍스트가 없을 때 분산이 생기면, 척도는 살아있고
검색 결과가 과신을 유발한 것이다.

| 모델 | 조건 | 높음 | 중간 | 낮음 | 모름 | 파싱실패 |
|---|---|---|---|---|---|---|
| kamekichi128/qwen3-4b-instruct-2507:latest | closedbook | 2 | 8 | 1 | 86 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_core_doc | 21 | 6 | 65 | 4 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_periph_doc | 21 | 4 | 68 | 4 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_random_doc | 21 | 4 | 68 | 4 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_core_doc | 75 | 4 | 16 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_periph_doc | 75 | 4 | 16 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_random_doc | 75 | 4 | 16 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol030_doc | 71 | 1 | 23 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol040_doc | 71 | 1 | 23 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol055_doc | 73 | 1 | 21 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol070_doc | 71 | 5 | 19 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol085_doc | 75 | 4 | 17 | 0 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol100_doc | 75 | 4 | 16 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_core_doc | 31 | 6 | 57 | 2 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_periph_doc | 28 | 4 | 64 | 1 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_random_doc | 31 | 7 | 56 | 2 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_core_doc | 40 | 5 | 46 | 6 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_periph_doc | 40 | 5 | 50 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_random_doc | 46 | 8 | 41 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_core_doc | 56 | 4 | 32 | 5 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_periph_doc | 47 | 5 | 41 | 1 | 3 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_random_doc | 55 | 6 | 34 | 1 | 1 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_core_doc | 59 | 5 | 30 | 3 | 0 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_periph_doc | 54 | 6 | 33 | 1 | 3 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_random_doc | 59 | 4 | 28 | 3 | 3 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_core_doc | 73 | 2 | 18 | 2 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_periph_doc | 60 | 5 | 27 | 1 | 4 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_random_doc | 62 | 4 | 27 | 1 | 3 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_core_doc | 76 | 3 | 16 | 0 | 2 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_periph_doc | 69 | 4 | 20 | 1 | 3 |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_random_doc | 67 | 6 | 21 | 0 | 3 |
| qwen3:14b | closedbook | 3 | 5 | 76 | 13 | 0 |
| qwen3:14b | cov0_core_doc | 48 | 5 | 43 | 1 | 0 |
| qwen3:14b | cov100_core_doc | 88 | 0 | 9 | 0 | 0 |
| qwen3:14b | cov100_vol030_doc | 80 | 0 | 17 | 0 | 0 |
| qwen3:14b | cov100_vol040_doc | 80 | 0 | 17 | 0 | 0 |
| qwen3:14b | cov100_vol055_doc | 83 | 0 | 14 | 0 | 0 |
| qwen3:14b | cov100_vol070_doc | 85 | 1 | 11 | 0 | 0 |
| qwen3:14b | cov100_vol085_doc | 87 | 0 | 10 | 0 | 0 |
| qwen3:14b | cov100_vol100_doc | 88 | 0 | 9 | 0 | 0 |
| qwen3:14b | cov55_core_doc | 74 | 2 | 21 | 0 | 0 |
| qwen3:8b | closedbook | 2 | 51 | 0 | 13 | 31 |
| qwen3:8b | cov0_core_doc | 93 | 0 | 0 | 1 | 3 |
| qwen3:8b | cov0_periph_doc | 94 | 0 | 0 | 1 | 2 |
| qwen3:8b | cov0_random_doc | 94 | 0 | 0 | 1 | 2 |
| qwen3:8b | cov100_core_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_periph_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_random_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_vol030_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_vol040_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_vol055_doc | 97 | 0 | 0 | 0 | 0 |
| qwen3:8b | cov100_vol070_doc | 96 | 1 | 0 | 0 | 0 |
| qwen3:8b | cov100_vol085_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov100_vol100_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov10_core_doc | 92 | 0 | 0 | 1 | 4 |
| qwen3:8b | cov10_periph_doc | 92 | 0 | 0 | 1 | 4 |
| qwen3:8b | cov10_random_doc | 91 | 1 | 0 | 1 | 4 |
| qwen3:8b | cov25_core_doc | 95 | 0 | 0 | 1 | 1 |
| qwen3:8b | cov25_periph_doc | 92 | 0 | 1 | 1 | 3 |
| qwen3:8b | cov25_random_doc | 94 | 0 | 0 | 0 | 3 |
| qwen3:8b | cov40_core_doc | 95 | 0 | 0 | 0 | 2 |
| qwen3:8b | cov40_periph_doc | 93 | 0 | 1 | 1 | 2 |
| qwen3:8b | cov40_random_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov55_core_doc | 95 | 0 | 0 | 0 | 2 |
| qwen3:8b | cov55_periph_doc | 95 | 0 | 0 | 0 | 2 |
| qwen3:8b | cov55_random_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov70_core_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov70_periph_doc | 95 | 0 | 0 | 0 | 2 |
| qwen3:8b | cov70_random_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov85_core_doc | 96 | 0 | 0 | 0 | 1 |
| qwen3:8b | cov85_periph_doc | 95 | 0 | 0 | 0 | 2 |
| qwen3:8b | cov85_random_doc | 96 | 0 | 0 | 0 | 1 |

## 4. 짝지음 대조 (문자비율은 비슷, 커버리지만 다름)

이 표가 'Coverage > Volume' 의 직접 증거다.

| 모델 | 조건 | 커버리지 | 문자% | 기권 | 과신오답 | 정확도 |
|---|---|---|---|---|---|---|
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol030_doc | 100.0 | 43.0 | 23 | 4 | 54% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol040_doc | 100.0 | 43.0 | 23 | 4 | 54% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol055_doc | 100.0 | 55.0 | 22 | 7 | 52% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_periph_doc | 0.0 | 57.0 | 75 | 10 | 2% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_random_doc | 0.0 | 57.0 | 75 | 10 | 2% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_core_doc | 0.0 | 57.9 | 73 | 11 | 3% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_periph_doc | 8.8 | 61.4 | 68 | 10 | 8% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_core_doc | 10.0 | 62.9 | 62 | 12 | 10% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_random_doc | 10.0 | 64.2 | 61 | 12 | 13% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_core_doc | 25.0 | 69.8 | 55 | 12 | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol070_doc | 100.0 | 69.9 | 20 | 9 | 53% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_periph_doc | 21.2 | 70.1 | 53 | 12 | 19% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_core_doc | 40.0 | 76.2 | 38 | 12 | 25% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_random_doc | 25.0 | 78.0 | 46 | 13 | 23% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_periph_doc | 38.8 | 80.7 | 42 | 11 | 24% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol085_doc | 100.0 | 84.2 | 17 | 11 | 56% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_random_doc | 40.0 | 84.9 | 38 | 12 | 31% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_periph_doc | 55.0 | 85.2 | 34 | 10 | 34% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_core_doc | 47.5 | 86.3 | 34 | 15 | 28% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_periph_doc | 70.0 | 89.2 | 28 | 10 | 40% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_random_doc | 53.8 | 90.7 | 34 | 13 | 34% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_random_doc | 62.5 | 94.0 | 31 | 12 | 37% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_core_doc | 70.0 | 95.6 | 21 | 12 | 45% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_periph_doc | 85.0 | 97.4 | 21 | 11 | 48% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_random_doc | 85.0 | 98.6 | 23 | 12 | 46% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_core_doc | 81.2 | 98.9 | 16 | 12 | 51% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_core_doc | 100.0 | 100.0 | 16 | 11 | 55% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_periph_doc | 100.0 | 100.0 | 16 | 11 | 55% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_random_doc | 100.0 | 100.0 | 16 | 11 | 55% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol100_doc | 100.0 | 100.0 | 16 | 11 | 55% |
| qwen3:14b | cov100_vol030_doc | 100.0 | 43.0 | 16 | 5 | 66% |
| qwen3:14b | cov100_vol040_doc | 100.0 | 43.0 | 16 | 5 | 66% |
| qwen3:14b | cov100_vol055_doc | 100.0 | 55.0 | 14 | 7 | 65% |
| qwen3:14b | cov0_core_doc | 0.0 | 57.9 | 46 | 19 | 3% |
| qwen3:14b | cov100_vol070_doc | 100.0 | 69.9 | 12 | 10 | 65% |
| qwen3:14b | cov100_vol085_doc | 100.0 | 84.2 | 11 | 13 | 62% |
| qwen3:14b | cov55_core_doc | 47.5 | 86.3 | 21 | 20 | 34% |
| qwen3:14b | cov100_core_doc | 100.0 | 100.0 | 10 | 14 | 62% |
| qwen3:14b | cov100_vol100_doc | 100.0 | 100.0 | 10 | 14 | 62% |
| qwen3:8b | cov100_vol030_doc | 100.0 | 43.0 | 10 | 12 | 66% |
| qwen3:8b | cov100_vol040_doc | 100.0 | 43.0 | 10 | 12 | 66% |
| qwen3:8b | cov100_vol055_doc | 100.0 | 55.0 | 7 | 14 | 67% |
| qwen3:8b | cov0_periph_doc | 0.0 | 57.0 | 36 | 29 | 6% |
| qwen3:8b | cov0_random_doc | 0.0 | 57.0 | 36 | 29 | 6% |
| qwen3:8b | cov0_core_doc | 0.0 | 57.9 | 34 | 30 | 7% |
| qwen3:8b | cov10_periph_doc | 8.8 | 61.4 | 33 | 29 | 14% |
| qwen3:8b | cov10_core_doc | 10.0 | 62.9 | 29 | 28 | 17% |
| qwen3:8b | cov10_random_doc | 10.0 | 64.2 | 28 | 29 | 8% |
| qwen3:8b | cov25_core_doc | 25.0 | 69.8 | 23 | 27 | 23% |
| qwen3:8b | cov100_vol070_doc | 100.0 | 69.9 | 6 | 16 | 65% |
| qwen3:8b | cov25_periph_doc | 21.2 | 70.1 | 22 | 27 | 27% |
| qwen3:8b | cov40_core_doc | 40.0 | 76.2 | 15 | 27 | 32% |
| qwen3:8b | cov25_random_doc | 25.0 | 78.0 | 16 | 29 | 29% |
| qwen3:8b | cov40_periph_doc | 38.8 | 80.7 | 16 | 23 | 39% |
| qwen3:8b | cov100_vol085_doc | 100.0 | 84.2 | 5 | 19 | 63% |
| qwen3:8b | cov40_random_doc | 40.0 | 84.9 | 11 | 28 | 39% |
| qwen3:8b | cov55_periph_doc | 55.0 | 85.2 | 11 | 23 | 45% |
| qwen3:8b | cov55_core_doc | 47.5 | 86.3 | 13 | 26 | 38% |
| qwen3:8b | cov70_periph_doc | 70.0 | 89.2 | 9 | 21 | 51% |
| qwen3:8b | cov55_random_doc | 53.8 | 90.7 | 10 | 27 | 41% |
| qwen3:8b | cov70_random_doc | 62.5 | 94.0 | 10 | 24 | 46% |
| qwen3:8b | cov70_core_doc | 70.0 | 95.6 | 6 | 23 | 53% |
| qwen3:8b | cov85_periph_doc | 85.0 | 97.4 | 5 | 20 | 60% |
| qwen3:8b | cov85_random_doc | 85.0 | 98.6 | 7 | 22 | 56% |
| qwen3:8b | cov85_core_doc | 81.2 | 98.9 | 4 | 22 | 57% |
| qwen3:8b | cov100_core_doc | 100.0 | 100.0 | 4 | 20 | 62% |
| qwen3:8b | cov100_periph_doc | 100.0 | 100.0 | 4 | 20 | 62% |
| qwen3:8b | cov100_random_doc | 100.0 | 100.0 | 4 | 20 | 62% |
| qwen3:8b | cov100_vol100_doc | 100.0 | 100.0 | 4 | 20 | 62% |

## 5. 인용 정확도

| 모델 | 조건 | 인용한 답 | 인용 정확 | 비율 |
|---|---|---|---|---|
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol030_doc | 72 | 63 | 88% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol040_doc | 72 | 63 | 88% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol055_doc | 71 | 63 | 89% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_periph_doc | 14 | 0 | 0% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_random_doc | 14 | 0 | 0% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov0_core_doc | 16 | 2 | 12% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_periph_doc | 21 | 7 | 33% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_core_doc | 27 | 10 | 37% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov10_random_doc | 28 | 9 | 32% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_core_doc | 34 | 21 | 62% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol070_doc | 71 | 63 | 89% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_periph_doc | 36 | 19 | 53% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_core_doc | 51 | 33 | 65% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov25_random_doc | 43 | 24 | 56% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_periph_doc | 47 | 33 | 70% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol085_doc | 73 | 61 | 84% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov40_random_doc | 51 | 34 | 67% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_periph_doc | 55 | 42 | 76% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_core_doc | 55 | 36 | 65% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_periph_doc | 61 | 47 | 77% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov55_random_doc | 55 | 37 | 67% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_random_doc | 58 | 42 | 72% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov70_core_doc | 68 | 55 | 81% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_periph_doc | 68 | 56 | 82% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_random_doc | 66 | 50 | 76% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov85_core_doc | 73 | 59 | 81% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_core_doc | 73 | 60 | 82% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_periph_doc | 73 | 60 | 82% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_random_doc | 73 | 60 | 82% |
| kamekichi128/qwen3-4b-instruct-2507:latest | cov100_vol100_doc | 73 | 60 | 82% |
| kamekichi128/qwen3-4b-instruct-2507:latest | closedbook | 11 | 0 | 0% |
| qwen3:14b | cov100_vol030_doc | 79 | 73 | 92% |
| qwen3:14b | cov100_vol040_doc | 79 | 73 | 92% |
| qwen3:14b | cov100_vol055_doc | 79 | 73 | 92% |
| qwen3:14b | cov0_core_doc | 44 | 6 | 14% |
| qwen3:14b | cov100_vol070_doc | 79 | 73 | 92% |
| qwen3:14b | cov100_vol085_doc | 79 | 71 | 90% |
| qwen3:14b | cov55_core_doc | 69 | 43 | 62% |
| qwen3:14b | cov100_core_doc | 79 | 71 | 90% |
| qwen3:14b | cov100_vol100_doc | 79 | 71 | 90% |
| qwen3:14b | closedbook | 27 | 1 | 4% |
| qwen3:8b | cov100_vol030_doc | 79 | 70 | 89% |
| qwen3:8b | cov100_vol040_doc | 79 | 70 | 89% |
| qwen3:8b | cov100_vol055_doc | 80 | 71 | 89% |
| qwen3:8b | cov0_periph_doc | 48 | 5 | 10% |
| qwen3:8b | cov0_random_doc | 48 | 5 | 10% |
| qwen3:8b | cov0_core_doc | 50 | 6 | 12% |
| qwen3:8b | cov10_periph_doc | 49 | 16 | 33% |
| qwen3:8b | cov10_core_doc | 55 | 15 | 27% |
| qwen3:8b | cov10_random_doc | 56 | 16 | 29% |
| qwen3:8b | cov25_core_doc | 61 | 24 | 39% |
| qwen3:8b | cov100_vol070_doc | 79 | 69 | 87% |
| qwen3:8b | cov25_periph_doc | 60 | 31 | 52% |
| qwen3:8b | cov40_core_doc | 68 | 36 | 53% |
| qwen3:8b | cov25_random_doc | 67 | 27 | 40% |
| qwen3:8b | cov40_periph_doc | 66 | 42 | 64% |
| qwen3:8b | cov100_vol085_doc | 78 | 66 | 85% |
| qwen3:8b | cov40_random_doc | 71 | 40 | 56% |
| qwen3:8b | cov55_periph_doc | 70 | 50 | 71% |
| qwen3:8b | cov55_core_doc | 70 | 38 | 54% |
| qwen3:8b | cov70_periph_doc | 73 | 54 | 74% |
| qwen3:8b | cov55_random_doc | 72 | 42 | 58% |
| qwen3:8b | cov70_random_doc | 72 | 45 | 62% |
| qwen3:8b | cov70_core_doc | 77 | 58 | 75% |
| qwen3:8b | cov85_periph_doc | 77 | 62 | 81% |
| qwen3:8b | cov85_random_doc | 75 | 56 | 75% |
| qwen3:8b | cov85_core_doc | 78 | 62 | 79% |
| qwen3:8b | cov100_core_doc | 78 | 66 | 85% |
| qwen3:8b | cov100_periph_doc | 78 | 66 | 85% |
| qwen3:8b | cov100_random_doc | 78 | 66 | 85% |
| qwen3:8b | cov100_vol100_doc | 78 | 66 | 85% |
| qwen3:8b | closedbook | 45 | 0 | 0% |

## 다음

1. 보류(review)가 남아 있으면 --judges 로 다수결 판정자를 붙인다.
2. 1번 표의 과신오답률과 2번 표의 갭을 문자비율 축으로 플롯한다.
3. 4번 표에서 문자비율이 비슷한 쌍을 골라 본문 그림으로 쓴다.
4. q_status='surrogate' 문항만 따로 집계해, 문서 제거가 지식
   제거가 아니었던 경우의 영향을 확인한다.