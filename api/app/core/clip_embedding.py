import asyncio
from io import BytesIO
from threading import Lock
from typing import Any, cast

from api.app.config import Settings

CLIP_IMAGE_CONTENT_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


class ClipEmbeddingClient:
    """Lazy local CLIP encoder for text-image retrieval."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.multimodal_rag_enabled
        self.model = settings.clip_model
        self.dimension = settings.clip_embedding_dimension
        self._device_setting = settings.clip_device
        self._local_files_only = settings.clip_local_files_only
        self._model: Any | None = None
        self._processor: Any | None = None
        self._torch: Any | None = None
        self._image_class: Any | None = None
        self._device: str | None = None
        self._load_lock = Lock()

    async def warmup(self) -> None:
        """Download and load the configured CLIP model if multimodal RAG is enabled."""

        if not self.enabled:
            return
        await asyncio.to_thread(self.warmup_sync)

    def warmup_sync(self) -> None:
        """Synchronous variant used by worker startup hooks."""

        if not self.enabled:
            return
        self._load_model()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Encode text queries into the CLIP shared embedding space."""

        if not self.enabled or not texts:
            return []
        return await asyncio.to_thread(self._embed_texts_sync, texts)

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        """Encode images into the CLIP shared embedding space."""

        if not self.enabled or not images:
            return []
        return await asyncio.to_thread(self._embed_images_sync, images)

    async def close(self) -> None:
        """Release interface placeholder for symmetry with async clients."""

    def _embed_texts_sync(self, texts: list[str]) -> list[list[float]]:
        model, processor, torch, device = self._load_model()
        inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            features = model.get_text_features(**inputs)
            features = torch.nn.functional.normalize(features, p=2, dim=1)
        return cast(list[list[float]], features.detach().cpu().tolist())

    def _embed_images_sync(self, images: list[bytes]) -> list[list[float]]:
        model, processor, torch, device = self._load_model()
        pil_images = [self._load_image(content) for content in images]
        inputs = processor(images=pil_images, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            features = model.get_image_features(**inputs)
            features = torch.nn.functional.normalize(features, p=2, dim=1)
        return cast(list[list[float]], features.detach().cpu().tolist())

    def _load_model(self) -> tuple[Any, Any, Any, str]:
        if self._model is not None and self._processor is not None and self._torch is not None:
            return self._model, self._processor, self._torch, str(self._device)

        with self._load_lock:
            if self._model is not None and self._processor is not None and self._torch is not None:
                return self._model, self._processor, self._torch, str(self._device)

            try:
                import torch
                from PIL import Image
                from transformers import CLIPModel, CLIPProcessor
            except ImportError as exc:
                raise RuntimeError(
                    "CLIP multimodal RAG requires torch, pillow, and transformers. "
                    "Run `uv sync --extra dev` after updating dependencies."
                ) from exc

            device = self._resolve_device(torch)
            processor = CLIPProcessor.from_pretrained(
                self.model,
                local_files_only=self._local_files_only,
            )
            model = CLIPModel.from_pretrained(
                self.model,
                local_files_only=self._local_files_only,
            ).to(device)
            model.eval()

            self._image_class = Image
            self._torch = torch
            self._processor = processor
            self._model = model
            self._device = device
            return model, processor, torch, device

    def _resolve_device(self, torch: object) -> str:
        if self._device_setting != "auto":
            return self._device_setting
        torch_module = cast(Any, torch)
        return "cuda" if torch_module.cuda.is_available() else "cpu"

    def _load_image(self, content: bytes) -> object:
        if self._image_class is None:
            self._load_model()
        image_class = cast(Any, self._image_class)
        return image_class.open(BytesIO(content)).convert("RGB")


def is_clip_image_content_type(content_type: str) -> bool:
    """Return whether an asset content type can be embedded by CLIP."""

    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized in CLIP_IMAGE_CONTENT_TYPES