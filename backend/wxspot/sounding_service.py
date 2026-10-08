"""API-side immutable profiles and separate derived jobs, sharing the bounded worker."""

import asyncio
import json
from collections import OrderedDict

from wxspot.providers.soundings import distance_km
from wxspot.sounding_contracts import (
    SoundingDiagnostics,
    SoundingProfile,
    SoundingResponse,
    SoundingSelection,
)
from wxspot.weather import SourceError
from wxspot.weather_jobs import enqueue


class SoundingService:
    def __init__(self, objects):
        self.objects = objects
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()

    async def document(self, key):
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            data = await self.objects.get(key)
            if len(data) > 2 * 1024 * 1024:
                raise SourceError("source_unavailable", "Prepared sounding is too large")
            document = json.loads(data)
            self.cache[key] = document
            while len(self.cache) > 16:
                self.cache.popitem(last=False)
            return document

    async def get(self, selection: SoundingSelection):
        point = [selection.lon, selection.lat]
        job = await enqueue(selection.profile_payload(), retry_failed=selection.retry_failed)
        response = SoundingResponse(state="preparing", requested_point=point, retry_after_seconds=3)
        if job.state == "failed":
            return response.model_copy(update={"state": "source_unavailable", "message": job.error})
        if job.state != "ready" or not job.manifest:
            return response
        document = await self.document(job.manifest["object_key"])
        profile = SoundingProfile.model_validate(document["profile"])
        response.profile = profile
        response.distance_km = distance_km(point, profile.sampled_point)
        response.options = document.get("options", {})
        derived = await enqueue(
            {
                "source_type": "sounding",
                "source_id": "noaa-soundings",
                "stage": "diagnostics",
                "profile_identity": profile.identity,
                "profile_object_key": job.manifest["object_key"],
                "parcel": selection.parcel,
                "motion": selection.motion,
                "storm_u": selection.storm_u if selection.motion == "custom" else None,
                "storm_v": selection.storm_v if selection.motion == "custom" else None,
            },
            retry_failed=selection.retry_failed,
        )
        if derived.state == "failed":
            response.state, response.message = "source_unavailable", derived.error
        elif derived.state == "ready" and derived.manifest:
            data = await self.document(derived.manifest["object_key"])
            response.diagnostics = SoundingDiagnostics.model_validate(data["diagnostics"])
            response.state, response.retry_after_seconds = "ready", None
        return response
