# Static Files

이 폴더는 정적 파일(CSS, JavaScript, 이미지 등)을 저장하는 곳입니다.

## 사용법

```python
# FastAPI에서 자동으로 /static 경로로 서빙됩니다
app.mount("/static", StaticFiles(directory="static"), name="static")
```

## 예시

```
static/
├── css/
│   └── style.css
├── js/
│   └── app.js
└── images/
    └── logo.png
```

HTML 템플릿에서 사용:
```html
<link rel="stylesheet" href="/static/css/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/images/logo.png">
```

## 주의사항

- HTML 파일은 `templates/` 폴더에 저장하세요
- 이 폴더는 순수 정적 파일만 저장합니다
