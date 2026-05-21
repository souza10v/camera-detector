# Camera Detector — MVP

Sistema de leitura automática de placas de veículos com anonimização de rostos.

## Funcionalidades

- Upload de imagens (JPG, PNG, WebP) e vídeos (MP4, AVI, MOV)
- Detecção de placas via OpenCV + OCR com EasyOCR
- Anonimização automática de rostos com Gaussian Blur (Haar Cascade)
- Imagens originais **nunca** são armazenadas — apenas a versão anonimizada
- API REST com FastAPI
- Frontend Angular com tabela de leituras, busca por placa e visualização de imagem
- Banco de dados PostgreSQL

---

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/)

---

## Rodando com Docker Compose

```bash
# Clone o projeto
git clone <url-do-repo>
cd camera-detector

# Suba todos os serviços
docker compose up --build
```

| Serviço   | URL                        |
|-----------|----------------------------|
| Frontend  | http://localhost:4200      |
| API       | http://localhost:8000      |
| Docs API  | http://localhost:8000/docs |

---

## Rodando localmente (sem Docker)

### Backend

```bash
cd backend

# Crie o virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt

# Configure variáveis de ambiente
cp .env.example .env
# Edite .env com sua DATABASE_URL local

# Suba o banco PostgreSQL (ou ajuste DATABASE_URL para o seu)
# docker run -d -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=camera_detector -p 5432:5432 postgres:16-alpine

# Inicie a API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start   # http://localhost:4200
```

---

## Estrutura do Projeto

```
camera-detector/
├── backend/
│   ├── app/
│   │   ├── main.py              # Entry point FastAPI
│   │   ├── config.py            # Settings via variáveis de ambiente
│   │   ├── database/
│   │   │   └── connection.py    # Engine SQLAlchemy async
│   │   ├── models/
│   │   │   └── reading.py       # Modelo PlateReading (ORM)
│   │   ├── schemas/
│   │   │   └── reading.py       # Pydantic schemas
│   │   ├── routes/
│   │   │   ├── upload.py        # POST /api/v1/upload/
│   │   │   └── readings.py      # GET /api/v1/readings/
│   │   ├── services/
│   │   │   ├── face_anonymizer.py   # Detecção e blur de rostos
│   │   │   ├── plate_detector.py    # OCR de placas
│   │   │   ├── image_processor.py   # Orquestrador imagem/vídeo
│   │   │   └── reading_service.py   # CRUD no banco
│   │   └── utils/
│   │       └── file_utils.py    # Validação e salvamento de arquivos
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   │   ├── components/
│   │   │   ├── upload/          # Componente de upload
│   │   │   └── readings/        # Tabela de leituras
│   │   ├── models/              # Interfaces TypeScript
│   │   └── services/            # ApiService (HTTP)
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Endpoints da API

### `POST /api/v1/upload/`
Envia imagem ou vídeo para processamento.

```bash
curl -X POST http://localhost:8000/api/v1/upload/ \
  -F "file=@/caminho/para/imagem.jpg"
```

Resposta:
```json
{
  "reading_id": 1,
  "plate_text": "ABC1234",
  "confidence": 0.94,
  "faces_detected": 2,
  "plates_detected": 1,
  "processed_image_url": "/images/abc123_processed.jpg",
  "status": "completed",
  "message": "Processamento concluído com sucesso."
}
```

---

### `GET /api/v1/readings/`
Lista todas as leituras paginadas.

```bash
curl "http://localhost:8000/api/v1/readings/?skip=0&limit=20"
```

---

### `GET /api/v1/readings/search?plate=ABC`
Busca leituras por texto de placa (parcial ou completo).

```bash
curl "http://localhost:8000/api/v1/readings/search?plate=ABC1234"
```

---

### `GET /api/v1/readings/{id}`
Busca uma leitura específica por ID.

```bash
curl http://localhost:8000/api/v1/readings/1
```

---

### `GET /images/{filename}`
Serve a imagem anonimizada processada.

---

## Variáveis de Ambiente (backend)

| Variável                    | Padrão                                                | Descrição                              |
|-----------------------------|-------------------------------------------------------|----------------------------------------|
| `DATABASE_URL`              | `postgresql+asyncpg://postgres:postgres@db:5432/...`  | URL do banco PostgreSQL                |
| `UPLOAD_DIR`                | `/app/uploads`                                        | Diretório temporário de uploads        |
| `PROCESSED_DIR`             | `/app/uploads/processed`                              | Diretório de imagens anonimizadas      |
| `MAX_FILE_SIZE_MB`          | `50`                                                  | Tamanho máximo de arquivo em MB        |
| `OCR_CONFIDENCE_THRESHOLD`  | `0.5`                                                 | Confiança mínima para aceitar leitura  |
| `FACE_BLUR_INTENSITY`       | `51`                                                  | Intensidade do blur (kernel Gaussian)  |
| `CORS_ORIGINS`              | `http://localhost:4200`                               | Origins permitidas (separadas por `,`) |

---

## Regras de privacidade

- A imagem original é **deletada do disco** imediatamente após o processamento.
- Apenas a versão anonimizada (rostos borrados) é persistida.
- O sistema não realiza identificação facial — apenas detecta regiões para aplicar blur.

---

## Tecnologias

| Camada      | Tecnologia                        |
|-------------|-----------------------------------|
| Backend     | Python 3.11, FastAPI, SQLAlchemy  |
| OCR         | EasyOCR                           |
| Visão       | OpenCV (Haar Cascade)             |
| Banco       | PostgreSQL 16                     |
| Frontend    | Angular 17 (standalone components)|
| Container   | Docker Compose                    |
