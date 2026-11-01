import cv2
import numpy as np

# Open the default webcam
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    raise RuntimeError("Could not open webcam")

frame_width = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

MARKER_LENGTH = 0.1  # Marker side length in meters

camera_matrix = np.array([
    [800, 0, frame_width / 2],
    [0, 800, frame_height / 2],
    [0, 0, 1]
], dtype=np.float32)
dist_coeffs = np.zeros((5, 1), dtype=np.float32)

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

robots = {
    1: "Robot 1",
    2: "Robot 2",
    3: "Robot 3",
    4: "Robot 4",
    5: "Robot 5",
    6: "Robot 6",
    7: "Robot 7",
    8: "Robot 8",
    41: "Top Left",
    42: "Top Right",
    43: "Bottom Left",
    44: "Bottom Right"
}
try:
    while True:
        ret, frame = camera.read()
        if not ret:
            print("Could not read from webcam")
            break

        grid = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)

        if ids is not None:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            for marker_id, marker_corners in zip(ids.flatten(), corners):
                half = MARKER_LENGTH / 2
                object_points = np.array([
                    [-half,  half, 0],
                    [ half,  half, 0],
                    [ half, -half, 0],
                    [-half, -half, 0],
                ], dtype=np.float32)

                image_points = marker_corners.reshape(4, 2)

                ok, rvec, tvec = cv2.solvePnP(
                    object_points,
                    image_points,
                    camera_matrix,
                    dist_coeffs,
                    flags=cv2.SOLVEPNP_IPPE_SQUARE,
                )

                if not ok:
                    continue

                cv2.drawFrameAxes(frame, camera_matrix, dist_coeffs, rvec, tvec, 0.05)

                # Calculate yaw
                rotation_matrix, _ = cv2.Rodrigues(rvec)
                yaw_degrees = np.degrees(
                    np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
                )
                camera_yaw = -yaw_degrees

                # Find marker center and grid cell (1–10)
                points = marker_corners.reshape(4, 2)
                center_x = int(points[:, 0].mean())
                center_y = int(points[:, 1].mean())
                column = min(center_x * 10 // frame_width + 1, 10)
                row = min(center_y * 10 // frame_height + 1, 10)

                robot_name = robots.get(int(marker_id), "Unknown robot")
                print(robot_name, "позиция:", column, row, "угол:", camera_yaw)

        # Draw 10×10 grid
        for i in range(1, 10):
            x = frame_width * i // 10
            y = frame_height * i // 10
            cv2.line(grid, (x, 0), (x, frame_height), (0, 0, 255), 1)
            cv2.line(grid, (0, y), (frame_width, y), (0, 0, 255), 1)

        cv2.imshow("Webcam", frame)
        cv2.imshow("Grid", grid)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        
finally:
    camera.release()
    cv2.destroyAllWindows()