import os
import platform
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Set, Tuple

import cv2
import inspireface as isf

from src.config import DATABASE_PATH, SIMILARITY_THRESHOLD
from src.ipc import send_message
from src.logger import get_core_ui_logger
from src.schema import FaceIdentityMap, Person, db
from src.utils import ist_timestamp


class FaceRecognizer:
    """
    Handles face recognition and enrollment using InspireFace SDK.
    """

    def __init__(self):
        """
        Initializes the FaceRecognizer, loading the InspireFace engine and the face database.
        """
        self.logger = get_core_ui_logger("face_recognizer")
        # Tracks the active session and which personIds have been marked during it.
        self.current_session_id: Optional[str] = None
        self._attendance_marked_by_session: Dict[str, Set[str]] = {}
        # Optional UI callback invoked when a person is first marked in a session
        self.on_first_attendance: Optional[Callable[[str], None]] = None

        try:
            # -------------------------------------------------------------
            # Diagnostic logs to trace initialisation on all platforms
            # -------------------------------------------------------------
            self.logger.info("FaceRecognizer initialisation started")
            self.logger.debug(
                "Platform detected: system=%s, machine=%s",
                platform.system(),
                platform.machine(),
            )

            model_name = "Pikachu"
            model_path = os.path.join(Path.home(), ".inspireface", "models", model_name)
            self.logger.info("Using model '%s' at %s", model_name, model_path)

            # Detect if we are running on a Rockchip (e.g., RK3588) Linux device
            self.is_rockchip = platform.system() == "Linux" and (
                platform.machine() in {"aarch64", "arm64"}
            )
            self.logger.info("is_rockchip resolved to %s", self.is_rockchip)

            if not os.path.exists(model_path):
                print(f"Model '{model_name}' not found at {model_path}, downloading...")
                try:
                    isf.pull_latest_model(model_name)
                    print("Model downloaded successfully.")
                except Exception as e:
                    print(f"Failed to download model: {e}")
                    exit(1)

            self.logger.info("Launching InspireFace engine …")
            ret = isf.launch(resource_path=model_path)
            self.logger.debug("isf.launch returned %s", ret)
            if not ret:
                raise RuntimeError("Failed to launch from local model.")

            opt = isf.HF_ENABLE_FACE_RECOGNITION
            self.session = isf.InspireFaceSession(opt, isf.HF_DETECT_MODE_ALWAYS_DETECT)

            # Configure and enable the feature hub
            self.logger.info("Enabling FeatureHub …")
            hub_config = isf.FeatureHubConfiguration(
                primary_key_mode=isf.HF_PK_AUTO_INCREMENT,
                search_mode=isf.HF_SEARCH_MODE_EAGER,
                enable_persistence=True,
                persistence_db_path=DATABASE_PATH,
                search_threshold=SIMILARITY_THRESHOLD,
            )

            ret = isf.feature_hub_enable(hub_config)
            self.logger.debug("feature_hub_enable returned %s", ret)
            if not ret:
                raise RuntimeError("Failed to enable FeatureHub.")

            print("InspireFace session created and FeatureHub enabled.")

            # Log basic runtime/platform information
            self.logger.info(
                "Session launched – Rockchip: %s, model path: %s",
                self.is_rockchip,
                model_path,
            )
        except Exception as e:
            self.logger.exception("Exception during FaceRecognizer initialisation")
            print(f"Error creating InspireFace session: {e}")
            exit(1)

    # Legacy ID-to-name helpers removed as we now resolve names via DB mapping

    # --- Idempotency tracking for attendance (per session) --------------------
    def set_current_session(self, session_id: Optional[str]) -> None:
        """Set the current session context.

        Resets internal write-set when session changes. If ``session_id`` is None,
        idempotency tracking is effectively disabled until a session is set again.
        """
        if session_id == self.current_session_id:
            return

        self.current_session_id = session_id
        if session_id is None:
            return

        # Ensure a fresh container exists for this session
        if session_id not in self._attendance_marked_by_session:
            self._attendance_marked_by_session[session_id] = set()

    def add_attendance_if_new(self, person_id: str) -> bool:
        """Record a person's attendance for the current session if not seen.

        Returns True if this is the first time this person is seen in the current
        session, False if already recorded or if no session is active.
        """
        if not self.current_session_id:
            return False
        seen_set = self._attendance_marked_by_session.setdefault(
            self.current_session_id, set()
        )
        if person_id in seen_set:
            return False
        seen_set.add(person_id)
        return True

    def get_attendance_marked_tuple(self) -> Tuple[str, ...]:
        """Return a tuple of personIds marked for the current session.

        This provides an immutable snapshot suitable for idempotency checks.
        Returns an empty tuple when no active session is set.
        """
        if not self.current_session_id:
            return tuple()
        return tuple(
            self._attendance_marked_by_session.get(self.current_session_id, set())
        )

    def seed_attendance_for_session(
        self, session_id: Optional[str], person_ids: Iterable[str]
    ) -> None:
        """Seed idempotency set with already-present personIds for a session.

        This prevents duplicate "person-recognized" events for people who were
        already marked present before the current run.
        """
        if not session_id:
            return
        if not person_ids:
            return
        session_set = self._attendance_marked_by_session.setdefault(session_id, set())
        for pid in person_ids:
            if pid:
                session_set.add(pid)

    def seed_current_session(self, person_ids: Iterable[str]) -> None:
        """Seed idempotency for the currently active session."""
        self.seed_attendance_for_session(self.current_session_id, person_ids)

    def set_on_first_attendance_callback(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        """Register a callback to be invoked on first attendance per session."""
        self.on_first_attendance = callback

    def _draw_faces(self, frame, faces, names, confidences):
        """Draws bounding boxes and names on the frame."""
        for i, face in enumerate(faces):
            x1, y1, x2, y2 = face.location
            box = (int(x1), int(y1), int(x2), int(y2))
            name = names[i]
            confidence = confidences[i]
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)

            cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)

            if name != "Unknown":
                text = f"{name}: {confidence:.2f}"
            else:
                text = name
            cv2.putText(
                frame,
                text,
                (box[0], box[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
        return frame

    def recognize_faces(self, frame):
        """
        Detects and recognizes faces in a given frame.

        Args:
            frame: The video frame to process.

        Returns:
            The frame with detected faces and information drawn on it.
        """
        # Face detection can occasionally raise ProcessingError on RK3588 when
        # the RGA backend rejects an image with stride issues.  Capture the
        # exception so we can inspect the circumstances.
        try:
            faces = self.session.face_detection(frame)
        except Exception as e:
            self.logger.exception(
                "face_detection failed - frame.shape=%sx%sx%s | error=%s",
                *frame.shape,
                e,
            )
            # On Rockchip, stride issues can crash processing. Skip this frame.
            return frame

        names = []
        confidences = []

        if len(faces) > 0:
            # Log bounding-box dimensions for further analysis
            for face in faces:
                x1, y1, x2, y2 = face.location
                bw, bh = x2 - x1, y2 - y1
                self.logger.debug(
                    "Detected face - box=(%s,%s,%s,%s) w=%s h=%s",
                    x1,
                    y1,
                    x2,
                    y2,
                    bw,
                    bh,
                )
            for face in faces:
                feature = self.session.face_feature_extract(frame, face)
                if feature is not None:
                    search_result = isf.feature_hub_face_search(feature)
                    if search_result and search_result.similar_identity.id != -1:
                        feature_id = search_result.similar_identity.id
                        # Resolve to Person via FaceIdentityMap, but manual PK means feature_id maps from personId
                        resolved_name = "Unknown"
                        person = None
                        try:
                            if db.is_closed():
                                db.connect(reuse_if_open=True)
                            mapping = FaceIdentityMap.get_or_none(
                                FaceIdentityMap.hubId == feature_id
                            )
                            if mapping:
                                person = Person.get_or_none(
                                    Person.uniqueId == mapping.personId
                                )
                                if person:
                                    resolved_name = person.name
                                    # Record for idempotency: mark once per session
                                    try:
                                        is_first_time = self.add_attendance_if_new(
                                            person.uniqueId
                                        )
                                    except Exception:
                                        is_first_time = False

                                    # If first time in this session, notify server via IPC
                                    if is_first_time and self.current_session_id:
                                        try:
                                            payload = {
                                                "type": "person-recognized",
                                                "sessionId": self.current_session_id,
                                                "personId": person.uniqueId,
                                                "attendanceTimeStamp": ist_timestamp(),
                                            }
                                            send_message(payload)
                                        except Exception:
                                            # Never let IPC send break recognition pipeline
                                            pass
                                        # Notify UI to optimistically update counts
                                        try:
                                            if self.on_first_attendance:
                                                self.on_first_attendance(
                                                    person.uniqueId
                                                )
                                        except Exception:
                                            pass
                        finally:
                            if not db.is_closed():
                                db.close()

                        names.append(resolved_name)
                        confidences.append(search_result.confidence)
                    else:
                        names.append("Unknown")
                        confidences.append(0.0)
                else:
                    names.append("Unknown")
                    confidences.append(0.0)

        frame = self._draw_faces(frame, faces, names, confidences)
        return frame

    def add_face(self, frame, person_id: Optional[str] = None):
        """
        Adds a new face to the database from the current frame.
        It detects the largest face in the frame for enrollment.
        If person_id is provided, store mapping of FeatureHub id to our person id.
        Returns (hub_id, feature) on success, else None.
        """
        faces = self.session.face_detection(frame)
        if not faces:
            print("No faces detected to add.")
            return None

        largest_face = max(
            faces,
            key=lambda face: (face.location[2] - face.location[0])
            * (face.location[3] - face.location[1]),
        )
        feature = self.session.face_feature_extract(frame, largest_face)

        if feature is not None:
            # The 'id' argument is required by FaceIdentity, but since the hub's
            # primary_key_mode is AUTO_INCREMENT, the value is ignored.
            # We pass a dummy ID of -1. The hub returns the real new ID.
            identity = isf.FaceIdentity(feature, id=-1)
            ret, new_id = isf.feature_hub_face_insert(identity)
            if ret:
                if person_id:
                    try:
                        if db.is_closed():
                            db.connect(reuse_if_open=True)
                        FaceIdentityMap.insert(
                            hubId=new_id, personId=person_id
                        ).on_conflict_replace().execute()
                    finally:
                        if not db.is_closed():
                            db.close()
                return new_id, feature
            else:
                print("Failed to add face to FeatureHub.")
                return None
