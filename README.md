# channel-monitor — 상승채널 돌파 모니터 (NASDAQ / KOSPI)

일봉 기준으로 **상승채널(ascending channel)을 상단 돌파**하는 종목을 자동으로 찾아내는 스크리너입니다.
10x Genomics(TXG)의 2025년 12월 ~ 2026년 6월 구간처럼, 약 6개월간 평행한 상승 추세대 안에서
저항선을 3~4회 터치하며 올라가다가 상단선을 종가로 돌파하는 형태를 기본 탐지 대상으로 잡았습니다.

```
     상단 저항선 (pivot high 2점 앵커)            ← 돌파
   ────────────────────────────────────┐   ●
        ╱╲        ╱╲        ╱╲        ╱ ╲ ╱
       ╱  ╲      ╱  ╲      ╱  ╲      ╱   ●
   ───╱────╲────╱────╲────╱────╲────╱
     하단 지지선 (pivot low 2점 앵커)
```

## 설치

```bash
pip install -r requirements.txt          # 필수: numpy, pandas, requests, yfinance
pip install matplotlib pykrx             # 선택: 차트 이미지 / KOSPI 전체 종목 리스트
```

## 빠른 시작

```bash
# 0) 네트워크 없이 탐지 로직만 검증 (합성 데이터)
python -m channel_monitor selftest

# 1) 나스닥 + 코스피 전체 스캔 → 표 출력 + CSV + 차트 저장
python -m channel_monitor scan --markets nasdaq,kospi --csv out/hits.csv --plot-dir charts

# 2) 한 종목의 판정 근거 보기 (왜 걸렸는지 / 왜 안 걸렸는지)
python -m channel_monitor explain TXG --market nasdaq --plot charts/TXG.png
python -m channel_monitor explain 005930 --market kospi

# 3) 모니터링 모드: 60분마다 재스캔, 새로 발생한 돌파만 알림
python -m channel_monitor watch --interval 60 --webhook "$SLACK_WEBHOOK_URL"

# 4) 유니버스 확인
python -m channel_monitor universe kospi | head
```

`pip install -e .` 로 설치하면 `channel-monitor scan ...` 형태로도 실행됩니다.

출력 예시:

```
MARKET  CODE      SCORE STATUS    BREAK        AGE   EXC%  VOL x   EXT%  WIDTH%  SLOPE%   PAR   CONT  TU  TL   LB
nasdaq  TXG       77.60 breakout  2026-06-03     2   1.31   2.87   4.61   11.10    0.11  0.88   1.00   5   5  150
```

| 컬럼 | 의미 |
|---|---|
| `SCORE` | 0~100 종합 점수 (채널 품질 50 + 돌파 강도 50) |
| `STATUS` | `breakout`(상단선 위) / `retest`(돌파 후 상단선 재접근) |
| `BREAK` / `AGE` | 돌파 발생 일자 / 며칠 지났는지 |
| `EXC%` | 돌파 당일 종가가 저항선을 넘은 폭 |
| `VOL x` | 돌파 당일 거래량 / 직전 20일 평균 |
| `EXT%` | 현재 종가의 저항선 대비 위치 (과열 여부) |
| `WIDTH%` | 채널 폭 (중앙선 대비 %) |
| `SLOPE%` | 저항선 기울기 (일 %) |
| `PAR` | 상·하단 기울기 평행도 (1.0 = 완전 평행) |
| `CONT` | 돌파 이전 구간에서 종가가 채널 안에 있던 비율 |
| `TU` / `TL` | 저항선 / 지지선 터치 횟수 |
| `LB` | 패턴이 인식된 룩백 길이(일) |

## 탐지 알고리즘

`channel_monitor/channel.py` 의 `detect()` 가 (룩백 × 피벗 윈도) 격자를 모두 시도하고
가장 점수가 높은 결과를 돌려줍니다. 기본 룩백은 90 / 120 / 150일입니다.

1. **피벗 추출** (`pivots.py`)
   프랙탈 방식으로 좌우 `pivot_window`(기본 3)일보다 높은 고점 / 낮은 저점을 찾습니다.
   윈도 양 끝은 프랙탈이 성립하지 않으므로 구간 최고·최저점을 앵커 후보로 추가합니다.

2. **추세선 적합** (`trendline.py`)
   피벗 2점을 잇는 모든 후보 직선 중,
   - 두 앵커 사이 구간에서 **모든 고가가 선 위로 `violation_tolerance`(2%) 이상 벗어나지 않고**
   - 터치(선과의 거리 ≤ `touch_tolerance`, 1.5%) 수가 `min_pivots_per_line` 이상이며
   - 구간 길이 ≥ `min_line_span`(30일), 마지막 앵커가 최근 `max_anchor_gap`(35일) 안에 있는

   직선을 `2·터치수 + 1.5·구간비율 − 2·평균이격` 점수로 골라냅니다.
   선은 앵커 구간 안에서만 검증되고, 돌파 판정에는 그 선을 앞으로 연장해서 씁니다.

