# 오쏘몰 SOV 대시보드

실제 미디어 집행 없이 진행되는 학습 프로젝트를 위한 대시보드입니다. 채널별 유입·전환은
측정 불가능하므로, 네이버 데이터랩 검색어트렌드 API로 실측 가능한 대체 지표(SOV·비교의도
검색지수)를 수집·시각화해 "오쏘몰이 40대의 고려상표군(Evoked Set)에 들어가고 있는가"라는
가설을 검증합니다.

## 배포된 앱

배포 후 업데이트 예정

## 로컬 실행 방법

```bash
pip install -r requirements.txt
```

프로젝트 루트에 `.env` 파일을 만들고 네이버 오픈API(데이터랩) 인증키를 설정합니다.

```
NAVER_CLIENT_ID=발급받은_클라이언트_ID
NAVER_CLIENT_SECRET=발급받은_클라이언트_시크릿
```

최초 1회 데이터를 수집합니다 (네이버 데이터랩 API를 실제로 호출해 `cache/sov_history.json`에 저장).

```bash
python fetch_sov.py
```

대시보드를 실행합니다.

```bash
streamlit run app.py
```

## 배포 시 참고

Streamlit Community Cloud에 배포할 때는 `.env` 대신 앱 설정의 **Secrets**에 아래 값을 등록합니다
(`fetch_sov.py`가 `st.secrets`도 자동으로 읽습니다).

```toml
NAVER_CLIENT_ID = "발급받은_클라이언트_ID"
NAVER_CLIENT_SECRET = "발급받은_클라이언트_시크릿"
```

`cache/sov_history.json`은 지금까지 수집된 실측 데이터를 담아 레포에 함께 커밋되어 있습니다.
배포 직후에도 빈 화면이 아니라 기존 데이터가 바로 보이며, 화면의 "새로고침" 버튼으로 최신
주차 데이터를 다시 수집할 수 있습니다.
