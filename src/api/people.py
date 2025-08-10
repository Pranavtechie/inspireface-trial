from __future__ import annotations

import os
from urllib.parse import urlparse

import requests as req
from flask import Blueprint, jsonify, request

from src.config import ENROLLMENT_IMAGES_DIR
from src.core.face_recognizer import FaceRecognizer
from src.schema import FaceIdentityMap, Person, db
from src.utils import ist_timestamp

people_bp = Blueprint("people", __name__, url_prefix="/people")


@people_bp.before_request
def _open_db():
    if db.is_closed():
        db.connect(reuse_if_open=True)


@people_bp.teardown_request
def _close_db(exc):
    if not db.is_closed():
        db.close()


def _download_image_if_needed(picture_url: str) -> tuple[str, bool]:
    """Ensure the image is downloaded locally; return (local_path, downloaded_now)."""
    parsed_url = urlparse(picture_url)
    filename = os.path.basename(parsed_url.path)
    if not filename.lower().endswith(".jpg"):
        raise ValueError("Only .jpg images are supported")

    local_path = os.path.join(ENROLLMENT_IMAGES_DIR, filename)

    if os.path.exists(local_path):
        return local_path, False

    response = req.get(picture_url, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to download image (status={response.status_code})")

    content_type = response.headers.get("Content-Type", "")
    if "image/jpeg" not in content_type.lower():
        raise ValueError("URL does not point to a JPEG image")

    with open(local_path, "wb") as f:
        f.write(response.content)

    return local_path, True


@people_bp.route("/add", methods=["POST"])
def add_person():
    data = request.get_json(silent=True) or {}

    person_id = data.get("personId")
    user_type = data.get("userType")  # Cadet | Employee
    name = data.get("preferredName") or data.get("name")
    picture_url = data.get("picture") or data.get("pictureUrl")

    if not person_id or not user_type or not name or not picture_url:
        return (
            jsonify(
                {
                    "error": "Missing required fields",
                    "required": [
                        "personId",
                        "userType",
                        "preferredName|name",
                        "picture",
                    ],
                }
            ),
            400,
        )

    try:
        local_path, downloaded_now = _download_image_if_needed(picture_url)
    except Exception as e:
        return jsonify({"error": "Image fetch failed", "details": str(e)}), 400

    synced_at = ist_timestamp()

    # Insert/update Person in SQLite
    try:
        if user_type == "Cadet":
            Person.insert(
                uniqueId=person_id,
                name=name,
                admissionNumber=data.get("admissionNumber"),
                roomId=data.get("roomId"),
                pictureFileName=os.path.basename(local_path),
                personType=user_type,
                syncedAt=synced_at,
            ).on_conflict_replace().execute()
        else:
            Person.insert(
                uniqueId=person_id,
                name=name,
                admissionNumber=data.get("admissionNumber"),
                roomId=data.get("roomId"),
                pictureFileName=os.path.basename(local_path),
                personType=user_type,
                syncedAt=synced_at,
            ).on_conflict_replace().execute()
    except Exception as e:
        if downloaded_now:
            try:
                os.remove(local_path)
            except OSError:
                pass
        return jsonify({"error": "Failed to upsert person", "details": str(e)}), 500

    # Enroll into InspireFace FeatureHub and create mapping
    try:
        import cv2

        frame = cv2.imread(local_path)
        if frame is None:
            raise ValueError("Could not load image for enrollment")

        recognizer = FaceRecognizer()
        result = recognizer.add_face(frame, person_id)
        if result is None:
            raise RuntimeError("No face detected to enroll")
    except Exception as e:
        return (
            jsonify(
                {
                    "error": "Enrollment to FeatureHub failed",
                    "details": str(e),
                }
            ),
            500,
        )

    return jsonify({"syncedAt": synced_at, "personId": person_id}), 200


@people_bp.route("/<person_id>", methods=["DELETE"])
def delete_person(person_id: str):
    # Find mapping to FeatureHub id if exists
    hub_id = None
    mapping = None
    try:
        mapping = FaceIdentityMap.get_or_none(FaceIdentityMap.personId == person_id)
        if mapping:
            hub_id = mapping.hubId
    except Exception:
        hub_id = None

    # Remove from FeatureHub first (if mapped)
    feature_removed = None
    if hub_id is not None:
        try:
            import inspireface as isf

            # Ensure FeatureHub is enabled by constructing a recognizer
            _ = FaceRecognizer()
            feature_removed = isf.feature_hub_face_remove(int(hub_id))
        except Exception as e:
            return jsonify(
                {"error": "Failed to remove from FeatureHub", "details": str(e)}
            ), 500

    # Delete mapping row
    try:
        if mapping:
            mapping.delete_instance()
    except Exception:
        pass

    # Delete person from SQLite and remove local image if present
    try:
        person = Person.get_or_none(Person.uniqueId == person_id)
        if person:
            image_path = os.path.join(ENROLLMENT_IMAGES_DIR, person.pictureFileName)
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except OSError:
                pass
            person.delete_instance()
    except Exception as e:
        return jsonify({"error": "Failed to delete person", "details": str(e)}), 500

    return jsonify(
        {"deleted": True, "personId": person_id, "featureRemoved": feature_removed}
    ), 200
