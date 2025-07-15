import json
import os
import pickle
import platform
from pathlib import Path

import cv2
import numpy as np
import requests

import config
import inspireface as isf


class FaceRecognizer:
    """
    Handles face recognition and enrollment using InspireFace SDK.
    """

    def __init__(self):
        """
        Initializes the FaceRecognizer, loading the InspireFace engine and the face database.
        """
        try:
            model_name = "Megatron"
            model_path = os.path.join(Path.home(), ".inspireface", "models", model_name)

            # Detect if we are running on a Rockchip (e.g., RK3588) Linux device
            self.is_rockchip = platform.system() == "Linux" and (
                platform.machine() in {"aarch64", "arm64"}
            )

            if not os.path.exists(model_path):
                print(f"Model '{model_name}' not found at {model_path}, downloading...")
                try:
                    isf.pull_latest_model(model_name)
                    print("Model downloaded successfully.")
                except Exception as e:
                    print(f"Failed to download model: {e}")
                    exit(1)

            ret = isf.launch(resource_path=model_path)
            if not ret:
                raise RuntimeError("Failed to launch from local model.")

            opt = isf.HF_ENABLE_FACE_RECOGNITION
            self.session = isf.InspireFaceSession(opt, isf.HF_DETECT_MODE_ALWAYS_DETECT)

            # --- Rockchip-specific runtime tweaks --------------------------------------
            # The Rockchip RGA backend crashes when the cropped ROI width stride (in bytes)
            # is not 16-aligned.  This typically happens when the detector returns tiny
            # face boxes (< 16 px) that, after cropping in RGB888 (3 bytes/pixel), produce
            # a 24-byte stride.  We can avoid these edge-cases by:
            #   1) Upscaling the internal preview level to ≥320 px so the detector works
            #      on a reasonably large canvas.
            #   2) Ignoring detections whose bounding-box width is <16 px.
            # The C-API exposes `HFSessionSetTrackPreviewSize` and
            # `HFSessionSetFilterMinimumFacePixelSize`; the Python binding keeps the same
            # snake-case names.  We call them defensively via `hasattr` so the code still
            # runs on platforms / package builds where the symbols are absent.
            if self.is_rockchip:
                # Increase internal preview resolution
                if hasattr(self.session, "set_track_preview_size"):
                    try:
                        self.session.set_track_preview_size(
                            320
                        )  # px, allowed: 160/320/640
                    except Exception:
                        pass  # Non-critical – carry on with default

                # Skip faces smaller than 16 px to keep crop stride safe for RGA
                if hasattr(self.session, "set_filter_minimum_face_pixel_size"):
                    try:
                        self.session.set_filter_minimum_face_pixel_size(16)
                    except Exception:
                        pass

            # Configure and enable the feature hub
            hub_config = isf.FeatureHubConfiguration(
                primary_key_mode=isf.HF_PK_AUTO_INCREMENT,
                search_mode=isf.HF_SEARCH_MODE_EAGER,
                enable_persistence=True,
                persistence_db_path=config.DATABASE_PATH,
                search_threshold=config.SIMILARITY_THRESHOLD,
            )
            ret = isf.feature_hub_enable(hub_config)
            if not ret:
                raise RuntimeError("Failed to enable FeatureHub.")

            self.id_to_name_map = self._load_id_map()

            pickle_path = config.ID_NAME_MAP_PATH.replace(".json", ".pkl")
            if os.path.exists(pickle_path) and not os.path.exists(
                config.ID_NAME_MAP_PATH
            ):
                print(f"Migrating {pickle_path} to {config.ID_NAME_MAP_PATH}")
                self._save_id_map()
                os.remove(pickle_path)
                print(f"Removed old pickle file: {pickle_path}")

            print("InspireFace session created and FeatureHub enabled.")
        except Exception as e:
            print(f"Error creating InspireFace session: {e}")
            exit(1)

    def _load_id_map(self):
        """Loads the ID-to-name mapping from a JSON file or pickle file."""
        if os.path.exists(config.ID_NAME_MAP_PATH):
            with open(config.ID_NAME_MAP_PATH, "r") as f:
                # JSON keys must be strings, so convert them back to integers
                return {int(k): v for k, v in json.load(f).items()}

        pickle_path = config.ID_NAME_MAP_PATH.replace(".json", ".pkl")
        if os.path.exists(pickle_path):
            print(
                f"Found old pickle file at {pickle_path}. It will be migrated to JSON."
            )
            with open(pickle_path, "rb") as f:
                return pickle.load(f)

        return {}

    def _save_id_map(self):
        """Saves the ID-to-name mapping to a JSON file."""
        with open(config.ID_NAME_MAP_PATH, "w") as f:
            # JSON keys must be strings
            json.dump(self.id_to_name_map, f, indent=4)

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
        faces = self.session.face_detection(frame)
        names = []
        confidences = []

        if len(faces) > 0:
            for face in faces:
                feature = self.session.face_feature_extract(frame, face)
                if feature is not None:
                    search_result = isf.feature_hub_face_search(feature)
                    if search_result and search_result.similar_identity.id != -1:
                        found_id = search_result.similar_identity.id
                        name = self.id_to_name_map.get(found_id, "Unknown")
                        names.append(name)
                        confidences.append(search_result.confidence)
                    else:
                        names.append("Unknown")
                        confidences.append(0.0)
                else:
                    names.append("Unknown")
                    confidences.append(0.0)

        frame = self._draw_faces(frame, faces, names, confidences)
        return frame

    def add_face(self, frame):
        """
        Adds a new face to the database from the current frame.
        It detects the largest face in the frame for enrollment.
        """
        faces = self.session.face_detection(frame)
        if not faces:
            print("No faces detected to add.")
            return

        largest_face = max(
            faces,
            key=lambda face: (face.location[2] - face.location[0])
            * (face.location[3] - face.location[1]),
        )
        feature = self.session.face_feature_extract(frame, largest_face)

        if feature is not None:
            print(
                "\\n[ACTION REQUIRED] Video feed is paused. Please type a name in this terminal and press Enter to enroll the new face."
            )
            name = input("Enter the name for the new face: ")
            if name:
                # The 'id' argument is required by FaceIdentity, but since the hub's
                # primary_key_mode is AUTO_INCREMENT, the value is ignored.
                # We pass a dummy ID of -1. The hub returns the real new ID.
                identity = isf.FaceIdentity(feature, id=-1)
                ret, new_id = isf.feature_hub_face_insert(identity)
                if ret:
                    self.id_to_name_map[new_id] = name
                    self._save_id_map()
                    print(f"Added new face for {name} with ID {new_id}.")
                else:
                    print(f"Failed to add face for {name}.")

    def register_faces_from_json(self, json_file_path):
        """
        Registers faces from a JSON file containing person data.

        Args:
            json_file_path: Path to the JSON file.
        """
        print(f"Registering faces from {json_file_path}...")
        try:
            with open(json_file_path, "r") as f:
                people_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading JSON file: {e}")
            return

        for person in people_data:
            name = person.get("preferredName")
            image_url = person.get("picture")

            if not name or not image_url:
                print(f"Skipping person with missing name or picture URL: {person}")
                continue

            if name in self.id_to_name_map.values():
                print(f"'{name}' already seems to be registered. Skipping.")
                continue

            print(f"Processing {name} from {image_url}")
            try:
                # Use a timeout for urlopen to avoid hanging
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()  # Raise an exception for bad status codes
                image_data = np.frombuffer(response.content, dtype="uint8")
                frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

                if frame is None:
                    print(f"Could not decode image for {name} from {image_url}")
                    continue

                faces = self.session.face_detection(frame)
                if not faces:
                    print(f"No faces detected for {name} in image from {image_url}")
                    continue

                # Assuming the largest face is the correct one, similar to add_face
                largest_face = max(
                    faces,
                    key=lambda face: (face.location[2] - face.location[0])
                    * (face.location[3] - face.location[1]),
                )
                feature = self.session.face_feature_extract(frame, largest_face)

                if feature is not None:
                    identity = isf.FaceIdentity(feature, id=-1)
                    ret, new_id = isf.feature_hub_face_insert(identity)
                    if ret:
                        self.id_to_name_map[new_id] = name
                        self._save_id_map()
                        print(
                            f"Successfully added new face for {name} with ID {new_id}."
                        )
                    else:
                        print(f"Failed to add face for {name} to feature hub.")
                else:
                    print(f"Could not extract feature for {name} from image.")

            except requests.exceptions.RequestException as e:
                print(f"Failed to download image for {name} from {image_url}: {e}")
            except Exception as e:
                print(f"An error occurred while processing {name}: {e}")

        print("Completed face registration from JSON file.")

    def delete_face(self):
        """
        Deletes a face from the database.
        """
        if not self.id_to_name_map:
            print("No faces to delete.")
            return

        print("\\n--- Enrolled Faces ---")
        for id, name in self.id_to_name_map.items():
            print(f"  ID: {id}, Name: {name}")
        print("--------------------\\n")

        try:
            face_id_to_delete = int(input("Enter the ID of the face to delete: "))
            if face_id_to_delete in self.id_to_name_map:
                if isf.feature_hub_face_remove(face_id_to_delete):
                    name = self.id_to_name_map.pop(face_id_to_delete)
                    self._save_id_map()
                    print(f"Successfully deleted {name} (ID: {face_id_to_delete}).")
                else:
                    print(
                        f"Failed to delete face with ID {face_id_to_delete} from the feature hub."
                    )
            else:
                print("Invalid ID.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    def run(self):
        """
        Starts the video capture and face recognition loop. It automatically
        finds a working camera by trying indices 0 through 4.
        """
        cap = None
        for i in range(5):
            print(f"Attempting to open camera at index {i}...")
            temp_cap = cv2.VideoCapture(i)
            # Test if the camera is opened and we can read a frame
            if temp_cap.isOpened() and temp_cap.read()[0]:
                print(f"Successfully opened camera at index {i}.")
                cap = temp_cap
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                break
            else:
                # Release the capture if it's not working
                temp_cap.release()

        if cap is None:
            print(
                "Error: Could not open a working video stream from any of the first 5 indices."
            )
            return

        print("\\n--- Controls ---")
        print(" 'a' - Add a new face (when prompted in console)")
        print(" 'd' - Delete a face")
        print(" 'q' - Quit")
        print("----------------\\n")

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if self.is_rockchip:
                # RGA requires RGB888 width stride to be 16-aligned. Add padding on the right if needed.
                height, width = frame.shape[:2]
                pad_x = (-width) % 16  # how many columns to pad to reach multiple of 16
                if pad_x:
                    frame = cv2.copyMakeBorder(
                        frame,
                        top=0,
                        bottom=0,
                        left=0,
                        right=pad_x,
                        borderType=cv2.BORDER_CONSTANT,
                        value=[0, 0, 0],  # black padding
                    )
            processed_frame = self.recognize_faces(frame)
            cv2.imshow("InspireFace Recognition", processed_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("a"):
                self.add_face(frame)
            elif key == ord("d"):
                self.delete_face()

        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Face Recognition System")
    parser.add_argument(
        "--register-json",
        type=str,
        help="Path to a JSON file to register faces from.",
    )
    args = parser.parse_args()

    recognizer = FaceRecognizer()

    if args.register_json:
        recognizer.register_faces_from_json(args.register_json)
    else:
        recognizer.run()
