import logging
from celery import Celery
from celery.signals import worker_init, worker_process_init
from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "camera_detector",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.camera_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # cada processo pega 1 task por vez
    task_acks_late=True,            # confirma só após conclusão
    # Sem time limit — tasks de câmera rodam indefinidamente
    task_time_limit=None,
    task_soft_time_limit=None,
)


def _load_models():
    """Carrega EasyOCR + dlib na memória. Deve ser chamado uma única vez
    no processo pai (antes de fork) para que os filhos herdem via copy-on-write."""
    logger.info("[worker] carregando modelos de visão computacional…")
    try:
        from app.services.plate_detector import get_ocr_reader
        get_ocr_reader()
        logger.info("[worker] EasyOCR OK")
    except Exception as exc:
        logger.warning("[worker] EasyOCR falhou: %s", exc)
    try:
        import face_recognition  # noqa — inicializa dlib
        logger.info("[worker] face_recognition (dlib) OK")
    except Exception as exc:
        logger.warning("[worker] face_recognition falhou: %s", exc)
    logger.info("[worker] modelos prontos — pronto para receber tasks")


# ── worker_init: dispara no PROCESSO PAI antes de qualquer fork ──────────────
# Os filhos herdam os modelos carregados via copy-on-write (sem recarregar).
@worker_init.connect
def preload_in_parent(**kwargs):
    _load_models()


# ── worker_process_init: fallback — dispara em cada processo filho ───────────
# Só entra em ação se o filho não herdou os modelos (ex: execv habilitado).
_models_loaded = False

@worker_process_init.connect
def preload_in_child(**kwargs):
    global _models_loaded
    if not _models_loaded:
        _load_models()
        _models_loaded = True
