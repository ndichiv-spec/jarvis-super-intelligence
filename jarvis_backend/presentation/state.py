"""User-scoped presentation preferences, active state, and transition history."""

from __future__ import annotations

from typing import Any

from ..core import get_store
from .context import DEFAULT_PROFILE
from .schemas import PresentationPreferenceUpdate, UserPresentationProfile


class PresentationStateManager:
    def get_preferences(self, user_id: str) -> UserPresentationProfile:
        saved = get_store("presentation_preferences").load().get(user_id, {})
        return UserPresentationProfile.model_validate({**DEFAULT_PROFILE, **saved})

    def update_preferences(
        self,
        user_id: str,
        update: PresentationPreferenceUpdate,
    ) -> UserPresentationProfile:
        store = get_store("presentation_preferences")
        previous = store.load().get(user_id, {})
        merged = {**DEFAULT_PROFILE, **previous, **update.model_dump(exclude_unset=True, exclude_none=True)}
        profile = UserPresentationProfile.model_validate(merged)
        store.save_key(user_id, profile.model_dump(mode="json"))
        return profile

    def get_state(self, user_id: str, session_id: str) -> dict[str, Any]:
        key = self._key(user_id, session_id)
        return get_store("presentation_state").load().get(key, {})

    def get_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        key = self._key(user_id, session_id)
        return get_store("presentation_history").load().get(key, [])

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"


presentation_state_manager = PresentationStateManager()
