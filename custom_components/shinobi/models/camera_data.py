import logging
import sys

from ..helpers.const import *

_LOGGER = logging.getLogger(__name__)


class CameraData:
    monitorId: str
    name: str
    details: dict
    has_audio: bool
    has_audio_detector: bool
    has_motion_detector: bool
    fps: int
    jpeg_api_enabled: bool
    original_stream: str
    mode: str

    def __init__(self, camera):
        try:
            self.monitorId = camera.get(ATTR_CAMERA_MONITOR_ID)
            self.name = camera.get(ATTR_CAMERA_NAME)
            self.status = camera.get(ATTR_CAMERA_STATUS)
            self.snapshot = camera.get(ATTR_CAMERA_SNAPSHOT)
            self.streams = camera.get(ATTR_CAMERA_STREAMS)
            self.mode = camera.get(ATTR_CAMERA_MODE)
            self.details = camera
            self.jpeg_api_enabled = self.snapshot is not None and self.snapshot != ""

            monitor_details = camera.get("details", {})

            fps = monitor_details.get(ATTR_CAMERA_DETAILS_FPS, "1")

            if "." in fps:
                fps = fps.split(".")[0]

            self.fps = 1 if fps == "" else int(fps)
            self.has_audio = monitor_details.get(ATTR_CAMERA_DETAILS_AUDIO_CODEC, "no") != "no"
            self.has_audio_detector = monitor_details.get(ATTR_CAMERA_DETAILS_DETECTOR_AUDIO, "0") != "0"
            self.has_motion_detector = monitor_details.get(ATTR_CAMERA_DETAILS_DETECTOR, "0") != "0"
            original_stream = monitor_details.get(ATTR_ORIGINAL_STREAM)
            stream_username = monitor_details.get(ATTR_STREAM_USERNAME)
            stream_password = monitor_details.get(ATTR_STREAM_PASSWORD)
            stream_credentials = f"{STREAM_PROTOCOL_SUFFIX}{stream_username}:{stream_password}@"

            if original_stream is not None and stream_credentials not in original_stream:
                original_stream = original_stream.replace(STREAM_PROTOCOL_SUFFIX, stream_credentials)

            self.original_stream = original_stream

        except Exception as ex:
            exc_type, exc_obj, tb = sys.exc_info()
            line_number = tb.tb_lineno

            _LOGGER.error(
                f"Failed to initialize CameraData: {camera}, Error: {ex}, Line: {line_number}"
            )

    @property
    def disabled(self):
        is_disabled = self.mode == "stop"

        return is_disabled

    def __repr__(self):
        obj = {
            ATTR_CAMERA_MONITOR_ID: self.monitorId,
            ATTR_CAMERA_NAME: self.name,
            ATTR_CAMERA_STATUS: self.name,
            ATTR_CAMERA_SNAPSHOT: self.snapshot,
            ATTR_CAMERA_STREAMS: self.streams,
            ATTR_CAMERA_DETAILS: self.details,
            ATTR_ORIGINAL_STREAM: self.original_stream,
            MOTION_DETECTION: self.has_motion_detector,
            SOUND_DETECTION: self.has_audio_detector,
            TRIGGER_PLUG_DB: self.has_audio,
            ATTR_FPS: self.fps
        }

        to_string = f"{obj}"

        return to_string