3. **채널 검증** (`channel.py`)
   - 상·하단 기울기가 **둘 다 양수**이고 `min_slope_pct`(0.05%/일) ~ `max_slope_pct`(2%/일)
   - 평행도 `min(기울기)/max(기울기) ≥ parallel_tolerance`(0.40)
   - 채널 폭이 3~80%이고, 시작 대비 종료 폭 비율이 0.40~2.50 (수렴/발산 삼각형 배제)
   - 두 선이 교차하지 않음
   - 돌파 직전 구간 종가의 `min_containment`(80%) 이상이 채널 내부

4. **돌파 판정**
   - 최근 `breakout_window`(기본 5)일 중 **가장 이른** 바에서
     `종가 > 저항선 × (1 + max(min_break_pct, break_atr_mult × ATR / 저항선))`
     → 기본값은 0.5% 또는 0.25 ATR 중 큰 값
   - 직전 `fresh_window`(20)일 안에 이미 돌파가 있었으면 `stale_breakout`으로 제외 (신규 신호만)
   - 현재 종가가 저항선보다 `max_extension`(20%) 이상 위면 `overextended`로 제외 (추격 방지)
   - 되돌림은 `pullback_tolerance`(1%)까지 `retest` 상태로 허용, 그 아래로 빠지면 제외
   - `--require-volume` 을 주면 돌파 당일 거래량이 20일 평균의 `min_volume_ratio` 배 미만이면 제외

5. **점수** (0~100)
   채널 품질 50점 = 저항선 터치 15 + 지지선 터치 10 + 채널 내 수용도 10 + 평행도 10 + 추세 R² 5
   돌파 강도 50점 = 돌파 폭 20 + 거래량 배수 15 + 신선도 5 + 잔여 여력 10
   `--min-score`(기본 55) 미만은 걸러냅니다.

모든 판정은 **해당 일봉 종가까지의 정보만** 사용하며, 미래 데이터를 참조하지 않습니다.

## 데이터 소스

| 시장 | 시세 | 종목 리스트 |
|---|---|---|
| NASDAQ | yfinance (`TXG`) | nasdaqtrader.com 상장 파일 (테스트·ETF·워런트 제외), 실패 시 내장 폴백 105종목 |
| KOSPI | yfinance (`005930.KS`) | `pykrx` 전체 리스트, 미설치 시 내장 대형주 폴백 |
| KOSDAQ | yfinance (`005930.KQ`) | `pykrx` |

- 시세는 `--cache-dir`(기본 `.cache/prices`)에 CSV로 캐시되고 `--cache-ttl`(기본 12시간) 동안 재사용됩니다.
- `--csv-dir DIR` 를 주면 네트워크 없이 로컬 CSV(`<티커>.csv`, 컬럼 `Open,High,Low,Close,Volume`)로 스캔합니다.
- `--symbols TXG,NVDA` 또는 `--universe-file list.txt` 로 유니버스를 직접 지정할 수 있습니다.
- 유동성 필터는 시장별 기본값이 다릅니다(KRW/USD). `--min-price`, `--min-avg-volume`, `--min-avg-turnover` 로 덮어쓰세요.

## 파라미터 튜닝

기본값은 "6개월 채널 + 최근 5일 내 돌파"에 맞춰져 있습니다. 신호가 너무 적거나 많으면:

```bash
# 더 느슨하게 (신호 증가)
python -m channel_monitor scan --min-score 45 --parallel-tolerance 0.3 --min-containment 0.72 \
    --lookbacks 60,90,120,180

# 더 엄격하게 (거래량 동반 + 강한 돌파만)
python -m channel_monitor scan --require-volume --min-volume-ratio 1.8 --min-break-pct 0.01 \
    --min-score 70 --breakout-window 2
```

`explain` 명령의 `reason` 값이 어떤 조건에서 탈락했는지 알려주므로 튜닝 기준으로 쓰면 됩니다
(`no_pivots`, `slope_not_rising`, `not_parallel`, `width_unstable`, `low_containment`,
`no_breakout`, `stale_breakout`, `overextended`, `fell_back_inside`, `weak_volume`, `low_score`).

## 테스트

```bash
python -m pytest -q          # 62 tests: 피벗/추세선/채널/데이터/스크리너/CLI
python -m channel_monitor selftest --plot-dir charts   # 합성 패턴 5종 판정 + 차트
python examples/pattern_demo.py --out-dir charts       # 돌파/유지/되돌림/저거래량 비교
```

`channel_monitor/synthetic.py` 가 만드는 가격 경로는 **검증용 합성 데이터**이며 실제 시세가 아닙니다.

## 한계

- 일봉 종가 기준이므로 장중 돌파는 다음 종가까지 확정되지 않습니다.
- 직선 추세대만 다룹니다(로그 스케일·곡선 채널 미지원).
- 액면분할·배당은 yfinance 수정주가(`auto_adjust=True`)에 의존합니다.
- 상장 후 `min_history`(기본 150거래일) 미만 종목은 건너뜁니다.
- 패턴 탐지 결과이며 투자 판단·수익을 보장하지 않습니다.
